# Observability Stack (Prometheus + Grafana + Jaeger)

This service ships with:

- Structured JSON logs (structlog)
- Correlation IDs (`X-Request-ID`)
- OpenTelemetry tracing (Jaeger exporter)
- Prometheus metrics at `/metrics`

## Environment variables

```bash
JM_API_LOG_LEVEL=INFO
JM_API_LOG_JSON=true
JM_API_LOG_SAMPLE_RATE=1.0
JM_API_SLOW_QUERY_THRESHOLD_MS=500

JM_API_TRACING_ENABLED=true
JM_API_TRACING_SERVICE_NAME=jm-api
JM_API_TRACING_SERVICE_VERSION=0.1.0
JM_API_TRACING_JAEGER_HOST=localhost
JM_API_TRACING_JAEGER_PORT=6831

JM_API_METRICS_ENABLED=true
JM_API_METRICS_PATH=/metrics
```

## Local stack

```bash
docker compose -f docker-compose.observability.yml up -d
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Jaeger UI: http://localhost:16686

Run API locally and point Jaeger host/port to `localhost:6831`.

## Prometheus scrape config

`docker-compose.observability.yml` mounts `ops/prometheus/prometheus.yml` with `/metrics` scraping.

## Metrics exposed

- `http_requests_total{service,version,method,endpoint,status}`
- `http_request_duration_seconds_bucket` (histogram for p50/p95/p99)
- `http_request_errors_total{...}`

Example PromQL:

```promql
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))
```

```promql
sum(rate(http_request_errors_total[5m])) by (endpoint) / sum(rate(http_requests_total[5m])) by (endpoint)
```
