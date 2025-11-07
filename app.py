# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

# ✅ Use token directly (not wrapped in os.getenv)
SHOPIFY_ADMIN_TOKEN = "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"
SHOPIFY_DOMAIN = "fullstopbeest.myshopify.com"

# --- 🎯 Main SKUs (Trigger Products) ---
# If any of these SKUs are present in an order, all freebies will be added.
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
    payload = await request.json()
    order_id = payload.get("id")
    line_items = payload.get("line_items", [])

    print(f"🔔 New Order #{order_id} received")

    # Collect all SKUs in the order (clean whitespace + lowercase)
    order_skus = [item.get("sku", "").strip() for item in line_items if item.get("sku")]
    print(f"🧾 Order SKUs (from Shopify payload): {order_skus}")
    print(f"🎯 Main Trigger SKUs (code list): {MAIN_SKUS}")

    freebies_to_add = []

    # 🔍 Debug each SKU comparison
    for sku in order_skus:
        normalized_sku = sku.strip().upper()
        print(f"🔎 Checking order SKU '{normalized_sku}' against triggers...")
        if normalized_sku in [m.upper() for m in MAIN_SKUS]:
            print(f"✅ Match found: {sku}")
            freebies_to_add = FREEBIE_SKUS.copy()
            break
        else:
            print(f"❌ No match for {sku}")

    if not freebies_to_add:
        print("✅ No matching main SKU found — no freebies will be added.")
        return {"status": "no_freebies"}

    print(f"🎁 Adding freebies: {freebies_to_add}")

    # --- DEBUG: Fetch Shopify Variant IDs for each freebie SKU ---
    variant_ids = []
    for sku in freebies_to_add:
        url = f"https://{SHOPIFY_DOMAIN}/admin/api/2025-01/variants.json?sku={sku}"
        print(f"🔍 Fetching variant for SKU: {sku}")
        print(f"🌐 URL: {url}")

        resp = requests.get(
            url,
            headers={"X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN}
        )

        # ✅ Debug output (limit long responses)
        print(f"🧾 Shopify API Response ({resp.status_code}): {resp.text[:500]}")

        if resp.status_code != 200:
            print(f"⚠️ Failed to fetch variant for {sku}: {resp.status_code}")
            continue

        data = resp.json()
        if data.get("variants"):
            variant_id = data["variants"][0]["id"]
            variant_ids.append(variant_id)
            print(f"✅ Found variant ID {variant_id} for SKU {sku}")
        else:
            print(f"⚠️ No variant found for SKU {sku}")

    # --- Log freebies to order metafields (Shopify doesn't allow direct edits) ---
    for variant_id in variant_ids:
        add_metafield(order_id, variant_id)

    return {
        "status": "freebies_added",
        "freebie_count": len(variant_ids),
        "freebie_skus": freebies_to_add
    }


def add_metafield(order_id, variant_id):
    """Adds a metafield to log that a freebie was added."""
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/2025-01/orders/{order_id}/metafields.json"
    resp = requests.post(
        url,
        headers={"X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN},
        json={
            "metafield": {
                "namespace": "freebie",
                "key": f"variant_{variant_id}",
                "value": "added",
                "type": "single_line_text_field"
            }
        }
    )

    if resp.status_code in (200, 201):
        print(f"📝 Logged freebie variant {variant_id} to order {order_id}")
    else:
        print(f"⚠️ Failed to log freebie {variant_id}: {resp.status_code}")
