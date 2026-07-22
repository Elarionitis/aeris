# AQI Intelligence

AQI Intelligence is a hackathon scaffold for an air-quality monitoring and forecasting product.

## Structure

- `backend/` FastAPI service for ingestion, forecasting, attribution, and REST APIs
- `frontend/` React + Vite dashboard with Tailwind and Recharts
- `data/` cached and raw datasets for experimentation
- `notebooks/` exploration notebooks for model development
- `docs/` architecture notes, deck outline, and video script draft

## Local development

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Docker Compose

From the repository root:

```bash
docker compose up --build
```