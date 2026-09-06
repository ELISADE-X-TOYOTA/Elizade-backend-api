FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# WEB_CONCURRENCY is read by BOTH uvicorn (worker processes) and the app's
# pool sizing, so the two can never disagree — which is the failure this
# guards against: adding workers without shrinking the pool multiplies the
# connection count and reproduces the pool-exhaustion outage on purpose.
#
# Default 1. Raise it only together with DB_CONNECTION_BUDGET / REPLICA_COUNT,
# and see `app/core/database.py` for the arithmetic they feed.
ENV WEB_CONCURRENCY=1

# Shell form so ${WEB_CONCURRENCY} is expanded at runtime — the exec form would
# pass the literal string and uvicorn would refuse to start.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY}
