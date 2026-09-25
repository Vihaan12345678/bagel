import os
import requests

# 🔐 API and Webhook Credentials from Environment Variables
API_TOKEN = os.getenv("BAGEL_API_TOKEN")
BASE_URL = "https://bagelsmp.com"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

# 🌾 Estimated base yield rates per single block/plant per hour
GROWTH_RATES_PER_HOUR = {
    "cactus": 1.0,        # ~1 block per hour per plant
    "sugarcane": 2.0,     # ~2 blocks per hour per plant
    "melon_slice": 4.0,   # Melons break into multiple pieces
    "pumpkin": 1.0        # 1 pumpkin per stem per hour
}

def send_alert(message):
    """Sends a push notification directly to your phone via Discord Webhook."""
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
    else:
        print("ℹ️ Discord Webhook URL not set. Alert printed to console instead.")

def get_market_data(endpoint):
    """Fetches real-time pricing and marketplace details from Bagel SMP."""
    try:
        response = requests.get(f"{BASE_URL}/{endpoint}", headers=headers)
        if response.status_code == 200:
            return response.json()
        print(f"⚠️ API Error ({endpoint}): Status Code {response.status_code}")
        return None
    except Exception as e:
        print(f"❌ Network connection failed for {endpoint}: {e}")
        return None

def analyze_best_strategy():
    prices = get_market_data("prices")
    orders = get_market_data("orders") or get_market_data("auction-house")
    
    if not prices:
        print("❌ Unable to fetch baseline server market rates.")
        return

    print("📊 --- LIVE SERVER MARKET EVALUATION --- 📊\n")
    
    # 1. Base farming calculation
    best_passive_crop = None
    max_passive_yield = 0
    
    for crop, rate in GROWTH_RATES_PER_HOUR.items():
        crop_price = prices.get(crop, 0)
        hourly_yield = crop_price * rate
        print(f"• {crop.capitalize()}: Price = {crop_price} coins | Passive Yield = {hourly_yield:.2f} coins/hr")
        
        if hourly_yield > max_passive_yield:
            max_passive_yield = hourly_yield
            best_passive_crop = crop

    # 2. Order book / Auction House flipping evaluation
    print("\n🔍 Scanning for Arbitrage and Market Flipping Opportunities...")
    alert_message = ""
    flips_found = 0
    
    if orders:
        for listing in orders:
            item_name = listing.get("item", "").lower()
            listed_price = listing.get("price", 0)
            quantity = listing.get("quantity", 1)
            
            # Identify discrepancies where listed item is below 75% of server base value
            base_value = prices.get(item_name, 0)
            if base_value > 0 and listed_price < (base_value * 0.75):
                potential_profit = (base_value * quantity) - (listed_price * quantity)
                
                info_line = f"✨ [FLIP FOUND] {quantity}x {item_name.upper()} listed for {listed_price}! Net Profit: +{potential_profit} coins.\n"
                print(info_line.strip())
                alert_message += info_line
                flips_found += 1
                
    if flips_found == 0:
        print("• No immediate market mispricings found right now.")
        
    print("\n🏆 --- RECOMMENDED ACTION --- 🏆")
    if flips_found > 0:
        print("🎯 Priority: Invest your 22k liquidity into active flip orders listed above for rapid returns.")
        send_alert(f"💸 **Bagel SMP Deal Alert!**\n{alert_message}")
    else:
        print(f"🚜 Strategy: Allocate your 22k into building a massive {best_passive_crop.upper()} farm tower.")

if __name__ == "__main__":
    analyze_best_strategy()
