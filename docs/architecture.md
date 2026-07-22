# Architecture

## Overview
- Backend: FastAPI service for ingestion, model orchestration, and REST APIs.
- Frontend: React + Vite dashboard for AQI analysis and forecasting.
- Data: Cached raw inputs and processed datasets for repeatable experimentation.
- Notebooks: Exploratory development for attribution and forecasting work.

## Planned Flow
1. Pull AQI and meteorology data from external sources.
2. Normalize and cache the raw datasets.
3. Run forecasting and attribution logic in the backend.
4. Expose the results through REST endpoints.
5. Visualize live and forecast values in the frontend.
