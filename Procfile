web: cd services/trading-backend && BACKGROUND_WORKERS_ENABLED=false uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: cd services/trading-backend && BACKGROUND_WORKERS_ENABLED=true python -m src.worker
