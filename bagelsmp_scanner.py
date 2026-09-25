import os
import requests

# 🔐 Strip any hidden line breaks or white spaces from GitHub secrets
API_TOKEN = os.getenv("BAGEL_API_TOKEN", "").strip()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

# Base system URL configuration variants
BASE_URL = "https://api.bagelsmp.com/v1"

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

GROWTH_RATES_PER_HOUR = {
    "cactus": 1.0,        
    "sugarcane": 2.0,     
    "melon_slice": 4.0,   
    "pumpkin": 1.0        
}

def send_alert(message):
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
        except Exception as e:
            print(f"❌ Webhook failed: {e}")

def get_market_data(endpoint):
    """Attempts to pull data, testing fallback paths if a 404 occurs."""
    # Test primary path
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass

    # Fallback path adjustment in case API routing updates proxy mappings
    fallback_url = f"https://bagelsmp.com{endpoint}"
    try:
        response = requests.get(fallback_url, headers=headers)
        if response.status_code == 200:
            return response.json()
        print(f"⚠️ API Error ({endpoint}): Main 404, Fallback {response.status_code}")
    except Exception as e:
        print(f"❌ Connection failed for {endpoint}: {e}")
    
    return None

def analyze_best_strategy():
    if not API_TOKEN or "YOUR_" in API_TOKEN:
        print("❌ CRITICAL ERROR: Your BAGEL_API_TOKEN variable is invalid or empty!")
        return

    print("📡 Testing server connectivity pipelines...")
    prices = get_market_data("prices")
    orders = get_market_data("orders")
    auctions = get_market_data("auctions")
    
    if not prices:
        print("❌ Unable to fetch baseline market rates. Both primary and fallback paths returned 404.")
        print("💡 Solution: Verify your Bagel+ account status via the server dashboard.")
        return

    print("📊 --- LIVE SERVER MARKET EVALUATION --- 📊\n")
    
    best_passive_crop = None
    max_passive_yield = 0
    for crop, rate in GROWTH_RATES_PER_HOUR.items():
        crop_price = prices.get(crop, 0)
        hourly_yield = crop_price * rate
        print(f"• {crop.capitalize()}: {crop_price} coins | Yield = {hourly_yield:.2f} coins/hr")
        if hourly_yield > max_passive_yield:
            max_passive_yield = hourly_yield
            best_passive_crop = crop

    print("\n🔍 Scanning for Flipping Opportunities...")
    alert_message = ""
    flips_found = 0
    
    marketplace_listings = []
    if isinstance(orders, list): marketplace_listings.extend(orders)
    if isinstance(auctions, list): marketplace_listings.extend(auctions)
    
    for listing in marketplace_listings:
        item_name = listing.get("item", "").lower()
        listed_price = listing.get("price", 0)
        quantity = listing.get("quantity", 1)
        
        base_value = prices.get(item_name, 0)
        if base_value > 0 and listed_price < (base_value * 0.75):
            potential_profit = (base_value * quantity) - (listed_price * quantity)
            info_line = f"✨ [FLIP] {quantity}x {item_name.upper()} listed for {listed_price}! Profit: +{potential_profit}\n"
            print(info_line.strip())
            alert_message += info_line
            flips_found += 1
                
    if flips_found == 0:
        print("• No immediate market mispricings found right now.")
        
    print("\n🏆 --- RECOMMENDED ACTION --- 🏆")
    if flips_found > 0:
        print("🎯 Priority: Buy the active market listings shown above.")
        send_alert(f"💸 **Bagel SMP Deal Alert!**\n{alert_message}")
    else:
        print(f"🚜 Strategy: Allocate your 22k into building a {best_passive_crop.upper()} farm tower.")

if __name__ == "__main__":
    analyze_best_strategy()
