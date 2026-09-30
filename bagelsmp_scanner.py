import os
import sys
import time
import requests

API_TOKEN = os.getenv("BAGEL_API_TOKEN", "").strip()
BASE_URL = "https://api.bagelsmp.com/v1"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

headers = {
"Authorization": f"Bearer {API_TOKEN}",
"Content-Type": "application/json"
}

def send_alert(message):
if not DISCORD_WEBHOOK_URL:
return

try:
    response = requests.post(
        DISCORD_WEBHOOK_URL,
        json={"content": message},
        timeout=15
    )

    print("Discord status:", response.status_code)

except Exception as e:
    print("Discord error:", e)

def get_market_data(endpoint):
url = f"{BASE_URL}/{endpoint}"

try:
    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    print()
    print("REQUEST:", url)
    print("STATUS:", response.status_code)

    if response.status_code != 200:
        print("ERROR RESPONSE:")
        print(response.text[:5000])
        return None

    try:
        return response.json()

    except Exception as e:
        print("JSON ERROR:", e)
        print(response.text[:5000])
        return None

except Exception as e:
    print("REQUEST ERROR:", e)
    return None

def show_data(name, data):
print()
print("=" * 70)
print(name)
print("=" * 70)

if data is None:
    print("NO DATA")
    return

print("TYPE:", type(data).__name__)

if isinstance(data, list):

    print("COUNT:", len(data))

    for i, item in enumerate(data[:10]):
        print()
        print("ENTRY", i + 1)
        print(repr(item)[:3000])

elif isinstance(data, dict):

    print("KEY COUNT:", len(data))
    print("KEYS:", list(data.keys()))

    count = 0

    for key, value in data.items():
        print()
        print("KEY:", key)
        print("VALUE:", repr(value)[:3000])

        count += 1

        if count >= 10:
            break

else:

    print(repr(data)[:5000])

def run_scan():

if not API_TOKEN:
    print("ERROR: BAGEL_API_TOKEN is empty.")
    return

print()
print("=" * 70)
print("BAGEL SMP API DIAGNOSTIC")
print("=" * 70)
print("API TOKEN FOUND: YES")
print("TOKEN VALUE IS HIDDEN")
print("=" * 70)

prices = get_market_data("prices")
show_data("PRICES", prices)

orders = get_market_data("orders")
show_data("ORDERS", orders)

auctions = get_market_data("auctions")
show_data("AUCTIONS", auctions)

print()
print("=" * 70)
print("SCAN COMPLETE")
print("=" * 70)

if name == "main":

if "--loop" in sys.argv:

    send_alert(
        "Bagel SMP diagnostic scanner started."
    )

    start_time = time.time()
    max_duration = 330 * 60

    while (time.time() - start_time) < max_duration:

        try:
            run_scan()

        except Exception as e:
            print("SCAN ERROR:", e)

        time.sleep(300)

    send_alert(
        "Bagel SMP diagnostic loop finished."
    )

else:

    run_scan()
