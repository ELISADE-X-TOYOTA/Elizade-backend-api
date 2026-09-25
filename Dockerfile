FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Listen on the port the HOST asks for, falling back to 8000 locally.
#
# This was hardcoded to 8000. Railway injects $PORT and routes to it, so the
# app came up perfectly — "Application startup complete", uvicorn listening —
# and the edge proxy, pointed at a different port, answered every request
# with 502 "Application failed to respond". That string reached customers on
# the login screen, under an email field, looking like a validation error.
#
# The old service survived it only because its target port had been set to
# 8000 by hand in the dashboard; a new service does not inherit that, which
# is why a working deploy looked dead the moment the backend moved.
#
# Shell form so ${PORT} is expanded, and `exec` so uvicorn stays PID 1 and
# still receives SIGTERM for a graceful shutdown.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
