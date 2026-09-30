import os
import sys
import time
import requests

API Credentials from GitHub Secrets / Linux Environment Variables

API_TOKEN = os.getenv("BAGEL_API_TOKEN", "").strip()
BASE_URL = "https://api.bagelsmp.com/v1"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

headers = {
"Authorization": f"Bearer {API_TOKEN}",
"Content-Type": "application/json"
}

def send_alert(message):
"""Send a mobile push notification through Discord Webhook."""
if DISCORD_WEBHOOK_URL:
try:
payload = {"content": message}

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=15
        )

        if response.status_code == 204:
            print("Discord alert sent successfully.")
        else:
            print(
                f"Discord Webhook returned status code: "
                f"{response.status_code}"
            )

    except Exception as e:
        print(f"Failed to send Discord notification: {e}")

def get_market_data(endpoint):
"""Fetch market data from Bagel SMP API."""
url = f"{BASE_URL}/{endpoint}"

try:
    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    print(f"\nGET {url}")
    print(f"HTTP Status: {response.status_code}")

    if response.status_code == 200:
        try:
            return response.json()
        except Exception as e:
            print(f"Could not decode JSON: {e}")
            print(response.text[:5000])
            return None

    print("API returned an error.")
    print(response.text[:5000])

    return None

except Exception as e:
    print(f"API request failed for {endpoint}: {e}")
    return None

def print_diagnostic_data(name, data, max_items=10):
"""Print a safe sample of API data."""

print("\n" + "=" * 70)
print(f"========== {name.upper()} ==========")
print("=" * 70)

if data is None:
    print("No data returned.")
    return

print(f"Python data type: {type(data).__name__}")

if isinstance(data, dict):

    print(f"Dictionary keys: {list(data.keys())}")
    print("\nSample data:")

    count = 0

    for key, value in data.items():

        print(f"\nKEY: {key}")
        print(f"VALUE: {repr(value)[:2000]}")

        count += 1

        if count >= max_items:
            break

elif isinstance(data, list):

    print(f"Number of entries returned: {len(data)}")
    print(
        f"\nShowing first "
        f"{min(max_items, len(data))} entries:"
    )

    for i, item in enumerate(data[:max_items]):

        print(f"\n--- ENTRY {i + 1} ---")
        print(repr(item)[:3000])

else:

    print("\nRaw data:")
    print(repr(data)[:5000])

def analyze_api():
"""Run one diagnostic API scan."""

if not API_TOKEN:

    print(
        "CRITICAL ERROR: "
        "BAGEL_API_TOKEN environment variable is empty!"
    )

    return

print("\n")
print("=" * 70)
print("BAGEL SMP API DIAGNOSTIC SCANNER")
print("=" * 70)
print("API token detected: YES")
print("API token value will NOT be printed.")
print("=" * 70)

# Get prices
prices = get_market_data("prices")

print_diagnostic_data(
    "prices",
    prices,
    max_items=10
)

# Get orders
orders = get_market_data("orders")

print_diagnostic_data(
    "orders",
    orders,
    max_items=10
)

# Get auctions
auctions = get_market_data("auctions")

print_diagnostic_data(
    "auctions",
    auctions,
    max_items=10
)

# Summary
print("\n")
print("=" * 70)
print("DIAGNOSTIC SUMMARY")
print("=" * 70)

if isinstance(prices, dict):
    print(f"Prices: {len(prices)} dictionary entries")

elif isinstance(prices, list):
    print(f"Prices: {len(prices)} entries")

else:
    print("Prices: No usable data")

if isinstance(orders, list):
    print(f"Orders: {len(orders)} entries")

elif isinstance(orders, dict):
    print(f"Orders: dictionary with {len(orders)} entries")

else:
    print("Orders: No usable data")

if isinstance(auctions, list):
    print(f"Auctions: {len(auctions)} entries")

elif isinstance(auctions, dict):
    print(f"Auctions: dictionary with {len(auctions)} entries")

else:
    print("Auctions: No usable data")

print("=" * 70)
print("Diagnostic scan complete.")
print("=" * 70)

if name == "main":

if "--loop" in sys.argv:

    send_alert(
        "Bagel SMP Diagnostic Scanner Started.\n"
        "Checking API structure. Results are being printed "
        "to the GitHub Actions log."
    )

    start_time = time.time()

    # Same worker lifetime as your existing setup.
    max_duration = 330 * 60

    while (time.time() - start_time) < max_duration:

        try:
            analyze_api()

        except Exception as e:
            print(f"Error during diagnostic scan: {e}")

        # Keep your existing 5-minute interval.
        time.sleep(300)

    send_alert(
        "Bagel SMP Diagnostic Loop Complete.\n"
        "The GitHub worker cycle has ended."
    )

else:

    send_alert(
        "Bagel SMP Diagnostic Scanner Started.\n"
        "Running one API structure check..."
    )

    analyze_api()
