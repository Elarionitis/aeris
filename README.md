# Aeris 🌍

> **AI-powered air-quality intelligence for forecasting pollution, identifying potential sources, prioritizing inspections, and delivering actionable citizen advisories.**

Aeris is a full-stack **air-quality decision-support platform** that transforms environmental data into actionable intelligence.

Instead of only showing the current AQI, Aeris helps answer:

- 🔮 What will the AQI look like over the next 1–72 hours?
- 🔎 What factors may be contributing to the pollution?
- 🚨 Which locations should authorities investigate first?
- 🧑‍🤝‍🧑 What should citizens do right now?

**Core workflow:**

```text
Forecast → Explain → Prioritize → Act
```

---

## ✨ Features

### 🔮 AQI Forecasting
- Ward-level AQI forecasting for up to 72 hours
- Historical, weather, and contextual features
- XGBoost-based forecasting
- Recursive multi-step predictions
- Prediction intervals

### 🔎 Pollution Attribution
- Estimates potential contributions from:
  - Traffic
  - Construction
  - Industrial activity
  - Thermal anomalies
- Uses **Non-Negative Least Squares (NNLS)** for interpretable attribution
- Provides confidence scores with attribution results

### 🚨 Enforcement Prioritization
Ranks locations for potential inspection using factors such as:

- AQI severity
- Pollution persistence
- Estimated source contribution
- Nearby source density
- Distance to potential sources

### 🧑‍🤝‍🧑 Citizen Advisory
Generates contextual, plain-language air-quality guidance with multilingual support.

### 🗺️ Interactive Dashboard
- Ward-level AQI visualization
- Interactive map
- 72-hour forecasts
- Pollution attribution
- Inspection priority queue
- Citizen advisories

---

## 🏗️ Architecture

```text
        Environmental Data
                │
                ▼
        Data Ingestion
                │
                ▼
        Feature Engineering
                │
       ┌────────┼────────┐
       ▼        ▼        ▼
   Forecast  Attribution  Priority
       │        │        │
       └────────┼────────┘
                ▼
             FastAPI
                │
        ┌───────┴───────┐
        ▼               ▼
   React Dashboard   AI Advisory
```

Aeris combines air-quality, weather, traffic, construction, industrial,
and thermal-anomaly signals into a unified intelligence pipeline.

---

## 🛠️ Tech Stack

**Backend**
- Python
- FastAPI
- Pandas / NumPy
- Scikit-learn / SciPy
- XGBoost
- Prophet

**Frontend**
- React
- Vite
- Tailwind CSS
- Recharts
- Leaflet

**Infrastructure**
- Docker
- Docker Compose

**External Data / Services**
- OpenAQ
- OpenWeather
- NASA FIRMS
- OpenStreetMap
- Anthropic API

---

## 📁 Project Structure

```text
aeris/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── ingestion/
│   │   ├── models/
│   │   └── main.py
│   ├── tests/
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   └── package.json
│
├── data/
├── docs/
├── scripts/
├── docker-compose.yml
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm
- Docker *(optional)*

### Clone

```bash
git clone https://github.com/<your-username>/aeris.git
cd aeris
```

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API:

```text
http://localhost:8000
```

API documentation:

```text
http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard:

```text
http://localhost:5173
```

### Docker

```bash
docker compose up --build
```

---

## 🔌 API

| Endpoint | Purpose |
|---|---|
| `/health` | Health check |
| `/wards` | Ward information |
| `/forecast/{ward_id}` | AQI forecast |
| `/attribution/{ward_id}` | Pollution attribution |
| `/enforcement/priority-queue` | Inspection priorities |
| `/advisory/{ward_id}` | Citizen advisory |

Interactive API documentation is available at `/docs`.

---

## 🧪 Testing

Run the backend test suite:

```bash
cd backend
pytest tests -q
```

Tests cover forecasting, attribution, enforcement scoring, advisory generation,
API contracts, and data-ingestion components.

---

## 📊 Model Evaluation

Aeris includes a controlled synthetic evaluation comparing its forecasting
model against a persistence baseline.

| Horizon | Baseline RMSE | Model RMSE |
|---:|---:|---:|
| 1h | 21.91 | 0.38 |
| 3h | 22.45 | 0.39 |
| 6h | 23.30 | 0.51 |
| 12h | 23.32 | 0.40 |
| 24h | 22.26 | 0.27 |

> **Note:** These results are from a synthetic evaluation and should not be
> interpreted as production accuracy on real-world air-quality data.

---

## ⚠️ Responsible Use

Aeris is a **decision-support prototype**, not an autonomous enforcement system.

- Attribution represents estimated associations, not definitive causality.
- Forecast performance requires validation on real-world data.
- Inspection recommendations require human verification.
- Generated advisories should complement official public-health guidance.

---

## 🗺️ Roadmap

- [x] AQI forecasting
- [x] Pollution attribution
- [x] Enforcement prioritization
- [x] Citizen advisory
- [x] Interactive dashboard
- [x] REST API
- [x] Docker support
- [x] Automated tests
- [ ] Live-data validation
- [ ] Improved source attribution
- [ ] Model monitoring
- [ ] Production deployment
- [ ] Support for additional cities

---

## 🎯 Vision

> **Don't just report pollution. Turn pollution data into decisions.**

Aeris aims to bridge the gap between environmental monitoring and real-world
action by connecting **forecasting, attribution, prioritization, and citizen
guidance** in one platform.

---

**Aeris - From air-quality data to actionable intelligence.**
