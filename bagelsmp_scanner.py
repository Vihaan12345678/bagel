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
SELL_MULTIPLIER = float(os.getenv("SELL_MULTIPLIER", "1.0"))

# A sell price is based on exactly the five cheapest active AH listings
# for the item, measured by price per item. We then undercut that average
# by 5% so the scanner does not assume we can sell at the market average.
PRICE_SAMPLE_SIZE = 5
SELL_UNDERCUT_RATE = 0.05
# Never treat a wildly higher AH asking price as a realistic exit when active
# player orders are dramatically lower. This is a sanity check, not a price source.
MAX_AH_TO_ORDER_PRICE_RATIO = float(os.getenv("MAX_AH_TO_ORDER_PRICE_RATIO", "1.50"))

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
    # Blocks / common conversion recipes
    "bamboo_block": {"bamboo": 9},
    "stripped_bamboo_block": {"bamboo_block": 1},
    "bone_block": {"bone_meal": 9},
    "dried_kelp_block": {"dried_kelp": 9},
    "coal_block": {"coal": 9},
    "iron_block": {"iron_ingot": 9},
    "gold_block": {"gold_ingot": 9},
    "diamond_block": {"diamond": 9},
    "emerald_block": {"emerald": 9},
    "redstone_block": {"redstone": 9},
    "lapis_block": {"lapis_lazuli": 9},
    "copper_block": {"copper_ingot": 9},
    "quartz_block": {"quartz": 4},
    "hay_block": {"wheat": 9},
    "slime_block": {"slime_ball": 9},
    "honey_block": {"honey_bottle": 4},
    "paper": {"sugar_cane": 3},
    "stick": {"oak_planks": 2},
    "torch": {"coal": 1, "stick": 1},
    "glass_pane": {"glass": 6},
    "ladder": {"stick": 7},
    "furnace": {"cobblestone": 8},
    "hopper": {"iron_ingot": 5, "chest": 1},
    "iron_bars": {"iron_ingot": 6},
    "rail": {"iron_ingot": 6, "stick": 1},
    "golden_rail": {"gold_ingot": 6, "stick": 1, "redstone": 1},
    "redstone_torch": {"redstone": 1, "stick": 1},
    "lever": {"cobblestone": 1, "stick": 1},
    "piston": {"oak_planks": 3, "cobblestone": 4, "iron_ingot": 1, "redstone": 1},
    "sticky_piston": {"piston": 1, "slime_ball": 1},
    "dispenser": {"cobblestone": 7, "bow": 1, "redstone": 1},
    "dropper": {"cobblestone": 7, "redstone": 1},
    "observer": {"cobblestone": 6, "redstone": 2, "quartz": 1},
    "tnt": {"gunpowder": 5, "sand": 4},
    "book": {"paper": 3, "leather": 1},
    "bookshelf": {"book": 3, "oak_planks": 6},
    "enchanting_table": {"book": 1, "diamond": 2, "obsidian": 4},
    "anvil": {"iron_block": 3, "iron_ingot": 4},
    "diamond_sword": {"diamond": 2, "stick": 1},
    "diamond_axe": {"diamond": 3, "stick": 2},
    "diamond_pickaxe": {"diamond": 3, "stick": 2},
    "diamond_shovel": {"diamond": 1, "stick": 2},
    "diamond_hoe": {"diamond": 2, "stick": 2},
    "diamond_helmet": {"diamond": 5},
    "diamond_chestplate": {"diamond": 8},
    "diamond_leggings": {"diamond": 7},
    "diamond_boots": {"diamond": 4},
    "iron_sword": {"iron_ingot": 2, "stick": 1},
    "iron_axe": {"iron_ingot": 3, "stick": 2},
    "iron_pickaxe": {"iron_ingot": 3, "stick": 2},
    "iron_shovel": {"iron_ingot": 1, "stick": 2},
    "iron_hoe": {"iron_ingot": 2, "stick": 2},
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
    """Normalize an active player order.

    IMPORTANT: Bagel orders are quoted PER ITEM. If an order wants 16 items
    at 1,200 coins each, the order value is 19,200 coins. Do NOT divide the
    order price by quantity. This is different from an AH listing, where the
    listing price is a total and must be divided by quantity.
    """
    item = normalize_name(row)
    qty = num(first_value(row, [
        "remaining_quantity", "remaining_qty", "remaining",
        "amount_remaining", "available_quantity", "available_qty",
        "quantity_available", "quantity", "qty", "amount", "count", "stock"
    ]), 1)
    if not item or qty is None or qty <= 0:
        return None

    explicit_unit = num(first_value(row, [
        "unit_price", "price_per_unit", "per_unit", "unitPrice", "price_each", "priceEach"
    ]))
    # On the Bagel order board, price is the amount paid for EACH item.
    generic_price = num(first_value(row, ["price", "price_each", "priceEach", "offer_price", "bid_price"]))

    if explicit_unit is not None and explicit_unit > 0:
        unit = explicit_unit
    elif generic_price is not None and generic_price > 0:
        unit = generic_price
    else:
        # Some APIs expose an order total instead of price_each. Only use an
        # explicitly named total here; never guess that a generic price is a total.
        total_price = num(first_value(row, ["total_price", "totalPrice", "order_total", "total_value"]))
        if total_price is None or total_price <= 0:
            return None
        unit = total_price / qty

    if unit <= 0:
        return None

    buyer = text(first_value(row, [
        "buyer", "buyer_name", "username", "owner", "player", "player_name", "seller", "seller_name"
    ]), "Unknown")
    enchantments = extract_enchantments(row)

    return {
        "item": item,
        "total": unit * qty,
        "qty": qty,
        "unit": unit,
        "seller": buyer,
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
        result[item].sort(key=lambda x: x["unit"], reverse=True)

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


def make_opportunity(kind, item, buy_unit, qty, sell_unit, source, note, sell_basis=None, extra=None):
    if buy_unit <= 0 or sell_unit <= 0 or qty <= 0:
        return None

    buy_total = buy_unit * qty
    revenue = after_fee(sell_unit) * qty
    profit = revenue - buy_total
    roi = profit / buy_total if buy_total else 0

    if profit < MIN_PROFIT or roi < MIN_ROI:
        return None

    result = {
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
    if extra:
        result.update(extra)
    return result


def first_available_json(endpoints):
    """Try optional endpoints without failing the whole scan if absent."""
    for endpoint in endpoints:
        data = get_json(endpoint)
        if data is not None:
            print(f"Optional endpoint found: {endpoint}")
            return data, endpoint
    return None, None


def parse_price_map(data, kind):
    """Parse Shop or /sell prices and normalize bundle/stack prices.

    If an API row says price=1200 and quantity=16, the returned value is
    75.0. Explicit unit-price fields are respected when present.
    """
    result = {}
    for raw in extract_rows(data):
        if not isinstance(raw, dict):
            continue
        item = normalize_name(raw)
        if not item:
            continue
        qty = num(first_value(raw, [
            "quantity", "qty", "amount_available", "stock", "count", "amount"
        ]), 1) or 1
        explicit_unit = num(first_value(raw, [
            "unit_price", "price_per_unit", "per_unit", "unitPrice"
        ]))
        total = num(first_value(raw, [
            "total_price", "totalPrice", "total", "bundle_price", "stack_price"
        ]))
        if kind == "shop":
            generic = num(first_value(raw, ["buy_price", "purchase_price", "shop_buy_price", "cost", "price", "buy"]))
        else:
            generic = num(first_value(raw, ["sell_price", "base_sell_price", "server_sell_price", "payout", "value", "price", "sell"]))
        if explicit_unit is not None and explicit_unit > 0:
            value = explicit_unit
        elif total is not None and total > 0:
            value = total / qty
        elif generic is not None and generic > 0:
            value = generic / qty if qty > 1 else generic
        else:
            continue
        result[item] = value

    if isinstance(data, dict):
        for key, raw in data.items():
            if isinstance(raw, (int, float, str)) and not isinstance(raw, bool):
                value = num(raw)
                if value is not None and value > 0:
                    result[str(key).lower().replace("minecraft:", "").replace(" ", "_")] = value
            elif isinstance(raw, dict):
                item = str(key).lower().replace("minecraft:", "").replace(" ", "_")
                qty = num(first_value(raw, ["quantity", "qty", "count", "amount"]), 1) or 1
                unit = num(first_value(raw, ["unit_price", "price_per_unit", "per_unit"]))
                value = unit
                if value is None:
                    value = num(first_value(raw, ["buy_price", "purchase_price", "shop_buy_price", "sell_price", "base_sell_price", "server_sell_price", "payout", "price", "value"]))
                    if value is not None and qty > 1:
                        value /= qty
                if value is not None and value > 0:
                    result[item] = value
    return result


def parse_market_price_map(data):
    """Extract a conservative per-item market/sold-price signal from prices data.

    This is deliberately separate from AH asking prices. A current AH listing
    is not evidence that somebody will actually pay that amount. The scanner
    uses this map as a sanity check for AH exits.
    """
    result = {}
    for raw in extract_rows(data):
        if not isinstance(raw, dict):
            continue
        item = normalize_name(raw)
        if not item:
            continue

        # Prefer fields that explicitly describe sold/market prices.
        value = num(first_value(raw, [
            "market_price", "marketPrice", "median_price", "medianPrice",
            "average_price", "averagePrice", "price_7d", "price7d",
            "seven_day_price", "price_24h", "price24h",
            "last_sale_price", "lastSalePrice", "sold_price", "soldPrice",
            "sale_price", "salePrice", "last_price", "lastPrice",
        ]))

        # If the API gives an explicit total + quantity, normalize it.
        if value is None:
            total = num(first_value(raw, ["total_price", "totalPrice", "total", "sales_total"]))
            qty = num(first_value(raw, ["quantity", "qty", "amount", "count"]), 1) or 1
            if total is not None and total > 0 and qty > 0:
                value = total / qty

        # Finally accept a generic price from the prices endpoint as a
        # per-item market value. Do NOT divide it merely because a quantity
        # field exists; prices are normally already quoted per item.
        if value is None:
            value = num(first_value(raw, ["price", "value"]))

        if value is not None and value > 0:
            result[item] = value

    if isinstance(data, dict):
        for key, raw in data.items():
            item = normalize_recipe_item(key)
            if not item or not isinstance(raw, (dict, int, float, str)) or isinstance(raw, bool):
                continue
            if isinstance(raw, dict):
                value = num(first_value(raw, [
                    "market_price", "marketPrice", "median_price", "medianPrice",
                    "average_price", "averagePrice", "price_7d", "price7d",
                    "seven_day_price", "price_24h", "price24h",
                    "last_sale_price", "lastSalePrice", "sold_price", "soldPrice",
                    "sale_price", "salePrice", "last_price", "lastPrice", "price", "value"
                ]))
                if value is not None and value > 0:
                    result[item] = value
            else:
                value = num(raw)
                if value is not None and value > 0:
                    result[item] = value
    return result


def normalize_recipe_item(value):
    return text(value).lower().replace("minecraft:", "").replace(" ", "_").strip()


def parse_recipes(data):
    """Parse common recipe API shapes and merge in fallback recipes."""
    recipes = {}
    for raw in extract_rows(data):
        if not isinstance(raw, dict):
            continue
        product = normalize_recipe_item(first_value(raw, ["output", "result", "product", "item", "item_name", "name", "id"]))
        ingredients = first_value(raw, ["ingredients", "ingredient", "materials", "components", "recipe", "inputs"])
        if not product or not ingredients:
            continue
        parsed = {}
        if isinstance(ingredients, dict):
            for key, value in ingredients.items():
                if isinstance(value, (int, float, str)) and not isinstance(value, bool):
                    qty = num(value)
                    if qty and qty > 0:
                        parsed[normalize_recipe_item(key)] = qty
                elif isinstance(value, dict):
                    name = normalize_recipe_item(first_value(value, ["item", "name", "id", "material"]))
                    qty = num(first_value(value, ["quantity", "count", "amount", "qty"]), 1)
                    if name and qty and qty > 0:
                        parsed[name] = qty
        elif isinstance(ingredients, list):
            for part in ingredients:
                if isinstance(part, dict):
                    name = normalize_recipe_item(first_value(part, ["item", "name", "id", "material"]))
                    qty = num(first_value(part, ["quantity", "count", "amount", "qty"]), 1)
                    if name and qty and qty > 0:
                        parsed[name] = qty
        if parsed:
            recipes[product] = parsed
    for product, recipe in RECIPES.items():
        recipes.setdefault(product, recipe)
    return recipes


def material_unit_prices(orders, auctions, shop, sell):
    """Find the cheapest usable source price for crafting materials."""
    result = {}
    for item in set(orders) | set(auctions) | set(shop) | set(sell):
        candidates = []
        if orders.get(item):
            # Buying from another player's order is NOT a supply source, so
            # orders are intentionally excluded from material acquisition.
            pass
        if auctions.get(item):
            candidates.append(auctions[item][0]["unit"])
        if item in shop:
            candidates.append(shop[item])
        if item in sell:
            # /sell is an exit, not a way to acquire the material. Do not use
            # it as an input cost.
            pass
        if candidates:
            result[item] = min(candidates)
    return result


def scan_shop_to_order(shop, orders):
    ideas = []
    for item, buy_unit in shop.items():
        for order in orders.get(item, [])[:3]:
            qty = order["qty"]
            idea = make_opportunity(
                "SHOP -> ORDER", item, buy_unit, qty, order["unit"],
                "Server Shop",
                f"buy {int(qty)} from the server shop and fulfill {order['seller']}'s active order"
            )
            if idea:
                ideas.append(idea)
    return ideas


def scan_sell_to_order(sell, orders):
    ideas = []
    for item, payout in sell.items():
        for order in orders.get(item, [])[:3]:
            if order["unit"] <= payout:
                continue
            idea = make_opportunity(
                "/SELL -> ORDER", item, payout, order["qty"], order["unit"],
                "Your /sell payout",
                f"obtain {int(order['qty'])} item(s), then fulfill {order['seller']}'s active order"
            )
            if idea:
                ideas.append(idea)
    return ideas


def scan_shop_to_sell(shop, sell):
    ideas = []
    for item, buy_unit in shop.items():
        payout = sell.get(item)
        if payout is None or payout <= buy_unit:
            continue
        qty = max(1, int(BUDGET // buy_unit)) if BUDGET > 0 else 1
        idea = make_opportunity(
            "SHOP -> /SELL", item, buy_unit, qty, payout,
            "Server Shop", "buy from the server shop, then use /sell"
        )
        if idea:
            ideas.append(idea)
    return ideas


def scan_ah_to_order(auctions, orders):
    ideas = []
    for item, listings in auctions.items():
        for listing in listings[:3]:
            for order in orders.get(item, [])[:3]:
                if order["unit"] <= listing["unit"]:
                    continue
                if listing.get("enchantments") != order.get("enchantments") and (listing.get("enchantments") or order.get("enchantments")):
                    continue
                # AH listing is treated as indivisible. Never invent a partial
                # purchase when a listing is a 16-item lot.
                if order["qty"] < listing["qty"]:
                    continue
                idea = make_opportunity(
                    "AH -> ORDER", item, listing["unit"], listing["qty"],
                    order["unit"], listing["seller"],
                    f"buy the full {int(listing['qty'])}-item AH listing and fulfill {order['seller']}'s order"
                )
                if idea:
                    idea["enchantments"] = listing.get("enchantments", ())
                    idea["demand_score"] = listing.get("demand_score", 0.0)
                    ideas.append(idea)
    return ideas


def recursive_material_plan(product, recipe_map, direct_prices, memo=None, stack=None):
    """Return the cheapest known cost and an action plan for one crafted item.

    Direct materials are acquired from Shop/AH when available. If a material
    has its own recipe, the scanner can recursively craft that intermediate.
    This lets recipes chain instead of stopping at the first crafted ingredient.
    """
    memo = memo or {}
    stack = stack or set()
    product = normalize_recipe_item(product)
    if product in memo:
        return memo[product]
    if product in stack:
        return None
    stack = set(stack)
    stack.add(product)

    if product in direct_prices:
        source, price = direct_prices[product]
        result = {
            "cost": price,
            "plan": [(source.upper(), product, 1, price)],
        }
        memo[product] = result
        return result

    recipe = recipe_map.get(product)
    if not recipe:
        return None

    total = 0.0
    plan = []
    for material, count in recipe.items():
        child = recursive_material_plan(material, recipe_map, direct_prices, memo, stack)
        if child is None:
            return None
        total += child["cost"] * count
        for source, name, qty, unit in child["plan"]:
            plan.append((source, name, qty * count, unit))

    result = {"cost": total, "plan": plan}
    memo[product] = result
    return result


def format_material_plan(plan):
    merged = {}
    for source, item, qty, unit in plan:
        key = (source, item, round(unit, 8))
        merged[key] = merged.get(key, 0) + qty
    lines = []
    for (source, item, unit), qty in sorted(merged.items()):
        if source == "CRAFT":
            verb = "CRAFT"
        elif source == "SHOP":
            verb = "BUY FROM SHOP"
        elif source == "AH":
            verb = "BUY FROM AH"
        else:
            verb = source
        lines.append(f"{verb}: {qty:g}x {item} at {money(unit)} each")
    return lines


def scan_crafting(recipes, orders, auctions, shop, sell, market_prices):
    ideas = []
    direct_prices = {}
    for item, listings in auctions.items():
        if listings:
            direct_prices[item] = ("AH", listings[0]["unit"])
    for item, price in shop.items():
        # Shop is normally the cleanest direct acquisition source when cheaper.
        if item not in direct_prices or price < direct_prices[item][1]:
            direct_prices[item] = ("SHOP", price)

    memo = {}
    for product, recipe in recipes.items():
        order = orders.get(product, [None])[0]
        ah_basis = price_sample_details(auctions.get(product, [])) if auctions.get(product) else None
        market_price = market_prices.get(product)
        exits = []
        if order:
            exits.append(("ORDER", order["unit"], int(order["qty"]), f"craft {product.replace('_', ' ')} yourself, then fulfill {order['seller']}'s active order"))
        if ah_basis and market_price is not None and market_price > 0:
            # AH asking prices are not treated as proof of demand. Cap the
            # exit using the market/sold-price signal and reject it if an
            # active order is dramatically lower.
            ah_exit = min(ah_basis["target"], market_price * 1.05)
            best_order = order["unit"] if order else None
            if best_order is None or ah_exit <= best_order * MAX_AH_TO_ORDER_PRICE_RATIO:
                exits.append(("AH", ah_exit, None, f"craft {product.replace('_', ' ')} yourself, then list it on AH; exit price is supported by market/sold data"))
        if product in sell:
            exits.append(("/SELL", sell[product], None, f"craft {product.replace('_', ' ')} yourself, then use /sell"))

        if not exits:
            continue

        plan = recursive_material_plan(product, recipes, direct_prices, memo={})
        if plan is None or plan["cost"] <= 0:
            continue

        for exit_type, exit_price, order_qty, note in exits:
            if exit_price <= plan["cost"]:
                continue
            if exit_type == "ORDER":
                qty = order_qty
            elif BUDGET > 0:
                qty = int(BUDGET // plan["cost"])
            else:
                qty = 1
            if qty <= 0:
                continue

            full_plan = [(source, item, item_qty * qty, unit) for source, item, item_qty, unit in plan["plan"]]
            idea = make_opportunity(
                f"CRAFT -> {exit_type}", product, plan["cost"], qty, exit_price,
                "Recipe materials", note,
                sell_basis=ah_basis if exit_type == "AH" else None,
                extra={
                    "recipe": recipe,
                    "recipe_breakdown": format_material_plan(full_plan),
                    "action_plan": full_plan,
                    "craft_required": True,
                }
            )
            if idea:
                ideas.append(idea)
    return ideas


def scan_order_to_ah(orders, auctions):
    """Disabled intentionally. An active Order is a BUYER, not a source.

    The old scanner incorrectly treated an order price as a price we could
    buy from, producing nonsense alerts such as "buy 300,000 bamboo at 0.00".
    Use SHOP -> ORDER, AH -> ORDER, /SELL -> ORDER, or CRAFT -> ORDER instead.
    """
    return []


def scan_ah_flip(auctions, market_prices, shop=None):
    """Find AH -> AH flips only when sold/market data supports the exit.

    Active listings alone are not enough. A seller can list an item at an
    absurd price and nobody may buy it. We therefore require a market/sold
    price signal from the prices endpoint and cap the proposed exit using it.
    """
    ideas = []
    for item, listings in auctions.items():
        if len(listings) < PRICE_SAMPLE_SIZE:
            continue

        market_price = market_prices.get(item)
        if market_price is None or market_price <= 0:
            # No sold/market evidence = no AH -> AH alert.
            continue

        listings = sorted(listings, key=lambda x: x["unit"])
        cheapest = listings[0]
        basis = best_comparable_basis(listings, cheapest)
        if basis is None:
            continue

        # Never assume we can sell above the proven market price merely
        # because current asking prices are high. Allow a small 5% cushion.
        exit_price = min(basis["target"], market_price * 1.05)

        # If the server shop sells this exact item, that shop price is a hard
        # ceiling for an AH resale assumption. A buyer can always obtain the
        # item from the server shop, so a wildly higher AH asking price is not
        # evidence that a player will pay it.
        shop_price = (shop or {}).get(item)
        if shop_price is not None and shop_price > 0:
            exit_price = min(exit_price, shop_price)
        if exit_price <= cheapest["unit"]:
            continue

        idea = make_opportunity(
            "AH -> AH",
            item,
            cheapest["unit"],
            cheapest["qty"],
            exit_price,
            cheapest["seller"],
            "buy the cheapest full listing and relist its actual quantity; the sell price is capped by recent/market-price evidence",
            sell_basis=basis,
            extra={
                "market_price": market_price,
                "market_supported_sell": True,
                "shop_price": shop_price,
            },
        )
        if idea:
            idea["enchantments"] = cheapest.get("enchantments", ())
            idea["demand_score"] = cheapest.get("demand_score", 0.0)
            ideas.append(idea)
    return ideas


def filter_unrealistic_ah_exits(ideas, orders, market_prices, shop):
    """Reject AH exits that lack buyer/sold-price support."""
    filtered = []
    for idea in ideas:
        if idea.get("kind") not in {"AH -> AH", "CRAFT -> AH"}:
            filtered.append(idea)
            continue

        item = idea["item"]
        market_price = market_prices.get(item)
        item_orders = orders.get(item, [])
        best_order = max((o["unit"] for o in item_orders), default=0)

        # For AH exits, require either market/sold evidence or a real active
        # order. The current scanner only creates AH exits with market data,
        # but this second guard protects against malformed API data.
        if market_price is None or market_price <= 0:
            print(f"Rejected AH exit for {item}: no sold/market price evidence.")
            continue

        if idea["sell_unit"] > market_price * 1.05:
            print(
                f"Rejected unrealistic AH exit for {item}: "
                f"scanner AH={idea['sell_unit']:.2f}, market={market_price:.2f}."
            )
            continue

        if best_order > 0 and idea["sell_unit"] > best_order * MAX_AH_TO_ORDER_PRICE_RATIO:
            print(
                f"Rejected AH exit for {item}: "
                f"scanner AH={idea['sell_unit']:.2f}, best order={best_order:.2f}."
            )
            continue

        shop_price = shop.get(item)
        if shop_price is not None and shop_price > 0 and idea["sell_unit"] > shop_price + 1e-9:
            print(
                f"Rejected AH exit for {item}: "
                f"scanner AH={idea['sell_unit']:.2f} exceeds server shop price={shop_price:.2f}."
            )
            continue

        filtered.append(idea)
    return filtered


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


def format_alert(ideas, data_sources=None):
    lines = [
        "BAGEL SMP 鈥� DEAL FOUND",
        "",
        f"Your budget: {money(BUDGET) if BUDGET > 0 else 'No limit'} coins",
        "",
        "All prices below are normalized to coins per item.",
    ]
    if data_sources:
        lines.append(f"DATA SOURCES: {', '.join(data_sources)}")
    lines.extend([
        "",
        "The scanner compares Shop, /sell, Orders, AH, and crafting recipes when those data sources are available.",
        "",
    ])

    for i, x in enumerate(ideas, 1):
        lines.extend([f"DEAL {i}: {x['item'].upper()}", f"METHOD: {x['kind']}", ""])

        if x.get("recipe"):
            lines.extend([
                "ACTION PLAN:",
                "1. Get the required materials using the sources below.",
            ])
            lines.extend(f"   - {part}" for part in x.get("recipe_breakdown", []))
            lines.append("2. CRAFT the finished item yourself using the recipe.")
            lines.append(f"3. Cost to produce ONE finished item: {money(x['buy_unit'])} coins.")
            lines.append("")

        if x.get("craft_required"):
            lines.extend([
                f"STEP 1 鈥� GET MATERIALS: follow the material plan above.",
                f"TOTAL MATERIAL SPEND: {money(x['buy_total'])} coins.",
                "",
                f"STEP 2 鈥� CRAFT: make {x['qty']} {x['item'].replace('_', ' ')} yourself.",
                "",
                f"STEP 3 鈥� SELL: {x['qty']} item(s) for about {money(x['sell_unit'])} coins each.",
                f"ESTIMATED SALES REVENUE: {money(x['revenue'])} coins.",
            ])
        else:
            lines.extend([
                f"STEP 1 鈥� BUY: {x['qty']} item(s) at {money(x['buy_unit'])} coins each.",
                f"TOTAL TO SPEND: {money(x['buy_total'])} coins.",
                f"SOURCE: {x['source']}.",
                "",
                f"STEP 2 鈥� SELL: {x['qty']} item(s) for about {money(x['sell_unit'])} coins each.",
                f"ESTIMATED SALES REVENUE: {money(x['revenue'])} coins.",
            ])

        lines.extend([
            "",
            f"ESTIMATED PROFIT: {money(x['profit'])} coins.",
            f"RETURN ON MONEY SPENT: {x['roi'] * 100:.1f}%.",
        ])

        enchantments = x.get("enchantments", ())
        if enchantments:
            lines.extend([
                f"ENCHANTMENTS: {enchantment_text(enchantments)}",
                f"ENCHANTMENT DEMAND SCORE: {x.get('demand_score', 0.0):.2f}",
            ])

        basis = x.get("sell_basis", {})
        if x.get("market_price"):
            lines.extend([
                f"SOLD/MARKET PRICE CHECK: {money(x['market_price'])} coins each.",
                "The scanner will not use a much higher AH asking price as the expected sale price.",
            ])
        if x.get("shop_price"):
            lines.append(
                f"SERVER SHOP PRICE: {money(x['shop_price'])} coins each. "
                "This is the maximum AH resale price the scanner will assume when the item is available in the server shop."
            )

        if basis.get("sample"):
            sample_text = ", ".join(
                f"{int(round(s['qty']))} for {money(s['total'])} ({money(s['unit'])}/each)"
                for s in basis["sample"]
            )
            lines.extend([
                "",
                f"AH PRICE CHECK: {sample_text}.",
                f"AVERAGE OF THE 5 CHEAPEST COMPARABLE LISTINGS: {money(basis['average'])} coins each.",
                f"RAW 5-LISTING UNDERCUT PRICE: {money(basis['target'])} coins each.",
                f"ACTUAL SCANNER SELL PRICE USED: {money(x['sell_unit'])} coins each.",
                f"COMPARABLE LISTINGS FOUND: {basis.get('comparable_count', len(basis['sample']))}.",
            ])

        lines.extend([
            "",
            f"WHAT TO DO: {x['note'].capitalize()}.",
            "",
            "IMPORTANT: An AH asking price is not a guaranteed sale. Active Orders are checked separately.",
            "For crafting deals, the scanner does NOT assume mining/farming is free. It only counts materials with a known Shop/AH acquisition price.",
            "If you already own the materials, your real cash cost can be lower; if you must mine/farm them yourself, treat that as your time cost.",
            "Check the live market before buying because another player can change the price.",
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
            "The core market data could not be checked completely. "
            "No buying decision should be made from this scan. "
            "Check the GitHub Actions log for the HTTP status."
        )
        return

    # These endpoints are optional because the private API schema has not been
    # documented here. If an endpoint does not exist, the scanner continues
    # using the data sources that are actually available.
    shop_raw, shop_endpoint = first_available_json([
        "shop", "shops", "shop-prices", "shop_prices", "shop_prices/all"
    ])
    sell_raw, sell_endpoint = first_available_json([
        "sell", "sell-prices", "sell_prices", "sell_prices/all"
    ])
    recipes_raw, recipe_endpoint = first_available_json([
        "recipes", "crafting-recipes", "crafting_recipes", "crafting"
    ])

    auctions = build_auction_book(auctions_raw)
    orders = build_orders(orders_raw)
    raw_prices = prices_raw if isinstance(prices_raw, dict) else {}
    market_prices = parse_market_price_map(prices_raw)
    shop = parse_price_map(shop_raw, "shop") if shop_raw is not None else {}
    sell = parse_price_map(sell_raw, "sell") if sell_raw is not None else {}
    if sell and SELL_MULTIPLIER != 1.0:
        sell = {item: price * SELL_MULTIPLIER for item, price in sell.items()}
    recipes = parse_recipes(recipes_raw) if recipes_raw is not None else dict(RECIPES)

    ideas = []
    ideas.extend(scan_order_to_ah(orders, auctions))
    ideas.extend(scan_ah_flip(auctions, market_prices, shop))
    ideas.extend(scan_shop_to_order(shop, orders))
    ideas.extend(scan_sell_to_order(sell, orders))
    ideas.extend(scan_shop_to_sell(shop, sell))
    ideas.extend(scan_ah_to_order(auctions, orders))
    ideas.extend(scan_crafting(recipes, orders, auctions, shop, sell, market_prices))
    # Keep the existing crafting path for the original hard-coded recipes if
    # the optional endpoint returned a malformed/partial recipe map.
    ideas.extend(scan_crafting(RECIPES, orders, auctions, shop, sell, market_prices))

    ideas = filter_unrealistic_ah_exits(ideas, orders, market_prices, shop)
    ideas = scan_budget(ideas)
    ideas = dedupe_and_rank(ideas)

    sources = ["prices", "orders", "auctions"]
    if shop_endpoint:
        sources.append(shop_endpoint)
    if sell_endpoint:
        sources.append(sell_endpoint)
    if recipe_endpoint:
        sources.append(recipe_endpoint)

    print(
        f"Market data: {len(auctions)} auction items, {len(orders)} order items, "
        f"{len(shop)} shop prices, {len(sell)} /sell prices, "
        f"{len(recipes)} recipes, {len(market_prices)} sold/market prices, {len(ideas)} opportunities."
    )

    if ideas:
        fp = fingerprint(ideas)
        previous = seen_alerts.get("market")
        if fp != previous:
            send_discord(format_alert(ideas, sources))
            seen_alerts["market"] = fp
        else:
            print("Same opportunities as previous scan; Discord alert suppressed.")
    elif HEARTBEAT:
        send_discord(
            "BAGEL SMP 鈥� NO DEAL FOUND\n"
            "I checked the available market sources successfully. There is currently "
            "no deal that meets both the minimum profit and ROI requirements.\n\n"
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
    print(f"/sell multiplier: {SELL_MULTIPLIER:.3f}x")
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
