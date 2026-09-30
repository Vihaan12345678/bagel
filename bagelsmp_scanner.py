import os
import requests

API_TOKEN = os.getenv("BAGEL_API_TOKEN", "").strip()
BASE_URL = "https://api.bagelsmp.com/v1"

HEADERS = {
"Authorization": f"Bearer {API_TOKEN}",
"Content-Type": "application/json"
}

def get_data(endpoint):
url = f"{BASE_URL}/{endpoint}"

print()
print("=" * 70)
print("ENDPOINT:", endpoint)
print("=" * 70)

try:
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    print("HTTP STATUS:", response.status_code)

    if response.status_code != 200:
        print("API ERROR:")
        print(response.text[:10000])
        return None

    try:
        data = response.json()
    except Exception as error:
        print("JSON ERROR:", error)
        print("RAW RESPONSE:")
        print(response.text[:10000])
        return None

    print("DATA TYPE:", type(data).__name__)

    if isinstance(data, list):
        print("NUMBER OF ITEMS:", len(data))

        for index, item in enumerate(data[:20]):
            print()
            print("--- ITEM", index + 1, "---")
            print(repr(item)[:5000])

    elif isinstance(data, dict):
        print("NUMBER OF KEYS:", len(data))
        print("KEYS:")

        for key in data.keys():
            print(" ", key)

        print()
        print("SAMPLE DATA:")

        count = 0

        for key, value in data.items():
            print()
            print("--- KEY:", key, "---")
            print(repr(value)[:5000])

            count += 1

            if count >= 20:
                break

    else:
        print("DATA:")
        print(repr(data)[:10000])

    return data

except requests.exceptions.Timeout:
    print("REQUEST TIMED OUT.")
    return None

except requests.exceptions.RequestException as error:
    print("REQUEST ERROR:", error)
    return None

except Exception as error:
    print("UNEXPECTED ERROR:", error)
    return None

def main():

print("=" * 70)
print("BAGEL SMP API DIAGNOSTIC")
print("=" * 70)

if not API_TOKEN:
    print("ERROR: BAGEL_API_TOKEN is missing.")
    print("Check your GitHub repository secret.")
    return

print("API TOKEN FOUND: YES")
print("API TOKEN VALUE IS HIDDEN.")

prices = get_data("prices")
orders = get_data("orders")
auctions = get_data("auctions")

print()
print("=" * 70)
print("DIAGNOSTIC SUMMARY")
print("=" * 70)

if prices is None:
    print("PRICES: FAILED")
elif isinstance(prices, list):
    print("PRICES:", len(prices), "items")
elif isinstance(prices, dict):
    print("PRICES:", len(prices), "keys")
else:
    print("PRICES: received")

if orders is None:
    print("ORDERS: FAILED")
elif isinstance(orders, list):
    print("ORDERS:", len(orders), "items")
elif isinstance(orders, dict):
    print("ORDERS:", len(orders), "keys")
else:
    print("ORDERS: received")

if auctions is None:
    print("AUCTIONS: FAILED")
elif isinstance(auctions, list):
    print("AUCTIONS:", len(auctions), "items")
elif isinstance(auctions, dict):
    print("AUCTIONS:", len(auctions), "keys")
else:
    print("AUCTIONS: received")

print("=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)

if name == "main":
main()
