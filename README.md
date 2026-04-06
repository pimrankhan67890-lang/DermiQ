# Skin Image Analysis (Free MVP)

A beginner-friendly Streamlit web app MVP:

- Upload **one** skin photo (or use your camera)
- Get **top-3 non-diagnostic** “possible conditions” with confidence
- See a safety message and general next steps
- Get product suggestions (image + reason + buy link) driven by a JSON file

## What this is / isn’t

- **Not a medical diagnosis tool.**
- Predictions are for **education/demo** only and can be wrong due to lighting, angle, skin tone, camera quality, etc.
- If symptoms are severe, spreading, painful, bleeding, rapidly changing, or you’re concerned, seek a licensed clinician.

## Quickstart (run the app)

1. Create and activate a virtual environment (Windows PowerShell):
   - `python -m venv .venv`
   - `.\.venv\Scripts\Activate.ps1`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Start Streamlit:
   - `streamlit run app.py`

The app **still opens even without a trained model**. If no model is present (or TensorFlow isn’t installed), it uses a lightweight heuristic fallback so you can try the UI end-to-end.

If product images don’t load from the internet, the app automatically generates local placeholder images in `assets/products/`.

---

## Premium 3D landing (runs without Node)

This repo includes a standalone cinematic landing page in `landing/` (pure HTML/CSS/JS + WebGL).

- `cd landing`
- `python -m http.server 5173`
- Open `http://127.0.0.1:5173`

If you deploy the landing separately from the backend, set `window.DERMIQ_API_BASE` in `landing/config.js` to your public backend URL.

---

# Next.js Website (Recommended)

If you want a **real website** that you can deploy so users can visit from mobile/desktop, use the Next.js frontend + FastAPI backend included in this repo.

## Local run (website)

### 1) Start the backend API (FastAPI)

In PowerShell from the repo root:

- `python -m venv .venv`
- `.\.venv\Scripts\Activate.ps1`
- `pip install -r backend/requirements.txt`
- `python -m uvicorn backend.main:app --reload --port 8000`

Health check:

- `http://localhost:8000/health`

### 2) Start the frontend (Next.js)

Install Node.js LTS (18+), then:

- `cd frontend`
- `npm install`
- `npm run dev`

Open:

- `http://localhost:3000`

Notes:
- Camera capture works best over **HTTPS** when deployed.
- Frontend calls the backend using `NEXT_PUBLIC_API_URL` (see `frontend/.env.example`).
- For the backend, set `CORS_ALLOW_ORIGINS` to your real frontend URL(s) (comma-separated) in production.

## Deploy for free (simple path)

One reliable free-tier setup:

1. Deploy the backend on **Render** (free tier) as a Python web service.
   - Start command: `python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - Install command:
     - Without ML (heuristic fallback): `pip install -r backend/requirements.txt`
     - With trained model (TensorFlow): `pip install -r backend/requirements-ml.txt`
2. Deploy the frontend on **Vercel** (free tier) from the `frontend/` directory.
   - Add env var: `NEXT_PUBLIC_API_URL=https://<your-render-backend-url>`

This gives you a public URL where people can upload/take a photo and see results.

## Train a real model (optional)

If you have a dataset, place it like this:

```
data/
  train/
    acne/
      img1.jpg
      img2.jpg
    eczema/
      img1.jpg
    rosacea/
      img1.jpg
```

Then:

- Install TensorFlow (only needed for training / loading a saved Keras model).
  - **Important:** TensorFlow may not support the latest Python versions. If `pip install tensorflow` fails, use Python **3.10/3.11** in your virtualenv.
  - `pip install tensorflow`
- Train:
  - `python train.py --dataset data/train --epochs 8`

Optional helper scripts (Windows PowerShell):

- `tools/check_model.ps1` — shows whether a trained model is present (otherwise the app uses heuristic fallback)
- `tools/train_model.ps1` — creates a venv, installs deps + TensorFlow, and trains to `models/skin_model.h5`
- `tools/prefetch_imagenet_weights.ps1` — downloads MobileNetV2 ImageNet weights into `.keras_cache/` (improves accuracy and avoids network at train time)

Outputs:

- `models/skin_model.keras`
- `models/labels.json`

Restart the app after training and it will automatically use the saved model.

## Product recommendations (JSON)

Products live in `products.json` (the app also supports `product.json`).

Each product looks like:

```json
{
  "id": "gentle-cleanser",
  "name": "Gentle Cleanser (Fragrance-Free)",
  "conditions": ["acne", "rosacea"],
  "reason": "Cleans without stripping; helps reduce irritation.",
  "image_url": "https://…",
  "buy_url": "https://…"
}
```

The app filters products by the **top predicted label** and renders them as cards.

## Repository layout

- `app.py` — Streamlit UI + prediction + product cards (with fallbacks)
- `train.py` — Optional TensorFlow training script (skips training if dataset is missing)
- `products.json` / `product.json` — Product catalog for recommendations
- `models/` — Model + labels (contains a default `labels.json`)
- `.streamlit/config.toml` — Simple theme configuration

## Notes

- Keep photos clear and well-lit.
- Avoid uploading personally identifying photos if you don’t want them on your device; this MVP does not upload to a server by itself, but your environment may vary.

## Production hardening (recommended)

Backend environment variables (FastAPI):

- `CORS_ALLOW_ORIGINS` — comma-separated allowlist (set to your deployed frontend origin). Default: `*` (dev only).
- `MAX_UPLOAD_BYTES` — maximum upload size (bytes). Default: `10485760` (10MB).
- `MAX_IMAGE_PIXELS` — maximum image resolution (width × height). Default: `12000000`.
- `PREDICT_RATE_MAX` — max `/predict` requests per IP per window. Default: `30`.
- `PREDICT_RATE_WINDOW_SECONDS` — rate limit window in seconds. Default: `600`.

Frontend environment variables (Next.js):

- `NEXT_PUBLIC_API_URL` — backend base URL (required for production).
- `NEXT_PUBLIC_CONTACT_EMAIL` — footer contact email.
- `NEXT_PUBLIC_GITHUB_URL` — optional footer link.
