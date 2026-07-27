# Railway service definitions
# Each line defines a deployable service

# FastAPI Backend API (main HTTP service)
api: cd backend && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT

# Celery Worker (background task processing)
worker: cd backend && celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=4

# Celery Beat (periodic task scheduler)
beat: cd backend && celery -A app.workers.celery_app.celery_app beat --loglevel=info

# Next.js Frontend (optional - can also deploy separately)
# web: cd frontend && npm run build && npm start
