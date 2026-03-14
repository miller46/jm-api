FROM golang:1.24-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /api ./cmd/api
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /worker ./cmd/worker

FROM alpine:3.20

RUN apk --no-cache add ca-certificates tzdata

COPY --from=builder /api /usr/local/bin/api
COPY --from=builder /worker /usr/local/bin/worker
COPY --from=builder /app/internal/db/migrate /migrations

EXPOSE 8000

<<<<<<< Updated upstream
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,sys,urllib.request; prefix=os.getenv('JM_API_API_V1_PREFIX','/api/v1'); url=f'http://127.0.0.1:{os.getenv('PORT','8000')}{prefix}/live'; sys.exit(0 if urllib.request.urlopen(url, timeout=3).status==200 else 1)"

CMD ["sh", "-c", "gunicorn jm_api.main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-4}"]
=======
CMD ["api"]
>>>>>>> Stashed changes
