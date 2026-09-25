import os
import requests

API_TOKEN = os.getenv("BAGEL_API_TOKEN", "").strip()
BASE_URL = "https://bagelsmp.com"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

# 🛠️ Define Minecraft Crafting Recipes & Material Requirements
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
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
            print("✅ Mobile alert sent successfully!")
        except Exception as e:
            print(f"❌ Failed to send Discord notification: {e}")

def get_market_data(endpoint):
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

    print("📊 --- BAGEL SMP MULTI-MARKET ARBITRAGE SYSTEM --- 📊\n")
    
    prices = get_market_data("prices") or {}
    orders = get_market_data("orders") or []
    auctions = get_market_data("auctions") or []

    alert_message = ""
    opportunities_count = 0

    # -------------------------------------------------------------------------
    # 🎯 STEP 1: Direct Order-to-AH Flipping Arbitrage
    # -------------------------------------------------------------------------
    print("🔍 Scanning for Direct Order-to-Auction House Flips...")
    
    # Map out the cheapest buying option from orders
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
        
        # If the item can be acquired from orders cheaper than it sells on AH
        if item_name in cheapest_orders:
            order_cost = cheapest_orders[item_name] * quantity
            if ah_listed_price > (order_cost * 1.25):  # 25%+ Profit Margin
                net_profit = ah_listed_price - order_cost
                msg = f"🔄 [DIRECT FLIP] Buy {quantity}x {item_name.upper()} from Orders for {order_cost} & Sell on AH for {ah_listed_price}! Net Profit: +{net_profit} coins.\n"
                print(msg.strip())
                alert_message += msg
                opportunities_count += 1

    # -------------------------------------------------------------------------
    # ⚔️ STEP 2: Crafting Arbitrage (Swords, Axes, Gear)
    # -------------------------------------------------------------------------
    print("\n🔨 Analyzing Crafting Profit Margins for Weapons & Armor...")
    
    # Calculate the raw material costs using current order pricing
    # Standard fallback prices applied if order book lacks raw items
    material_costs = {
        "diamond": cheapest_orders.get("diamond", prices.get("diamond", 200)),
        "iron_ingot": cheapest_orders.get("iron_ingot", prices.get("iron_ingot", 30)),
        "stick": cheapest_orders.get("stick", prices.get("stick", 1))
    }

    # Map out active prices on the auction house to verify standard gear value
    highest_ah_gear = {}
    for a in auctions:
        item = a.get("item", "").lower()
        price = a.get("price", 0)
        if item in CRAFTING_RECIPES:
            if item not in highest_ah_gear or price > highest_ah_gear[item]:
                highest_ah_gear[item] = price

    # Calculate profit metrics for each recipe
    for gear_item, ingredients in CRAFTING_RECIPES.items():
        # Compute the cost to craft the gear piece
        crafting_cost = 0
        for mat, count in ingredients.items():
            crafting_cost += material_costs.get(mat, 999999) * count
        
        # Check if players are listing this completed gear on AH for more than the cost to make it
        market_value = highest_ah_gear.get(gear_item, prices.get(gear_item, 0))
        
        if market_value > (crafting_cost * 1.30): # 30%+ profit matrix check
            profit = market_value - crafting_cost
            msg = f"⚒️ [CRAFTING PROFIT] Craft {gear_item.upper()}! Material Cost: {crafting_cost} coins ➔ Sells on AH for ~{market_value} coins! Profit per item: +{profit} coins.\n"
            print(msg.strip())
            alert_message += msg
            opportunities_count += 1

    # -------------------------------------------------------------------------
    # 📢 STEP 3: Report & Send Mobile Notifications
    # -------------------------------------------------------------------------
    print("\n🏆 --- RECOMMENDED ACTION --- 🏆")
    if opportunities_count > 0:
        print("🎯 Opportunities detected! Review the targets above and log into the server to execute.")
        send_alert(f"💰 **Bagel SMP Arbitrage Report!**\n{alert_message}")
    else:
        print("🚜 Markets are currently aligned perfectly. Maintain your passive crop farming lines.")

if __name__ == "__main__":
    # Add this temporary line right here to test your connection:
    send_alert("🔔 System Check: The market scanner is connected to Discord successfully!")
    
    analyze_best_strategy()

