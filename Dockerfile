FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
# Live Modes refuse to register without their evaluation suite (src/agent/registry.py).
COPY evals ./evals
# Startup recomputes the Gate A fingerprint for evaluated MODE_MODELS / non-Gemini routes
# (src/evaluation/model_policy.py); it hashes these too (src/evaluation/gate_a.py).
COPY migrations ./migrations
COPY scripts/run_gate_a_eval.py ./scripts/run_gate_a_eval.py

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV PORT=8080
EXPOSE 8080

CMD uvicorn src.main:app --host 0.0.0.0 --port $PORT
