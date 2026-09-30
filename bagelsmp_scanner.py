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
BUDGET = float(os.getenv("BUDGET", "0"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
HEARTBEAT = os.getenv("HEARTBEAT", "1") == "1"

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
    "User-Agent": "BagelSMP-Market-Scanner/2.0",
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
        # Some APIs return an item->record dictionary.
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

    if not item or raw_price is None or raw_price <= 0 or qty is None or qty <= 0:
        return None

    explicit_unit = num(first_value(row, [
        "unit_price", "price_per_unit", "per_unit"
    ]))

    # For AH listings, the existing scanner's convention is that "price"
    # is the total listing price. If the API supplies an explicit unit
    # price, prefer it.
    unit = explicit_unit if explicit_unit is not None else raw_price / qty

    return {
        "item": item,
        "total": raw_price,
        "qty": qty,
        "unit": unit,
        "seller": seller,
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

    if not item or raw_price is None or raw_price <= 0 or qty is None or qty <= 0:
        return None

    # For sell orders, "price" is treated as a per-unit price, matching
    # the user's original scanner logic: price * quantity = total cost.
    unit = raw_price

    return {
        "item": item,
        "total": unit * qty,
        "qty": qty,
        "unit": unit,
        "seller": seller,
    }


def build_auction_book(auctions):
    book = {}
    for raw in extract_rows(auctions):
        row = normalize_auction(raw)
        if row:
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


def conservative_exit_price(listings):
    prices = [x["unit"] for x in listings[:7]]
    if not prices:
        return None

    if len(prices) == 1:
        return None

    if len(prices) == 2:
        return prices[1]

    return min(prices[1], statistics.median(prices[:7]))


def after_fee(price):
    return price * (1.0 - AH_FEE_RATE)


def make_opportunity(kind, item, buy_unit, qty, sell_unit, source, note):
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
    }


def scan_order_to_ah(orders, auctions):
    ideas = []
    for item, order_list in orders.items():
        ah = auctions.get(item, [])
        if not ah:
            continue

        exit_price = conservative_exit_price(ah)
        if exit_price is None:
            continue

        for order in order_list[:3]:
            qty = min(order["qty"], ah[0]["qty"])
            idea = make_opportunity(
                "ORDER -> AH",
                item,
                order["unit"],
                qty,
                exit_price,
                order["seller"],
                f"buy order stock from {order['seller']}",
            )
            if idea:
                ideas.append(idea)
    return ideas


def scan_ah_flip(auctions):
    ideas = []
    for item, listings in auctions.items():
        if len(listings) < 3:
            continue

        cheapest = listings[0]
        exit_price = conservative_exit_price(listings)

        if exit_price is None or exit_price <= cheapest["unit"]:
            continue

        idea = make_opportunity(
            "AH -> AH",
            item,
            cheapest["unit"],
            cheapest["qty"],
            exit_price,
            cheapest["seller"],
            "buy the cheapest listing and relist near the conservative market price",
        )
        if idea:
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
        if product not in auctions or len(auctions[product]) < 2:
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

        sell = conservative_exit_price(auctions[product])
        if sell is None:
            continue

        idea = make_opportunity(
            "CRAFT",
            product,
            cost,
            1,
            sell,
            "market materials",
            "buy the cheapest materials, craft one item, then relist",
        )

        if idea:
            ideas.append(idea)

    return ideas


def scan_budget(ideas):
    if BUDGET <= 0:
        return ideas

    result = []

    for idea in ideas:
        affordable = int(BUDGET // idea["buy_total"])
        if affordable <= 0:
            continue

        idea = dict(idea)
        idea["qty"] = min(idea["qty"], affordable)
        idea["buy_total"] = idea["buy_unit"] * idea["qty"]
        idea["revenue"] = after_fee(idea["sell_unit"]) * idea["qty"]
        idea["profit"] = idea["revenue"] - idea["buy_total"]
        idea["roi"] = idea["profit"] / idea["buy_total"]

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
        )

        old = unique.get(key)

        if old is None or idea["profit"] > old["profit"]:
            unique[key] = idea

    ideas = list(unique.values())
    ideas.sort(
        key=lambda x: (x["profit"], x["roi"]),
        reverse=True
    )

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
        "",
    ]

    for i, x in enumerate(ideas, 1):
        lines.extend([
            f"DEAL {i}: {x['item'].upper()}",
            f"METHOD: {x['kind']}",
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
            "",
            f"WHAT TO DO: {x['note'].capitalize()}.",
            "",
            "IMPORTANT: The sell price is an estimate based on current market listings.",
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

    # Discord message limit is 2000 characters.
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
            f"I checked the market successfully. There is currently no deal "
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
