# 16 — Tech Stack & Dependency Justification

## 🛠️ Complete Technical Stack Table

| System Layer | Technology / Library | Version | Why Chosen / Industry Advantage | Where Used in Project |
| :--- | :--- | :--- | :--- | :--- |
| **Language** | Python | 3.12+ | Universal language for data engineering, ML modeling, and web backend APIs | Core language across entire codebase |
| **Backend Framework**| FastAPI | 0.128.8 | High-performance asynchronous ASGI web framework with automatic Swagger docs | `backend/app/main.py` & `routes/` |
| **ASGI Web Server** | Uvicorn | 0.39.0 | Lightning-fast ASGI HTTP server implementation | Backend process listener (Port 8000) |
| **Frontend UI** | Streamlit | 1.50.0 | Python-native web application framework for rapid interactive dashboard rendering | `frontend/app.py` (Port 8501) |
| **Charting Engine** | Plotly | 6.7.0 | Dynamic, interactive JavaScript charts rendered seamlessly via Python | Forecast line graphs, radar charts, histograms |
| **Data Manipulation**| Pandas | 2.3.3 | Industry-standard library for time-series aggregation, filtering, and resampling | `forecasting.py`, `synthetic_data.py`, `upload.py` |
| **Numerical Math** | NumPy | 2.0.2 | High-speed array operations, linear algebra, and statistical sampling | ML regression feature matrix & Monte Carlo |
| **Time-Series ML** | Holt-Winters / Ridge | Custom | Exponential smoothing + L2 regularized regression for seasonal time-series | `forecasting.py:get_enhanced_cargo_forecast()` |
| **Data Models** | Pydantic | 2.13.4 | Strict data parsing, validation, and JSON schema serialization | FastAPI request/response validation |
| **Containerization** | Docker / Compose | 2.x | Multi-container orchestration guaranteeing identical dev & prod execution | `Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.yml` |

---

## 💡 Technology Choice Justification vs. Alternatives

### 1. FastAPI vs. Flask / Django
* **Why FastAPI?**: FastAPI is asynchronous by design, provides automatic interactive OpenAPI Swagger documentation at `/docs`, and serializes Pydantic models up to 300% faster than traditional Flask.

### 2. Streamlit vs. React / Angular
* **Why Streamlit?**: Allows pure Python developers to build complex, responsive web UI layouts with interactive sliders, dataframes, and Plotly charts without needing Node.js or complex state-management boilerplate.

### 3. Holt-Winters + Ridge Regression vs. Deep Learning (LSTM / Prophet)
* **Why Holt-Winters + Ridge?**: Monthly port traffic datasets (1,354 records) are structured tabular time-series. Deep learning models like LSTM require millions of data points and tend to overfit small port datasets. Ridge Regression with L2 regularization guarantees stable, explainable weights with zero overfitting.
