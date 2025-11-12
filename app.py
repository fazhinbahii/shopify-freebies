from fastapi import FastAPI, Request
import requests
import json
import os

app = FastAPI()

# === Shopify Configuration ===
SHOPIFY_ADMIN_TOKEN = "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"
SHOPIFY_DOMAIN = "fullstopbeest.myshopify.com"

# === SKU Lists ===
TRIGGER_SKUS = [
    "B-BP-SFI-12PK-V2",
    "B-BP-SFI-24PK-V1-MF",
    "B-BP-SFI-36PK-V1-MF",
]

FREEBIE_SKUS = [
    "FREE-B-BP-SPC-2PK-V1",
    "FREE-B-BP-APPLICAT-XX-V1",
    "FREE-B-BP-PPE-V1",
]


# === Helper Functions ===

def fetch_variant_id_by_sku(sku: str):
    """Fetch variant ID for a SKU using Shopify API."""
    print(f"🔍 Fetching variant for SKU: {sku}")
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
    }
    resp = requests.get(
        f"https://{SHOPIFY_STORE_URL}/admin/api/2023-07/products.json?sku={sku}",
        headers=headers,
    )

    if resp.status_code != 200:
        print(f"❌ Shopify API error {resp.status_code}: {resp.text}")
        return None

    products = resp.json().get("products", [])
    for p in products:
        for v in p.get("variants", []):
            if (v.get("sku") or "").strip().upper() == sku.upper():
                print(f"✅ Found variant {v['id']} for SKU {sku}")
                return v["id"]

    print(f"⚠️ No variant found for SKU {sku}")
    return None


# === Webhook Endpoint ===
@app.post("/webhook/orders/create")
async def order_created(request: Request):
    """Triggered when a new order is created in Shopify."""
    try:
        payload = await request.json()
        order_id = payload.get("id")
        line_items = payload.get("line_items", [])

        print(f"\n🔔 New Order #{order_id} received")
        order_skus = [item.get("sku", "").strip().upper() for item in line_items]
        print(f"🧾 Order SKUs (from Shopify payload): {order_skus}")
        print(f"🎯 Main Trigger SKUs (code list): {TRIGGER_SKUS}")

        # Check if order contains any main SKU
        trigger_found = any(sku in TRIGGER_SKUS for sku in order_skus)
        print(f"✅ Trigger present? {trigger_found}")

        if not trigger_found:
            print("🚫 No trigger SKU found. No freebies added.")
            return {"status": "ignored"}

        # Identify existing freebies already in the order
        existing_freebies = [sku for sku in order_skus if sku in FREEBIE_SKUS]
        print(f"🎁 Existing freebies in order: {existing_freebies}")

        # Determine which freebies are missing
        missing_freebies = [sku for sku in FREEBIE_SKUS if sku not in existing_freebies]
        print(f"🆕 Missing freebies to add: {missing_freebies}")

        if not missing_freebies:
            print("✅ All freebies already present. Nothing to add.")
            return {"status": "freebies_already_present"}

        # Prepare freebies to add
        add_freebie_items = []
        for sku in missing_freebies:
            variant_id = fetch_variant_id_by_sku(sku)
            if variant_id:
                add_freebie_items.append({"variant_id": variant_id, "quantity": 1})

        if not add_freebie_items:
            print("⚠️ No valid freebies found to add.")
            return {"status": "no_valid_freebies"}

        # === Create Draft Order or Add to Existing Order ===
        print(f"🛒 Adding freebies to Order #{order_id}")
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        }
        data = {"order": {"id": order_id, "line_items": add_freebie_items}}

        update_resp = requests.put(
            f"https://{SHOPIFY_STORE_URL}/admin/api/2023-07/orders/{order_id}.json",
            headers=headers,
            data=json.dumps(data),
        )

        if update_resp.status_code == 200:
            print(f"✅ Freebies successfully added to order #{order_id}")
            return {"status": "success"}
        else:
            print(f"❌ Failed to update order: {update_resp.text}")
            return {"status": "failed", "error": update_resp.text}

    except Exception as e:
        print(f"💥 Error in webhook: {e}")
        return {"status": "error", "message": str(e)}
