
# Dukhr Smart Receipt Match — Streamlit Prototype

This prototype:

1. Uploads a supermarket receipt image.
2. Extracts receipt lines, prices, quantities, store and purchase date.
3. Uploads one or more product images, including multi-product images.
4. Extracts product identity, package size and expiry date.
5. Suggests the three closest receipt matches.
6. Lets the user confirm each price match.
7. Exports the final matched products as JSON.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate        # Windows

pip install -r requirements.txt
streamlit run app.py
```

## API key

Create `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "your-key-here"
```

Never place the real API key directly in `app.py` or commit it to GitHub.

## Streamlit Community Cloud

Add `GEMINI_API_KEY` under:

App settings → Secrets

## Suggested test

Use:
- One clear supermarket receipt.
- One photo containing 2–4 packaged products.
- Products that appear on the uploaded receipt.
- Visible product names, sizes and expiry dates.

This is an MVP matching prototype. Prices and expiry dates should always be reviewed before saving.
