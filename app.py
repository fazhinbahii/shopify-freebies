# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request
import requests

app = FastAPI()

# --- 🔐 Shopify Configuration ---
SHOPIFY_ADMIN_TOKEN = "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"
SHOPIFY_DOMAIN = "fullstopbeest.myshopify.com"

# --- 🎯 Main SKUs (Trigger Products) ---
MAIN_SKUS = [
    "B-BP-SFI-12PK-V2",
    "B-BP-SFI-24PK-V1-MF",
    "B-BP-SFI-36PK-V1-MF"
]

# --- 🎁 Freebie SKUs (Items to Add Automatically) ---
FREEBIE_SKUS = [
    "FREE-B-BP-SPC-2PK-V1",
    "FREE-B-BP-APPLICAT-XX-V1",
    "FREE-B-BP-PPE-V1"
]


@app.post("/webhook/orders/create")
async def order_created(request: Request):
    """Handles Shopify order creation webhook and adds freebies if applicable."""
    payload = await request.json()
    order_id = payload.get("id")
    line_items = payload.get("line_items", [])

    print(f"🔔 New Order #{order_id} received")
    print(f"🧾 Raw payload SKUs: {[item.get('sku') for item in line_items]}")

    # Normalize order SKUs
    order_skus = [item.get("sku", "").strip().upper() for item in line_items if item.get("sku")]
    print(f"🧾 Cleaned Order SKUs: {order_skus}")
    print(f"🎯 Trigger SKUs: {MAIN_SKUS}")

    # --- Check if any main SKU exists in the order ---
    freebies_to_add = []
    for sku in order_skus:
        print(f"🔎 Checking SKU '{sku}' against triggers...")
        if sku in [m.upper() for m in MAIN_SKUS]:
            print(f"✅ Trigger match found: {sku}")
            freebies_to_add = FREEBIE_SKUS.copy()
            break
        else:
            print(f"❌ No trigger match for: {sku}")

    if not freebies_to_add:
        print("ℹ️ No matching trigger SKU found — skipping freebies.")
        return {"status": "no_freebies"}

    print(f"🎁 Freebies to add: {freebies_to_add}")

    # --- Fetch Shopify Variant IDs for each freebie SKU ---
    variant_ids = []
    for freebie_sku in freebies_to_add:
        url = f"https://{SHOPIFY_DOMAIN}/admin/api/2025-01/variants.json?sku={freebie_sku}"
        print(f"\n🔍 Fetching variant for SKU: {freebie_sku}")
        print(f"🌐 URL: {url}")

        resp = requests.get(
            url,
            headers={"X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN}
        )

        print(f"🧾 Shopify API Response ({resp.status_code}): {resp.text[:400]}...")

        if resp.status_code != 200:
            print(f"⚠️ Failed to fetch variant for {freebie_sku}: {resp.status_code}")
            continue

        data = resp.json()

        # ✅ Exact SKU filter (Shopify ignores ?sku= filter)
        variant = next((v for v in data.get("variants", []) if v.get("sku") == freebie_sku), None)

        if variant:
            variant_id = variant["id"]
            variant_ids.append(variant_id)
            print(f"✅ Exact variant match found → ID: {variant_id}")
        else:
            print(f"⚠️ No exact variant found for SKU {freebie_sku}")

    if not variant_ids:
        print("⚠️ No variant IDs found — freebies not added.")
        return {"status": "no_variants_found", "freebie_skus": freebies_to_add}

    # --- Log freebies to order metafields (Shopify doesn't allow editing existing orders) ---
    for variant_id in variant_ids:
        add_metafield(order_id, variant_id)

    print(f"✅ All freebies logged successfully for Order #{order_id}")

    return {
        "status": "freebies_added",
        "freebie_count": len(variant_ids),
        "freebie_skus": freebies_to_add
    }


def add_metafield(order_id, variant_id):
    """Adds a metafield to log that a freebie variant was linked to the order."""
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/2025-01/orders/{order_id}/metafields.json"
    payload = {
        "metafield": {
            "namespace": "freebie",
            "key": f"variant_{variant_id}",
            "value": "added",
            "type": "single_line_text_field"
        }
    }

    resp = requests.post(
        url,
        headers={"X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN},
        json=payload
    )

    if resp.status_code in (200, 201):
        print(f"📝 Logged freebie variant {variant_id} to order {order_id}")
    else:
        print(f"⚠️ Failed to log freebie {variant_id}: {resp.status_code} → {resp.text[:300]}")
