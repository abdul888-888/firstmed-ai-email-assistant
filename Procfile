# Railway service definitions
# Each line defines a deployable service

# FastAPI Backend API (main HTTP service)
api: exec sh -c 'alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'

# Celery Worker (background task processing)
worker: celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=4

# Celery Beat (periodic task scheduler)
beat: celery -A app.workers.celery_app.celery_app beat --loglevel=info

# Next.js Frontend (optional - can also deploy separately)
# web: cd frontend && npm run build && npm start
