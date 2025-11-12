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
    payload = await request.json()
    order_id = payload.get("id")
    line_items = payload.get("line_items", [])

    print(f"🔔 New Order #{order_id} received")

    # ✅ Collect SKUs from order
    order_skus = [item.get("sku", "").strip().upper() for item in line_items if item.get("sku")]
    print(f"🧾 Order SKUs (from Shopify payload): {order_skus}")

    # --- Step 1: Check for main SKU trigger ---
    main_sku_found = any(sku in [m.upper() for m in MAIN_SKUS] for sku in order_skus)
    print(f"🎯 Main Trigger SKUs (code list): {MAIN_SKUS}")
    print(f"✅ Trigger present? {main_sku_found}")

    if not main_sku_found:
        print("✅ No main SKU in order — skipping freebies.")
        return {"status": "no_freebies"}

    # --- Step 2: Check which freebies are already present ---
    existing_freebies = [sku for sku in FREEBIE_SKUS if sku.upper() in order_skus]
    missing_freebies = [sku for sku in FREEBIE_SKUS if sku.upper() not in order_skus]

    print(f"🎁 Existing freebies in order: {existing_freebies}")
    print(f"🆕 Missing freebies to add: {missing_freebies}")

    if not missing_freebies:
        print("✅ All freebies already in order — nothing to add.")
        return {"status": "all_freebies_present"}

    # --- Step 3: Fetch variant IDs for missing freebies ---
    variant_ids = []
    for sku in missing_freebies:
        url = f"https://{SHOPIFY_DOMAIN}/admin/api/2025-01/variants.json?sku={sku}"
        print(f"🔍 Fetching variant for SKU: {sku}")
        resp = requests.get(url, headers={"X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN})
        print(f"🧾 Shopify API Response ({resp.status_code}): {resp.text[:300]}")

        if resp.status_code != 200:
            print(f"⚠️ Failed to fetch variant for {sku}")
            continue

        data = resp.json()
        # Safely filter for the exact SKU match
        matching_variants = [
            v for v in data.get("variants", [])
            if v.get("sku", "").strip().upper() == sku.upper()
        ]

        if matching_variants:
            variant_id = matching_variants[0]["id"]
            variant_ids.append(variant_id)
            print(f"✅ Found variant ID {variant_id} for SKU {sku}")
        else:
            print(f"⚠️ No variant found for SKU {sku}")

    # --- Step 4: Log freebies to order metafields ---
    for variant_id in variant_ids:
        add_metafield(order_id, variant_id)

    print(f"✅ Added {len(variant_ids)} missing freebies.")
    return {
        "status": "freebies_added",
        "added_count": len(variant_ids),
        "added_skus": missing_freebies,
        "already_present": existing_freebies
    }


def add_metafield(order_id, variant_id):
    """Adds a metafield to record that a freebie was added."""
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
