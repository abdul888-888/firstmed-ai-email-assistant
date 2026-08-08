FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy backend code
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY backend/ .

# Set Python path
ENV PYTHONPATH=/app

# Expose port (Railway will override with $PORT)
EXPOSE 8000

# Default command: run FastAPI (Railway uses $PORT env var)
# Note: Run migrations manually first, then start API
CMD ["sh", "-c", "python run_migrations.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} || tail -f /dev/null"]
