import os
import requests

# 🔐 API Credentials from GitHub Secrets / Linux Environment Variables
API_TOKEN = os.getenv("BAGEL_API_TOKEN", "").strip()
BASE_URL = "https://bagelsmp.com"
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

    print("📊 --- BAGEL SMP LOW-MARGIN ARBITRAGE SYSTEM --- 📊\n")
    
    prices = get_market_data("prices") or {}
    orders = get_market_data("orders") or []
    auctions = get_market_data("auctions") or []

    alert_message = ""
    opportunities_count = 0

    # -------------------------------------------------------------------------
    # 🎯 STEP 1: Direct Order-to-AH Flipping Arbitrage
    # -------------------------------------------------------------------------
    print("🔍 Scanning for Direct Order-to-Auction House Flips...")
    
    cheapest_orders = {}
    for o in orders:
        item = o.get("item", "").lower()
        price = o.get("price", 0)
        if item and (item not in cheapest_orders or price < cheapest_orders[item]):
            cheapest_orders[item] = price

    for a in auctions:
        item_name = a.get("item", "").lower()
        ah_listed_price = a.get("price", 0)
        quantity = a.get("quantity", 1)
        
        if item_name in cheapest_orders:
            order_cost = cheapest_orders[item_name] * quantity
            # 📉 LOWER THRESHOLD: Triggers at a 15%+ profit margin instead of 25%
            if ah_listed_price > (order_cost * 1.15):  
                net_profit = ah_listed_price - order_cost
                msg = f"🔄 [DIRECT FLIP] Buy {quantity}x {item_name.upper()} from Orders ({order_cost}) & Sell on AH ({ah_listed_price})! Profit: +{net_profit} coins.\n"
                print(msg.strip())
                alert_message += msg
                opportunities_count += 1

    # -------------------------------------------------------------------------
    # ⚔️ STEP 2: Crafting Arbitrage (Weapons & Gear)
    # -------------------------------------------------------------------------
    print("\n🔨 Analyzing Crafting Profit Margins for Weapons & Armor...")
    
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
        
        # 📉 LOWER THRESHOLD: Triggers at a 10%+ profit margin instead of 30%
        if market_value > (crafting_cost * 1.10): 
            profit = market_value - crafting_cost
            msg = f"⚒️ [CRAFTING PROFIT] Craft {gear_item.upper()}! Material Cost: {crafting_cost} ➔ AH Value: ~{market_value}! Profit: +{profit} coins.\n"
            print(msg.strip())
            alert_message += msg
            opportunities_count += 1

    # -------------------------------------------------------------------------
    # 📢 STEP 3: Report & Send Mobile Notifications
    # -------------------------------------------------------------------------
    print("\n🏆 --- RECOMMENDED ACTION --- 🏆")
    if opportunities_count > 0:
        print("🎯 Small-margin deals detected! Sending to Discord...")
        send_alert(f"📉 **Bagel SMP Low-Margin Arbitrage Report!**\n{alert_message}")
    else:
        print("🚜 No deals found crossing the 10% profit margin line right now.")

if __name__ == "__main__":
    # Add this temporary line right here to test your connection:
    send_alert("🔔 System Check: The market scanner is connected to Discord successfully!")
    
    analyze_best_strategy()

