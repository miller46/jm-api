web: gunicorn jm_api.main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --workers ${WEB_CONCURRENCY:-2} --timeout ${GUNICORN_TIMEOUT:-60} --graceful-timeout ${GUNICORN_GRACEFUL_TIMEOUT:-30} --keep-alive ${GUNICORN_KEEP_ALIVE:-5} --max-requests ${GUNICORN_MAX_REQUESTS:-1000} --max-requests-jitter ${GUNICORN_MAX_REQUESTS_JITTER:-100}
worker: python -m jm_api.worker_cli
