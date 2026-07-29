
import json
import os
import re
from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st
from PIL import Image
from rapidfuzz import fuzz
from google import genai
from google.genai import types

st.set_page_config(page_title="Dukhr Smart Receipt Match", page_icon="🧾", layout="wide")

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "store_name": {"type": "string"},
        "purchase_date": {"type": "string"},
        "currency": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "receipt_id": {"type": "string"},
                    "raw_text": {"type": "string"},
                    "product_name": {"type": "string"},
                    "brand": {"type": "string"},
                    "size": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit_price": {"type": "number"},
                    "total_price": {"type": "number"},
                    "is_food": {"type": "boolean"},
                },
                "required": [
                    "receipt_id", "raw_text", "product_name", "brand", "size",
                    "quantity", "unit_price", "total_price", "is_food"
                ],
            },
        },
    },
    "required": ["store_name", "purchase_date", "currency", "items"],
}

PRODUCT_SCHEMA = {
    "type": "object",
    "properties": {
        "products": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "product_name": {"type": "string"},
                    "brand": {"type": "string"},
                    "size": {"type": "string"},
                    "expiry_date": {"type": "string"},
                    "category": {"type": "string"},
                },
                "required": [
                    "product_id", "product_name", "brand", "size",
                    "expiry_date", "category"
                ],
            },
        }
    },
    "required": ["products"],
}

def get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY", "")

    try:
        api_key = st.secrets.get("GEMINI_API_KEY", api_key)
    except Exception:
        # لا يوجد ملف Secrets، لذلك نستخدم Environment Variable
        pass

    if not api_key:
        st.error(
            "GEMINI_API_KEY is missing. "
            "Open Manage app → Settings → Secrets and add:\n\n"
            'GEMINI_API_KEY = "your-key-here"'
        )
        st.stop()

    return genai.Client(api_key=api_key)


def uploaded_to_image(uploaded_file) -> Image.Image:
    return Image.open(BytesIO(uploaded_file.getvalue())).convert("RGB")


def extract_json_from_image(image: Image.Image, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    client = get_client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[prompt, image],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=schema,
            temperature=0.1,
        ),
    )
    return json.loads(response.text)


def normalize(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", text)
    return " ".join(text.split())


def token_score(product: dict[str, Any], receipt_item: dict[str, Any]) -> float:
    product_text = normalize(
        f"{product.get('brand', '')} {product.get('product_name', '')} {product.get('size', '')}"
    )
    receipt_text = normalize(
        f"{receipt_item.get('brand', '')} {receipt_item.get('product_name', '')} "
        f"{receipt_item.get('size', '')} {receipt_item.get('raw_text', '')}"
    )

    name_score = fuzz.token_set_ratio(product_text, receipt_text)
    brand_score = fuzz.partial_ratio(
        normalize(product.get("brand", "")),
        normalize(f"{receipt_item.get('brand', '')} {receipt_item.get('raw_text', '')}")
    ) if product.get("brand") else 50
    size_score = fuzz.partial_ratio(
        normalize(product.get("size", "")),
        normalize(f"{receipt_item.get('size', '')} {receipt_item.get('raw_text', '')}")
    ) if product.get("size") else 50

    return round((name_score * 0.65) + (brand_score * 0.2) + (size_score * 0.15), 1)


def build_suggestions(products: list[dict[str, Any]], receipt_items: list[dict[str, Any]]):
    food_items = [item for item in receipt_items if item.get("is_food", True)]
    suggestions = {}
    for product in products:
        ranked = sorted(
            [
                {
                    "receipt_id": item["receipt_id"],
                    "label": (
                        f"{item['product_name']} | {item['raw_text']} | "
                        f"{item['total_price']:.2f}"
                    ),
                    "score": token_score(product, item),
                    "item": item,
                }
                for item in food_items
            ],
            key=lambda x: x["score"],
            reverse=True,
        )
        suggestions[product["product_id"]] = ranked[:3]
    return suggestions


st.title("Dukhr — Smart Receipt Match")
st.caption("Prototype: receipt extraction + product multi-scan + price matching")

with st.sidebar:
    st.subheader("Prototype settings")
    st.write(f"Model: `{MODEL_NAME}`")
    auto_threshold = st.slider("Auto-match threshold", 50, 100, 85)
    st.info("For testing only. Always review prices and dates before saving.")

receipt_file = st.file_uploader(
    "1. Upload receipt image",
    type=["jpg", "jpeg", "png", "webp"],
    key="receipt",
)
product_files = st.file_uploader(
    "2. Upload one or more product images",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
    key="products",
)

if receipt_file:
    st.image(receipt_file, caption="Receipt", width=350)

if product_files:
    cols = st.columns(min(3, len(product_files)))
    for idx, file in enumerate(product_files):
        with cols[idx % len(cols)]:
            st.image(file, caption=file.name, use_container_width=True)

if st.button("Analyze and match", type="primary", disabled=not (receipt_file and product_files)):
    with st.spinner("Reading receipt and products..."):
        receipt_image = uploaded_to_image(receipt_file)
        receipt_prompt = """
        You are extracting supermarket receipt data for a food-waste app in the UAE.
        Read every visible receipt line carefully.
        Return food and non-food lines, but mark is_food accurately.
        Preserve abbreviated receipt text in raw_text.
        Infer a clean product_name and brand only when reasonably supported.
        Use numeric values without currency symbols.
        quantity defaults to 1 if not shown.
        unit_price equals total_price when quantity is 1.
        Dates must be YYYY-MM-DD when confidently readable, otherwise an empty string.
        Create stable IDs such as R1, R2, R3.
        """
        receipt_data = extract_json_from_image(receipt_image, receipt_prompt, RECEIPT_SCHEMA)

        all_products = []
        for index, product_file in enumerate(product_files, start=1):
            product_image = uploaded_to_image(product_file)
            product_prompt = f"""
            Analyze this image for the Dukhr food-expiry app.
            Identify every distinct food product visible, including multiple products in one image.
            Read product name, brand, package size and expiry date.
            Expiry dates must be YYYY-MM-DD when confidently readable, otherwise an empty string.
            Do not invent dates.
            Create unique IDs beginning with P{index}_.
            """
            product_data = extract_json_from_image(product_image, product_prompt, PRODUCT_SCHEMA)
            all_products.extend(product_data.get("products", []))

        st.session_state["receipt_data"] = receipt_data
        st.session_state["products"] = all_products
        st.session_state["suggestions"] = build_suggestions(
            all_products, receipt_data.get("items", [])
        )

if "receipt_data" in st.session_state:
    receipt_data = st.session_state["receipt_data"]
    products = st.session_state["products"]
    suggestions = st.session_state["suggestions"]

    st.divider()
    st.subheader("Receipt results")
    st.write(
        f"Store: **{receipt_data.get('store_name') or 'Unknown'}**  |  "
        f"Date: **{receipt_data.get('purchase_date') or 'Unknown'}**  |  "
        f"Currency: **{receipt_data.get('currency') or 'AED'}**"
    )
    st.dataframe(pd.DataFrame(receipt_data.get("items", [])), use_container_width=True)

    st.subheader("Confirm product matches")
    confirmed = []

    receipt_lookup = {
        item["receipt_id"]: item for item in receipt_data.get("items", [])
    }

    for product in products:
        st.markdown(
            f"#### {product.get('brand', '')} {product.get('product_name', '')}"
        )
        st.caption(
            f"Size: {product.get('size') or 'Unknown'} · "
            f"Expiry: {product.get('expiry_date') or 'Not detected'}"
        )

        options = suggestions.get(product["product_id"], [])
        option_map = {"No matching receipt item": None}
        for suggestion in options:
            option_map[
                f"{suggestion['label']} · Match {suggestion['score']}%"
            ] = suggestion

        best_score = options[0]["score"] if options else 0
        default_index = 1 if options and best_score >= auto_threshold else 0

        selected_label = st.selectbox(
            "Receipt match",
            list(option_map.keys()),
            index=default_index,
            key=f"match_{product['product_id']}",
        )
        selected = option_map[selected_label]

        if selected:
            item = selected["item"]
            confirmed.append(
                {
                    **product,
                    "receipt_item_id": item["receipt_id"],
                    "receipt_text": item["raw_text"],
                    "purchase_price": item["total_price"],
                    "purchase_quantity": item["quantity"],
                    "purchase_date": receipt_data.get("purchase_date", ""),
                    "store_name": receipt_data.get("store_name", ""),
                    "currency": receipt_data.get("currency", "AED"),
                    "match_confidence": selected["score"],
                    "match_status": (
                        "auto" if selected["score"] >= auto_threshold else "confirmed"
                    ),
                }
            )
        else:
            confirmed.append(
                {
                    **product,
                    "receipt_item_id": None,
                    "purchase_price": None,
                    "match_confidence": 0,
                    "match_status": "unmatched",
                }
            )

    st.subheader("Final data to save")
    st.dataframe(pd.DataFrame(confirmed), use_container_width=True)

    json_payload = json.dumps(confirmed, ensure_ascii=False, indent=2)
    st.download_button(
        "Download matched JSON",
        data=json_payload,
        file_name="dukhr_matched_products.json",
        mime="application/json",
    )
