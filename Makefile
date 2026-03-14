.PHONY: build test run worker migrate sqlc lint clean

build:
	go build -o bin/api ./cmd/api
	go build -o bin/worker ./cmd/worker

test:
	go test ./... -v -count=1

run:
	go run ./cmd/api

worker:
	go run ./cmd/worker

migrate-up:
	migrate -path internal/db/migrate -database "$$JM_API_DATABASE_URL" up

migrate-down:
	migrate -path internal/db/migrate -database "$$JM_API_DATABASE_URL" down

sqlc:
	sqlc generate

lint:
	go vet ./...

clean:
	rm -rf bin/
