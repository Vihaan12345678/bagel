import os
import sys
import time
import requests

# 🔐 API Credentials from GitHub Secrets / Linux Environment Variables
API_TOKEN = os.getenv("BAGEL_API_TOKEN", "").strip()
BASE_URL = "https://api.bagelsmp.com/v1"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

# 🛠️ Minecraft Crafting Recipes & Material Requirements
CRAFTING_RECIPES = {
    "diamond_sword":   {"diamond": 2, "stick": 1},
    "diamond_axe":     {"diamond": 3, "stick": 2},
    "diamond_pickaxe": {"diamond": 3, "stick": 2},
    "diamond_helmet":  {"diamond": 5},
    "diamond_chestplate": {"diamond": 8},
    "diamond_leggings":  {"diamond": 7},
    "diamond_boots":     {"diamond": 4},
    "iron_sword":      {"iron_ingot": 2, "stick": 1},
    "iron_axe":        {"iron_ingot": 3, "stick": 2},
    "iron_pickaxe":    {"iron_ingot": 3, "stick": 2},
}

def send_alert(message):
    """Sends a mobile push notification alert via your Discord Webhook."""
    if DISCORD_WEBHOOK_URL:
        try:
            payload = {"content": message}
            response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            if response.status_code == 204:
                print("✅ Mobile alert sent successfully!")
            else:
                print(f"⚠️ Discord Webhook returned status code: {response.status_code}")
        except Exception as e:
            print(f"❌ Failed to send Discord notification: {e}")

def get_market_data(endpoint):
    """Fetches target market data array from the server endpoint."""
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

def analyze_best_strategy():
    if not API_TOKEN or API_TOKEN == "":
        print("❌ CRITICAL ERROR: Your BAGEL_API_TOKEN environment variable is empty!")
        return

    print("📊 --- BAGEL SMP SELLER-TRACKING ENGINE (5%) --- 📊\n")
    
    prices = get_market_data("prices") or {}
    orders = get_market_data("orders") or []
    auctions = get_market_data("auctions") or []

    alert_message = ""
    opportunities_count = 0

    # -------------------------------------------------------------------------
    # 🎯 STEP 1: Direct Order-to-AH Flipping Arbitrage
    # -------------------------------------------------------------------------
    cheapest_orders = {}
    order_sellers = {}
    for o in orders:
        item = o.get("item", "").lower()
        price = o.get("price", 0)
        seller = o.get("seller") or o.get("username") or o.get("owner") or "Unknown Player"
        if item and (item not in cheapest_orders or price < cheapest_orders[item]):
            cheapest_orders[item] = price
            order_sellers[item] = seller

    for a in auctions:
        item_name = a.get("item", "").lower()
        ah_listed_price = a.get("price", 0)
        quantity = a.get("quantity", 1)
        
        if item_name in cheapest_orders:
            order_cost = cheapest_orders[item_name] * quantity
            if ah_listed_price > (order_cost * 1.05):  
                net_profit = ah_listed_price - order_cost
                order_seller = order_sellers[item_name]
                msg = f"🔄 **[ORDER -> AH FLIP]**\n👉 **{order_seller}** has an active sell order for {quantity}x {item_name.upper()} at {cheapest_orders[item_name]} each.\n💰 *Action:* Buy it from orders for {order_cost} total, then resell it on `/ah` for {ah_listed_price}! **Net Profit: +{net_profit} coins.**\n\n"
                alert_message += msg
                opportunities_count += 1

    # -------------------------------------------------------------------------
    # ⚔️ STEP 2: Crafting Arbitrage (Weapons & Gear)
    # -------------------------------------------------------------------------
    material_costs = {
        "diamond": cheapest_orders.get("diamond", prices.get("diamond", 200)),
        "iron_ingot": cheapest_orders.get("iron_ingot", prices.get("iron_ingot", 30)),
        "stick": cheapest_orders.get("stick", prices.get("stick", 1))
    }

    highest_ah_gear = {}
    for a in auctions:
        item = a.get("item", "").lower()
        price = a.get("price", 0)
        if item in CRAFTING_RECIPES:
            if item not in highest_ah_gear or price > highest_ah_gear[item]:
                highest_ah_gear[item] = price

    for gear_item, ingredients in CRAFTING_RECIPES.items():
        crafting_cost = 0
        for mat, count in ingredients.items():
            crafting_cost += material_costs.get(mat, 999999) * count
        
        market_value = highest_ah_gear.get(gear_item, prices.get(gear_item, 0))
        
        if market_value > (crafting_cost * 1.05): 
            profit = market_value - crafting_cost
            mat_sources = []
            for mat in ingredients.keys():
                src = order_sellers.get(mat, "the market")
                mat_sources.append(f"{mat} from {src}")
            mats_str = ", ".join(mat_sources)
            
            msg = f"⚒️ **[CRAFTING OPPORTUNITY]**\n👉 You can order materials ({mats_str}) for a total crafting cost of {crafting_cost} coins.\n💰 *Action:* Craft a {gear_item.upper()} and list it on `/ah` for ~{market_value} coins! **Net Profit: +{profit} coins per item.**\n\n"
            alert_message += msg
            opportunities_count += 1

    # -------------------------------------------------------------------------
    # ⚖️ STEP 3: Pure AH-to-AH Flipping (Reselling within /ah)
    # -------------------------------------------------------------------------
    items_by_group = {}
    for a in auctions:
        item_name = a.get("item", "").lower()
        price = a.get("price", 0)
        quantity = a.get("quantity", 1)
        seller = a.get("seller") or a.get("username") or a.get("owner") or "Unknown Player"
        if quantity > 0 and price > 0:
            price_per_unit = price / quantity
            if item_name not in items_by_group:
                items_by_group[item_name] = []
            items_by_group[item_name].append({
                "total_price": price, 
                "unit_price": price_per_unit, 
                "qty": quantity,
                "seller": seller
            })

    for item_name, listings in items_by_group.items():
        if len(listings) < 2:
            continue  
            
        listings.sort(key=lambda x: x["unit_price"])
        
        cheapest = listings[0]
        next_cheapest = listings[1]
        
        potential_resell_value = next_cheapest["unit_price"] * cheapest["qty"]
        if potential_resell_value > (cheapest["total_price"] * 1.05):
            profit = potential_resell_value - cheapest["total_price"]
            msg = f"⚖️ **[AH -> AH RESELL FLIP]**\n👉 **{cheapest['seller']}** mispriced a listing of {cheapest['qty']}x {item_name.upper()} for only {cheapest['total_price']} total coins!\n💰 *Action:* Buy it instantly from `/ah` and resell it at the standard unit price for ~{int(potential_resell_value)} coins! **Net Profit: +{int(profit)} coins.**\n\n"
            alert_message += msg
            opportunities_count += 1

    # -------------------------------------------------------------------------
    # 📢 STEP 4: Report Status
    # -------------------------------------------------------------------------
    if opportunities_count > 0:
        send_alert(f"🔥 **Bagel SMP 5% Arbitrage Alert!**\n\n{alert_message}")
    else:
        send_alert("🟢 **Scanner Heartbeat:** Checked markets. No deals crossing the 5% margin right now.")

if __name__ == "__main__":
    if "--loop" in sys.argv:
        send_alert("🚀 **Scanner Initialized:** Endless Cloud Loop Activated. Scanning every 5 minutes...")
        
        start_time = time.time()
        # Keep loop alive for ~5.5 hours (330 minutes) per worker session
        max_duration = 330 * 60 
        
        while (time.time() - start_time) < max_duration:
            try:
                analyze_best_strategy()
            except Exception as e:
                print(f"Error during loop run: {e}")
            
            # Wait exactly 5 minutes (300 seconds)
            time.sleep(300)
            
        send_alert("🔄 **Loop Cycle Complete:** Recycling server slot shortly to avoid system blockages...")
    else:
        send_alert("🚀 **Scanner Initialized:** Running single manual market check...")
        analyze_best_strategy()
