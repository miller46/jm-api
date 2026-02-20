.PHONY: migrate migrate-create migrate-downgrade

migrate:
	uv run alembic upgrade head

migrate-create:
	@if [ -z "$(msg)" ]; then echo "Usage: make migrate-create msg='description'"; exit 1; fi
	uv run alembic revision --autogenerate -m "$(msg)"

migrate-downgrade:
	uv run alembic downgrade -1
