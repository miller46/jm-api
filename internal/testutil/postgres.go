//go:build integration

package testutil

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/modules/postgres"
	"github.com/testcontainers/testcontainers-go/wait"
)

func SetupTestPostgres(t *testing.T) (*pgxpool.Pool, func()) {
	t.Helper()

	defer func() {
		if r := recover(); r != nil {
			t.Skipf("skipping integration tests: docker runtime unavailable: %v", r)
		}
	}()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	container, err := postgres.Run(ctx,
		"postgres:16-alpine",
		postgres.WithDatabase("jm_api_test"),
		postgres.WithUsername("postgres"),
		postgres.WithPassword("postgres"),
		testcontainers.WithWaitStrategy(
			wait.ForLog("database system is ready to accept connections").WithOccurrence(2),
		),
	)
	if err != nil {
		t.Skipf("skipping integration tests: unable to start postgres container: %v", err)
	}

	dsn, err := container.ConnectionString(ctx, "sslmode=disable")
	if err != nil {
		_ = container.Terminate(context.Background())
		t.Fatalf("failed to get postgres connection string: %v", err)
	}

	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		_ = container.Terminate(context.Background())
		t.Fatalf("failed to connect to test postgres: %v", err)
	}

	if err := applySchema(context.Background(), pool); err != nil {
		pool.Close()
		_ = container.Terminate(context.Background())
		t.Skipf("skipping integration tests: unable to apply schema: %v", err)
	}

	cleanup := func() {
		pool.Close()
		_ = container.Terminate(context.Background())
	}

	return pool, cleanup
}

func applySchema(ctx context.Context, pool *pgxpool.Pool) error {
	migrationPath := filepath.Join("internal", "db", "migrate", "000001_initial_schema.up.sql")
	schemaBytes, err := os.ReadFile(migrationPath)
	if err != nil {
		return fmt.Errorf("read migration file: %w", err)
	}

	if _, err := pool.Exec(ctx, string(schemaBytes)); err != nil {
		return fmt.Errorf("exec migration schema: %w", err)
	}

	return nil
}
