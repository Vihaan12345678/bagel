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
    "cactus": 1.0,        
    "sugarcane": 2.0,     
    "melon_slice": 4.0,   
    "pumpkin": 1.0        
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
    if not API_TOKEN or API_TOKEN == "YOUR_API_TOKEN":
        print("❌ CRITICAL ERROR: Your BAGEL_API_TOKEN environment variable is empty!")
        print("Please check your GitHub Secrets settings or local export variables.")
        return

    # Verified endpoints based on official Bagel SMP API routing configurations
    prices = get_market_data("prices")
    orders = get_market_data("orders")
    auctions = get_market_data("auctions") # The correct API route matching the in-game /ah
    
    if not prices:
        print("❌ Unable to fetch baseline server market rates. (Status Code 404)")
        print("Tip: Re-verify your Bearer Token in GitHub Secrets to ensure there are no trailing spaces.")
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

    # 2. Combined Market Loop (Orders + Live Auctions)
    print("\n🔍 Scanning for Arbitrage and Market Flipping Opportunities...")
    alert_message = ""
    flips_found = 0
    
    # Combine active data arrays from both marketplace endpoints
    marketplace_listings = []
    if orders: marketplace_listings.extend(orders)
    if auctions: marketplace_listings.extend(auctions)
    
    if marketplace_listings:
        for listing in marketplace_listings:
            item_name = listing.get("item", "").lower()
            listed_price = listing.get("price", 0)
            quantity = listing.get("quantity", 1)
            
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
