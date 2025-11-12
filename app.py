from fastapi import FastAPI, Request
import requests
import json
import os

app = FastAPI()

# === Shopify Configuration ===
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL", "fullstopbeest.myshopify.com")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "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")

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


def fetch_variant_id_by_sku(sku: str):
    """Fetch variant ID for a given SKU using Shopify API."""
    print(f"🔍 Fetching variant for SKU: {sku}")
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
    }

    resp = requests.get(
        f"https://{SHOPIFY_STORE_URL}/admin/api/2025-01/variants.json?sku={sku}",
        headers=headers,
    )

    print(f"🧾 Shopify API Response ({resp.status_code}): {resp.text[:400]}")

    if resp.status_code != 200:
        print(f"❌ Shopify API error {resp.status_code}: {resp.text}")
        return None

    variants = resp.json().get("variants", [])
    for v in variants:
        variant_sku = (v.get("sku") or "").strip().upper()
        if variant_sku == sku.upper():
            print(f"✅ Found variant ID {v['id']} for SKU {sku}")
            return v["id"]

    print(f"⚠️ No variant found for SKU {sku}")
    return None


@app.post("/webhook/orders/create")
async def order_created(request: Request):
    """Triggered when a new order is created in Shopify."""
    try:
        payload = await request.json()
        order_id = payload.get("id")
        line_items = payload.get("line_items", [])

        print(f"\n🔔 New Order #{order_id} received")

        order_skus = [(item.get("sku") or "").strip().upper() for item in line_items]
        print(f"🧾 Order SKUs (from Shopify payload): {order_skus}")
        print(f"🎯 Main Trigger SKUs (code list): {TRIGGER_SKUS}")

        # ✅ Detect main SKU
        trigger_found = any(sku in TRIGGER_SKUS for sku in order_skus)
        print(f"✅ Trigger present? {trigger_found}")

        if not trigger_found:
            print("🚫 No trigger SKU found — skipping freebies.")
            return {"status": "ignored"}

        # ✅ Find existing freebies
        existing_freebies = [sku for sku in order_skus if sku in FREEBIE_SKUS]
        print(f"🎁 Existing freebies in order: {existing_freebies}")

        # ✅ Detect missing freebies
        missing_freebies = [sku for sku in FREEBIE_SKUS if sku not in existing_freebies]
        print(f"🆕 Missing freebies to add: {missing_freebies}")

        if not missing_freebies:
            print("✅ All freebies already present.")
            return {"status": "freebies_already_present"}

        # ✅ Get variant IDs for missing freebies
        missing_variant_ids = []
        for sku in missing_freebies:
            vid = fetch_variant_id_by_sku(sku)
            if vid:
                missing_variant_ids.append(vid)

        print(f"🧩 Variant IDs to add (for log): {missing_variant_ids}")

        # ✅ Instead of modifying the order (Shopify doesn’t allow),
        # we log them via order metafields
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        }

        metafield_data = {
            "metafield": {
                "namespace": "freebies",
                "key": "missing_freebies",
                "value": json.dumps(missing_freebies),
                "type": "json"
            }
        }

        meta_resp = requests.post(
            f"https://{SHOPIFY_STORE_URL}/admin/api/2025-01/orders/{order_id}/metafields.json",
            headers=headers,
            data=json.dumps(metafield_data),
        )

        print(f"📝 Shopify metafield response ({meta_resp.status_code}): {meta_resp.text[:300]}")

        if meta_resp.status_code in (200, 201):
            print("✅ Missing freebies logged successfully.")
            return {
                "status": "logged_missing_freebies",
                "missing_freebies": missing_freebies,
            }
        else:
            print("⚠️ Could not log metafield, but no crash.")
            return {"status": "freebies_detected", "missing_freebies": missing_freebies}

    except Exception as e:
        print(f"💥 Error in webhook: {e}")
        return {"status": "error", "message": str(e)}
