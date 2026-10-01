import os
import sys
import time
import json
import hashlib
import statistics
from typing import Any, Dict, List, Optional, Tuple

import requests


BASE_URL = os.getenv("BAGEL_BASE_URL", "https://api.bagelsmp.com/v1").rstrip("/")
API_TOKEN = os.getenv("BAGEL_API_TOKEN", "").strip()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))
MAX_DURATION_SECONDS = int(os.getenv("MAX_DURATION_SECONDS", "19800"))
MIN_PROFIT = float(os.getenv("MIN_PROFIT", "100"))
MIN_ROI = float(os.getenv("MIN_ROI", "0.05"))
AH_FEE_RATE = float(os.getenv("AH_FEE_RATE", "0.0"))
MAX_ALERTS = int(os.getenv("MAX_ALERTS", "8"))
BUDGET = float(os.getenv("BUDGET", "100000"))
MIN_DURABILITY_PERCENT = float(os.getenv("MIN_DURABILITY_PERCENT", "70"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
HEARTBEAT = os.getenv("HEARTBEAT", "1") == "1"

# A sell price is based on exactly the five cheapest active AH listings
# for the item, measured by price per item. We then undercut that average
# by 5% so the scanner does not assume we can sell at the market average.
PRICE_SAMPLE_SIZE = 5
SELL_UNDERCUT_RATE = 0.05

# Enchantment demand is used as a marketability signal, NOT as a fake price
# multiplier. These are item-specific usefulness priorities based on Minecraft
# enchantment effects. Live Bagel market data still decides the actual price.
ENCHANTMENT_DEMAND = {
    "tools": {
        "efficiency": 1.00, "fortune": 1.00, "mending": 0.95,
        "unbreaking": 0.90, "silk_touch": 0.85,
    },
    "weapons": {
        "sharpness": 1.00, "looting": 0.95, "mending": 0.95,
        "unbreaking": 0.90, "fire_aspect": 0.70, "knockback": 0.45,
        "smite": 0.45, "bane_of_arthropods": 0.25,
    },
    "armor": {
        "protection": 1.00, "mending": 1.00, "unbreaking": 0.95,
        "feather_falling": 0.95, "respiration": 0.80,
        "aqua_affinity": 0.70, "depth_strider": 0.85,
        "fire_protection": 0.55, "blast_protection": 0.45,
        "projectile_protection": 0.45, "thorns": 0.30,
        "frost_walker": 0.30,
    },
    "bow": {
        "power": 1.00, "infinity": 0.95, "mending": 0.95,
        "unbreaking": 0.90, "flame": 0.75, "punch": 0.55,
    },
    "crossbow": {
        "quick_charge": 1.00, "piercing": 0.85,
        "multishot": 0.75, "unbreaking": 0.90, "mending": 0.95,
    },
    "trident": {
        "loyalty": 1.00, "impaling": 0.80, "channeling": 0.75,
        "riptide": 0.65, "mending": 0.95, "unbreaking": 0.90,
    },
    "fishing_rod": {
        "luck_of_the_sea": 1.00, "lure": 0.85,
        "mending": 0.95, "unbreaking": 0.90,
    },
    "mace": {
        "density": 1.00, "breach": 0.90, "wind_burst": 0.90,
        "mending": 0.95, "unbreaking": 0.90,
    },
}

NEGATIVE_ENCHANTMENTS = {"curse_of_binding", "curse_of_vanishing", "binding", "vanishing"}


RECIPES = {
    "diamond_sword": {"diamond": 2, "stick": 1},
    "diamond_axe": {"diamond": 3, "stick": 2},
    "diamond_pickaxe": {"diamond": 3, "stick": 2},
    "diamond_helmet": {"diamond": 5},
    "diamond_chestplate": {"diamond": 8},
    "diamond_leggings": {"diamond": 7},
    "diamond_boots": {"diamond": 4},
    "iron_sword": {"iron_ingot": 2, "stick": 1},
    "iron_axe": {"iron_ingot": 3, "stick": 2},
    "iron_pickaxe": {"iron_ingot": 3, "stick": 2},
}

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {API_TOKEN}",
    "Accept": "application/json",
    "User-Agent": "BagelSMP-Market-Scanner/3.0",
})

seen_alerts = {}


def num(value, default=None):
    if isinstance(value, bool):
        return default
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").replace("$", "").strip()
            if not value:
                return default
        return float(value)
    except (TypeError, ValueError):
        return default


def text(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def first_value(obj, keys):
    if not isinstance(obj, dict):
        return None
    lower = {str(k).lower(): v for k, v in obj.items()}
    for key in keys:
        if key.lower() in lower:
            return lower[key.lower()]
    return None


def extract_rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "items", "results", "auctions", "orders", "prices", "listings"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        if data and all(isinstance(v, dict) for v in data.values()):
            rows = []
            for key, value in data.items():
                row = dict(value)
                row.setdefault("item", key)
                rows.append(row)
            return rows
    return []


def get_json(endpoint):
    url = f"{BASE_URL}/{endpoint}"
    last_error = None

    for attempt in range(4):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                return response.json()

            if response.status_code in (429, 500, 502, 503, 504):
                retry_after = num(response.headers.get("Retry-After"), 2)
                time.sleep(min(max(retry_after, 1), 20))
                continue

            body = response.text[:1000].replace("\n", " ")
            print(f"{endpoint}: HTTP {response.status_code}: {body}")
            return None

        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            time.sleep(2 ** attempt)

    print(f"{endpoint}: request failed: {last_error}")
    return None


def normalize_name(row):
    value = first_value(row, [
        "item", "item_name", "name", "material", "product", "type", "id"
    ])
    return text(value).lower().replace("minecraft:", "").strip()


def canonical_enchant_name(value):
    value = text(value).lower().replace("minecraft:", "")
    value = value.replace(" ", "_").replace("-", "_")
    aliases = {
        "sharpness": "sharpness", "unbreaking": "unbreaking",
        "mending": "mending", "efficiency": "efficiency",
        "fortune": "fortune", "silk_touch": "silk_touch",
        "protection": "protection", "feather_falling": "feather_falling",
        "depth_strider": "depth_strider", "aqua_affinity": "aqua_affinity",
        "fire_protection": "fire_protection", "blast_protection": "blast_protection",
        "projectile_protection": "projectile_protection", "respiration": "respiration",
        "looting": "looting", "fire_aspect": "fire_aspect", "knockback": "knockback",
        "smite": "smite", "bane_of_arthropods": "bane_of_arthropods",
        "power": "power", "punch": "punch", "flame": "flame", "infinity": "infinity",
        "quick_charge": "quick_charge", "piercing": "piercing", "multishot": "multishot",
        "loyalty": "loyalty", "riptide": "riptide", "channeling": "channeling",
        "impaling": "impaling", "luck_of_the_sea": "luck_of_the_sea", "lure": "lure",
        "thorns": "thorns", "frost_walker": "frost_walker", "soul_speed": "soul_speed",
        "swift_sneak": "swift_sneak", "wind_burst": "wind_burst", "density": "density",
        "breach": "breach", "curse_of_binding": "curse_of_binding",
        "curse_of_vanishing": "curse_of_vanishing", "binding": "curse_of_binding",
        "vanishing": "curse_of_vanishing",
    }
    return aliases.get(value, value)


def extract_enchantments(row):
    """Extract enchantments from common API/NBT/metadata shapes.

    Returns a canonical tuple like (("efficiency", 5), ("mending", 1)).
    Unknown enchantment names are preserved rather than discarded.
    """
    found = {}

    def add(name, level=1):
        name = canonical_enchant_name(name)
        if not name:
            return
        lvl = num(level, 1) or 1
        found[name] = max(found.get(name, 0), int(lvl))

    def parse(obj, depth=0, allow_name=False):
        if depth > 5 or obj is None:
            return
        if isinstance(obj, list):
            for x in obj:
                parse(x, depth + 1, allow_name=True)
            return
        if isinstance(obj, str):
            for part in obj.replace(";", ",").split(","):
                part = part.strip()
                if not part:
                    continue
                bits = part.rsplit(" ", 1)
                if len(bits) == 2 and bits[1].isdigit():
                    add(bits[0], int(bits[1]))
                else:
                    add(part, 1)
            return
        if not isinstance(obj, dict):
            return

        # Only treat name/id as an enchantment when we are inside an
        # enchantment object. Never interpret the item's own name as an enchant.
        if allow_name:
            name = first_value(obj, ["enchantment", "ench", "name", "id", "key", "type"])
            level = first_value(obj, ["level", "lvl", "amplifier", "value"])
            if name is not None and not isinstance(name, (dict, list)):
                add(name, level if level is not None else 1)
        else:
            name = first_value(obj, ["enchantment", "ench"])
            level = first_value(obj, ["level", "lvl", "amplifier", "value"])
            if name is not None and not isinstance(name, (dict, list)):
                add(name, level if level is not None else 1)

        for key in ("enchantments", "enchants", "enchantment_data", "enchantment_data_list", "stored_enchantments", "storedEnchants", "effects"):
            value = first_value(obj, [key])
            if value is not None:
                if isinstance(value, dict):
                    # Common compact form: {"efficiency": 5, "fortune": 3}.
                    for k, v in value.items():
                        if isinstance(v, (int, float, str)) and not isinstance(v, bool):
                            add(k, v)
                        else:
                            parse(v, depth + 1, allow_name=True)
                else:
                    parse(value, depth + 1, allow_name=True)

        for key in ("metadata", "meta", "item_meta", "nbt", "tag", "item", "data"):
            value = first_value(obj, [key])
            if isinstance(value, (dict, list)):
                parse(value, depth + 1, allow_name=False)

    parse(row)
    return tuple(sorted(found.items()))

def item_category(item):
    name = item.lower()
    if any(x in name for x in ("helmet", "chestplate", "leggings", "boots", "armor")):
        return "armor"
    if "bow" in name and "crossbow" not in name:
        return "bow"
    if "crossbow" in name:
        return "crossbow"
    if "trident" in name:
        return "trident"
    if "fishing_rod" in name or "fishing rod" in name:
        return "fishing_rod"
    if "mace" in name:
        return "mace"
    if any(x in name for x in ("sword", "axe")):
        return "weapons"
    if any(x in name for x in ("pickaxe", "shovel", "hoe")):
        return "tools"
    return "tools"


def enchantment_demand_score(item, enchantments):
    if not enchantments:
        return 0.0
    profile = ENCHANTMENT_DEMAND.get(item_category(item), {})
    positive = 0.0
    negative = 0.0
    for name, level in enchantments:
        weight = profile.get(name, 0.35)
        if name in NEGATIVE_ENCHANTMENTS:
            negative += 1.0
        else:
            # Higher levels are generally more desirable, but cap their effect
            # so a single level cannot dominate the whole score.
            positive += weight * min(level, 5) / 5.0
    return max(0.0, positive - negative)


def enchantment_text(enchantments):
    if not enchantments:
        return "None"
    def roman(n):
        vals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
        out = ""
        for value, symbol in vals:
            while n >= value:
                out += symbol
                n -= value
        return out
    return ", ".join(f"{name.replace('_', ' ').title()} {roman(level)}" for name, level in enchantments)


def comparable_key(row):
    # Enchanted equipment is compared only with the same enchantment set.
    # Non-equipment items simply compare by item name.
    enchants = row.get("enchantments", ())
    return (row["item"], enchants)


def extract_durability(row):
    """Return durability percent when the API exposes enough information.

    Supports common Minecraft/API representations: durability/max_durability,
    current/max durability, or damage/max_damage. If the API does not expose
    durability, return None rather than guessing.
    """
    if not isinstance(row, dict):
        return None

    def walk(obj, depth=0):
        if depth > 3 or not isinstance(obj, dict):
            return None

        # Direct percentage fields.
        for key in ("durability_percent", "durability_percentage", "durability_pct"):
            v = num(first_value(obj, [key]))
            if v is not None:
                return max(0.0, min(100.0, v if v <= 100 else v / 100.0))

        current = num(first_value(obj, [
            "durability", "current_durability", "remaining_durability",
            "durability_remaining", "current"
        ]))
        maximum = num(first_value(obj, [
            "max_durability", "maximum_durability", "durability_max",
            "max_damage", "maximum_damage"
        ]))
        if current is not None and maximum is not None and maximum > 0:
            # If the API gives damage rather than remaining durability, use
            # damage/max_damage below. Otherwise current/max is the natural form.
            if first_value(obj, ["damage", "current_damage", "item_damage"]) is not None:
                return max(0.0, min(100.0, 100.0 * (1.0 - current / maximum)))
            return max(0.0, min(100.0, 100.0 * current / maximum))

        damage = num(first_value(obj, ["damage", "current_damage", "item_damage"]))
        max_damage = num(first_value(obj, ["max_damage", "maximum_damage", "durability_max"]))
        if damage is not None and max_damage is not None and max_damage > 0:
            return max(0.0, min(100.0, 100.0 * (1.0 - damage / max_damage)))

        for value in obj.values():
            if isinstance(value, dict):
                found = walk(value, depth + 1)
                if found is not None:
                    return found
        return None

    return walk(row)


def durability_ok(row):
    """Reject known-low-durability equipment; keep items with no durability data."""
    durability = row.get("durability_percent")
    return durability is None or durability >= MIN_DURABILITY_PERCENT


def normalize_auction(row):
    item = normalize_name(row)
    raw_price = num(first_value(row, [
        "price", "total_price", "listing_price", "amount"
    ]))
    qty = num(first_value(row, [
        "quantity", "qty", "amount_available", "stock", "count"
    ]), 1)
    seller = text(first_value(row, [
        "seller", "username", "owner", "player", "seller_name"
    ]), "Unknown")
    durability_percent = extract_durability(row)
    enchantments = extract_enchantments(row)

    if not item or raw_price is None or raw_price <= 0 or qty is None or qty <= 0:
        return None

    explicit_unit = num(first_value(row, [
        "unit_price", "price_per_unit", "per_unit"
    ]))

    unit = explicit_unit if explicit_unit is not None else raw_price / qty

    return {
        "item": item,
        "total": raw_price,
        "qty": qty,
        "unit": unit,
        "seller": seller,
        "durability_percent": durability_percent,
        "enchantments": enchantments,
        "demand_score": enchantment_demand_score(item, enchantments),
    }


def normalize_order(row):
    item = normalize_name(row)
    raw_price = num(first_value(row, [
        "unit_price", "price_per_unit", "per_unit", "price"
    ]))
    qty = num(first_value(row, [
        "quantity", "qty", "amount_available", "stock", "count"
    ]), 1)
    seller = text(first_value(row, [
        "seller", "username", "owner", "player", "seller_name"
    ]), "Unknown")
    enchantments = extract_enchantments(row)

    if not item or raw_price is None or raw_price <= 0 or qty is None or qty <= 0:
        return None

    unit = raw_price

    return {
        "item": item,
        "total": unit * qty,
        "qty": qty,
        "unit": unit,
        "seller": seller,
        "enchantments": enchantments,
        "demand_score": enchantment_demand_score(item, enchantments),
    }


def build_auction_book(auctions):
    book = {}
    for raw in extract_rows(auctions):
        row = normalize_auction(raw)
        if row and durability_ok(row):
            book.setdefault(row["item"], []).append(row)

    for item in book:
        book[item].sort(key=lambda x: x["unit"])

    return book


def build_orders(orders):
    result = {}
    for raw in extract_rows(orders):
        row = normalize_order(raw)
        if row:
            result.setdefault(row["item"], []).append(row)

    for item in result:
        result[item].sort(key=lambda x: x["unit"])

    return result


def realistic_sell_price(listings):
    details = price_sample_details(listings)
    return details["target"] if details else None


def price_sample_details(listings, target_listing=None):
    """Return a conservative sell price from comparable listings.

    For enchanted gear, only listings with the same enchantment set are
    comparable. Known-low durability listings have already been removed.
    Exactly five listings are required. Prices are normalized per item.
    """
    if target_listing is not None:
        key = comparable_key(target_listing)
        comparable = [x for x in listings if comparable_key(x) == key]
    else:
        comparable = listings

    if len(comparable) < PRICE_SAMPLE_SIZE:
        return None

    sample = sorted(comparable, key=lambda x: x["unit"])[:PRICE_SAMPLE_SIZE]
    average_unit_price = statistics.mean(x["unit"] for x in sample)
    target = average_unit_price * (1.0 - SELL_UNDERCUT_RATE)
    return {
        "sample": sample,
        "average": average_unit_price,
        "target": target,
        "comparable_count": len(comparable),
    }


def best_comparable_basis(listings, target_listing):
    return price_sample_details(listings, target_listing=target_listing)

def after_fee(price):
    return price * (1.0 - AH_FEE_RATE)


def make_opportunity(kind, item, buy_unit, qty, sell_unit, source, note, sell_basis=None):
    if buy_unit <= 0 or sell_unit <= 0 or qty <= 0:
        return None

    buy_total = buy_unit * qty
    revenue = after_fee(sell_unit) * qty
    profit = revenue - buy_total
    roi = profit / buy_total if buy_total else 0

    if profit < MIN_PROFIT or roi < MIN_ROI:
        return None

    return {
        "kind": kind,
        "item": item,
        "buy_unit": buy_unit,
        "qty": int(qty),
        "buy_total": buy_total,
        "sell_unit": sell_unit,
        "revenue": revenue,
        "profit": profit,
        "roi": roi,
        "source": source,
        "note": note,
        "sell_basis": sell_basis or {},
        "enchantments": (),
        "demand_score": 0.0,
    }


def scan_order_to_ah(orders, auctions):
    ideas = []
    for item, order_list in orders.items():
        ah = auctions.get(item, [])
        for order in order_list[:3]:
            # Match an order to the same enchantment set when possible.
            basis = price_sample_details(ah, target_listing=order)
            if basis is None:
                # For orders without enchantment metadata, fall back to the
                # base item market only. This avoids pretending enchanted and
                # unenchanted gear are equivalent.
                if order.get("enchantments"):
                    continue
                basis = price_sample_details(ah)
            if basis is None:
                continue

            exit_price = basis["target"]
            qty = order["qty"]
            idea = make_opportunity(
                "ORDER -> AH",
                item,
                order["unit"],
                qty,
                exit_price,
                order["seller"],
                f"buy up to {int(qty)} available item(s) from {order['seller']}",
                sell_basis=basis,
            )
            if idea:
                idea["enchantments"] = order.get("enchantments", ())
                idea["demand_score"] = enchantment_demand_score(item, idea["enchantments"])
                ideas.append(idea)
    return ideas

def scan_ah_flip(auctions):
    ideas = []
    for item, listings in auctions.items():
        if len(listings) < PRICE_SAMPLE_SIZE:
            continue

        listings = sorted(listings, key=lambda x: x["unit"])
        cheapest = listings[0]
        basis = best_comparable_basis(listings, cheapest)
        if basis is None:
            continue

        exit_price = basis["target"]
        if exit_price <= cheapest["unit"]:
            continue

        idea = make_opportunity(
            "AH -> AH",
            item,
            cheapest["unit"],
            cheapest["qty"],
            exit_price,
            cheapest["seller"],
            "buy the cheapest full listing and relist its actual quantity" + (
                f"; durability {cheapest['durability_percent']:.0f}%"
                if cheapest.get("durability_percent") is not None else ""
            ),
            sell_basis=basis,
        )
        if idea:
            idea["enchantments"] = cheapest.get("enchantments", ())
            idea["demand_score"] = cheapest.get("demand_score", 0.0)
            ideas.append(idea)
    return ideas

def scan_crafting(orders, auctions, prices):
    material_prices = {}

    for item in set(list(orders.keys()) + list(auctions.keys())):
        candidates = []
        if orders.get(item):
            candidates.append(orders[item][0]["unit"])
        if auctions.get(item):
            candidates.append(auctions[item][0]["unit"])
        if candidates:
            material_prices[item] = min(candidates)

    for key, value in (prices.items() if isinstance(prices, dict) else []):
        if key not in material_prices:
            p = num(value)
            if p is not None and p > 0:
                material_prices[str(key).lower()] = p

    ideas = []

    for product, recipe in RECIPES.items():
        if product not in auctions:
            continue

        basis = price_sample_details(auctions[product])
        if basis is None:
            continue

        cost = 0
        possible = True

        for mat, count in recipe.items():
            price = material_prices.get(mat)
            if price is None:
                possible = False
                break
            cost += price * count

        if not possible:
            continue

        sell = basis["target"]
        idea = make_opportunity(
            "CRAFT",
            product,
            cost,
            1,
            sell,
            "market materials",
            "buy the cheapest materials, craft one item, then relist",
            sell_basis=basis,
        )

        if idea:
            ideas.append(idea)

    return ideas


def scan_budget(ideas):
    if BUDGET <= 0:
        return ideas

    result = []

    for idea in ideas:
        # Do not reduce the quantity of an AH listing to fit the budget.
        # That would create an impossible recommendation if the listing is
        # sold only as a complete stack/lot. Instead, reject the opportunity
        # unless the complete purchase fits the budget.
        if idea["buy_total"] > BUDGET:
            continue

        result.append(idea)

    return result


def dedupe_and_rank(ideas):
    unique = {}

    for idea in ideas:
        key = (
            idea["kind"],
            idea["item"],
            round(idea["buy_unit"], 4),
            round(idea["sell_unit"], 4),
            idea["qty"],
        )

        old = unique.get(key)

        if old is None or idea["profit"] > old["profit"]:
            unique[key] = idea

    ideas = list(unique.values())
    # Profit remains the primary ranking. Demand is only a tie-breaker so
    # desirable enchantments can surface before equally-profitable weak ones.
    ideas.sort(key=lambda x: (x["profit"], x["roi"], x.get("demand_score", 0.0)), reverse=True)
    return ideas[:MAX_ALERTS]


def money(value):
    if abs(value - round(value)) < 0.01:
        return f"{int(round(value)):,}"
    return f"{value:,.2f}"


def format_alert(ideas):
    lines = [
        "BAGEL SMP 鈥� DEAL FOUND",
        "",
        f"Your budget: {money(BUDGET) if BUDGET > 0 else 'No limit'} coins",
        "Sell prices use the 5 cheapest active listings by price per item, averaged and reduced by 5%.",
        "",
    ]

    for i, x in enumerate(ideas, 1):
        basis = x.get("sell_basis", {})
        sample = basis.get("sample", [])
        average = basis.get("average")

        enchantments = x.get("enchantments", ())
        lines.extend([
            f"DEAL {i}: {x['item'].upper()}",
            f"METHOD: {x['kind']}",
        ])
        if enchantments:
            lines.extend([
                f"ENCHANTMENTS: {enchantment_text(enchantments)}",
                f"ENCHANTMENT DEMAND SCORE: {x.get('demand_score', 0.0):.2f} (higher means the enchantments are generally more useful)",
            ])
        lines.extend([
            "",
            f"STEP 1 鈥� BUY: {x['qty']} item(s) at {money(x['buy_unit'])} coins each.",
            f"TOTAL TO SPEND: {money(x['buy_total'])} coins.",
            f"BUY FROM: {x['source']}.",
            "",
            f"STEP 2 鈥� SELL: List them for about {money(x['sell_unit'])} coins each.",
            f"ESTIMATED SALES REVENUE: {money(x['revenue'])} coins.",
            "",
            f"ESTIMATED PROFIT: {money(x['profit'])} coins.",
            f"RETURN ON MONEY SPENT: {x['roi'] * 100:.1f}%.",
        ])

        if sample and average is not None:
            sample_text = ", ".join(
                f"{int(round(s['qty']))} for {money(s['total'])} ({money(s['unit'])}/each)"
                for s in sample
            )
            lines.extend([
                "",
                f"PRICE CHECK: The 5 cheapest listings were: {sample_text}.",
                f"AVERAGE OF THOSE 5: {money(average)} coins each.",
                f"COMPARABLE LISTINGS FOUND: {basis.get('comparable_count', len(sample))}.",
                "YOUR SELL PRICE: 5% below that average.",
            ])

        lines.extend([
            "",
            f"WHAT TO DO: {x['note'].capitalize()}.",
            "",
            "IMPORTANT: This is a market-based estimate, not a guaranteed sale.",
            "Check the live market before buying because another player can change listings.",
            "",
            "------------------------------",
            "",
        ])

    return "\n".join(lines)


def send_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("Discord webhook not configured.")
        return

    chunks = [message[i:i + 1900] for i in range(0, len(message), 1900)]

    for chunk in chunks:
        try:
            response = requests.post(
                DISCORD_WEBHOOK_URL,
                json={"content": chunk},
                timeout=15,
            )
            if response.status_code not in (200, 204):
                print(f"Discord HTTP {response.status_code}: {response.text[:300]}")
        except requests.RequestException as exc:
            print(f"Discord error: {exc}")


def fingerprint(ideas):
    raw = json.dumps(ideas, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def run_once():
    print("Starting Bagel SMP market scan...")

    prices_raw = get_json("prices")
    orders_raw = get_json("orders")
    auctions_raw = get_json("auctions")

    if prices_raw is None or orders_raw is None or auctions_raw is None:
        send_discord(
            "BAGEL SMP 鈥� SCANNER ERROR\n"
            "The market could not be checked completely this time. "
            "No buying decision should be made from this scan. "
            "Check the GitHub Actions log for the HTTP status."
        )
        return

    auctions = build_auction_book(auctions_raw)
    orders = build_orders(orders_raw)

    raw_prices = prices_raw if isinstance(prices_raw, dict) else {}
    ideas = []
    ideas.extend(scan_order_to_ah(orders, auctions))
    ideas.extend(scan_ah_flip(auctions))
    ideas.extend(scan_crafting(orders, auctions, raw_prices))
    ideas = scan_budget(ideas)
    ideas = dedupe_and_rank(ideas)

    print(
        f"Market data: {len(auctions)} auction items, "
        f"{len(orders)} order items, {len(ideas)} opportunities."
    )

    if ideas:
        fp = fingerprint(ideas)
        previous = seen_alerts.get("market")

        if fp != previous:
            send_discord(format_alert(ideas))
            seen_alerts["market"] = fp
        else:
            print("Same opportunities as previous scan; Discord alert suppressed.")

    elif HEARTBEAT:
        send_discord(
            "BAGEL SMP 鈥� NO DEAL FOUND\n"
            "I checked the market successfully. There is currently no deal "
            f"that meets both requirements: at least {MIN_ROI * 100:.1f}% "
            f"return and at least {money(MIN_PROFIT)} coins profit.\n\n"
            f"Your budget: {money(BUDGET) if BUDGET > 0 else 'No limit'} coins.\n"
            "I will check again on the next scan."
        )


def main():
    if not API_TOKEN:
        print("ERROR: BAGEL_API_TOKEN is missing.")
        sys.exit(1)

    print("Bagel SMP scanner starting.")
    print(f"Scan interval: {SCAN_SECONDS} seconds")
    print(f"Worker duration: {MAX_DURATION_SECONDS} seconds")
    print(f"Minimum ROI: {MIN_ROI * 100:.1f}%")
    print(f"Minimum profit: {MIN_PROFIT}")
    print(f"AH fee rate: {AH_FEE_RATE * 100:.2f}%")
    print(f"Sell-price sample: {PRICE_SAMPLE_SIZE} cheapest listings, then 5% under average")
    budget_text = money(BUDGET) if BUDGET > 0 else "No limit"
    print(f"Budget: {budget_text} coins")

    if "--loop" not in sys.argv:
        run_once()
        return

    started = time.time()

    while time.time() - started < MAX_DURATION_SECONDS:
        cycle_started = time.time()

        try:
            run_once()
        except Exception as exc:
            print(f"Unexpected scan error: {exc}")
            send_discord(
                "BAGEL SMP 鈥� SCANNER ERROR\n"
                f"The scanner hit an unexpected error: {type(exc).__name__}. "
                "It will try again on the next scan."
            )

        elapsed = time.time() - cycle_started
        sleep_for = max(5, SCAN_SECONDS - int(elapsed))
        print(f"Next scan in {sleep_for} seconds.")
        time.sleep(sleep_for)

    print("Worker duration reached. Exiting cleanly.")


if __name__ == "__main__":
    main()
