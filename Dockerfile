FROM python:3.11-slim
ARG BUILD_REVISION=local
LABEL org.opencontainers.image.revision=$BUILD_REVISION
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --no-create-home app
COPY app ./app
COPY tests ./tests
RUN RS_SERVICE_TOKEN=build-test-token-at-least-32-characters python -m unittest discover -s tests && rm -rf tests
USER 10001:10001
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/healthz',timeout=3)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090", "--no-access-log"]
