FROM python:3.13-slim AS application

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
# Versions exactes (requirements.lock) : une reconstruction donne la même image.
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock \
    && useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser app.py ./
COPY --chown=appuser:appuser services/ ./services/
COPY --chown=appuser:appuser data/glossaries/ ./data/glossaries/
COPY --chown=appuser:appuser .streamlit/ ./.streamlit/

USER appuser
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"

CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]

FROM application AS tests
USER root
COPY requirements-dev.lock ./
RUN python -m pip install --no-cache-dir -r requirements-dev.lock
COPY --chown=appuser:appuser tests/ ./tests/
COPY --chown=appuser:appuser examples/ ./examples/
COPY --chown=appuser:appuser evaluation/ ./evaluation/
COPY --chown=appuser:appuser pytest.ini ./
USER appuser
HEALTHCHECK NONE
CMD ["python", "-B", "-m", "pytest", "-v", "-p", "no:cacheprovider", "--tb=short"]
