package config

import (
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func setEnv(t *testing.T, key, value string) {
	t.Helper()
	t.Setenv(key, value)
}

func TestLoad_Defaults(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")

	cfg, err := Load()
	require.NoError(t, err)

	assert.Equal(t, "jm-api", cfg.AppName)
	assert.Equal(t, "0.1.0", cfg.AppVersion)
	assert.Equal(t, "development", cfg.Environment)
	assert.False(t, cfg.Debug)
	assert.Equal(t, "/api/v1", cfg.APIV1Prefix)
	assert.Equal(t, "X-Request-ID", cfg.RequestIDHeader)
	assert.True(t, cfg.SecurityHeadersEnabled)
	assert.Equal(t, "HS256", cfg.JWTAlgorithm)
	assert.Equal(t, 15, cfg.JWTAccessTokenExpireMin)
	assert.Equal(t, 7, cfg.JWTRefreshTokenExpireDays)
	assert.Equal(t, 120, cfg.RateLimitAPIPerMinute)
	assert.Equal(t, 20, cfg.DBPoolMaxConns)
	assert.Equal(t, 2, cfg.DBPoolMinConns)
	assert.Equal(t, 8000, cfg.ServerPort)
	assert.True(t, cfg.DBConnectRetryEnabled)
	assert.Equal(t, 5, cfg.DBConnectRetryMaxAttempts)
	assert.Equal(t, time.Second, cfg.DBConnectRetryInitialDelay)
	assert.Equal(t, 30*time.Second, cfg.DBConnectRetryMaxDelay)
}

func TestLoad_MissingDatabaseURL(t *testing.T) {
	os.Unsetenv("JM_API_DATABASE_URL")
	_, err := Load()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "JM_API_DATABASE_URL is required")
}

func TestLoad_ProductionValidation_DoesNotValidateDatabaseScheme(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "mysql://localhost/test")
	setEnv(t, "JM_API_ENVIRONMENT", "production")
	setEnv(t, "JM_API_JWT_SECRET_KEY", "this-is-a-very-long-secret-key-for-production-use")
	setEnv(t, "JM_API_RATE_LIMIT_STORAGE_URI", "redis://localhost")
	setEnv(t, "JM_API_BOTS_WRITE_ADMIN_ONLY", "true")

	_, err := Load()
	require.NoError(t, err)
}

func TestLoad_ProductionValidation_WeakJWT(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_ENVIRONMENT", "production")
	setEnv(t, "JM_API_JWT_SECRET_KEY", "short")
	setEnv(t, "JM_API_RATE_LIMIT_STORAGE_URI", "redis://localhost")
	setEnv(t, "JM_API_BOTS_WRITE_ADMIN_ONLY", "true")

	_, err := Load()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "JWT secret key must be >= 32 bytes")
}

func TestLoad_ProductionValidation_MemoryRateLimit(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_ENVIRONMENT", "staging")
	setEnv(t, "JM_API_JWT_SECRET_KEY", "this-is-a-very-long-secret-key-for-production-use")

	_, err := Load()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "rate limit storage must use Redis")
}

func TestLoad_ProductionValidation_BotsWriteNotAdmin(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_ENVIRONMENT", "production")
	setEnv(t, "JM_API_JWT_SECRET_KEY", "this-is-a-very-long-secret-key-for-production-use")
	setEnv(t, "JM_API_RATE_LIMIT_STORAGE_URI", "redis://localhost")
	setEnv(t, "JM_API_BOTS_WRITE_ADMIN_ONLY", "false")

	_, err := Load()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "bots write must be admin-only")
}

func TestLoad_ProductionValidation_TrustProxyNoCIDR(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_ENVIRONMENT", "production")
	setEnv(t, "JM_API_JWT_SECRET_KEY", "this-is-a-very-long-secret-key-for-production-use")
	setEnv(t, "JM_API_RATE_LIMIT_STORAGE_URI", "redis://localhost")
	setEnv(t, "JM_API_BOTS_WRITE_ADMIN_ONLY", "true")
	setEnv(t, "JM_API_TRUST_PROXY_HEADERS", "true")

	_, err := Load()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "trusted proxy headers requires trusted CIDR list")
}

func TestLoad_InvalidSampleRate(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_LOG_SAMPLE_RATE", "0")

	_, err := Load()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "LOG_SAMPLE_RATE")
}

func TestLoad_JWTSigningKeys(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_JWT_SIGNING_KEYS", "key1,key2,key3")

	cfg, err := Load()
	require.NoError(t, err)
	assert.Equal(t, []string{"key1", "key2", "key3"}, cfg.JWTSigningKeys)
}

func TestLoad_TrustedProxyCIDRs(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_TRUSTED_PROXY_CIDRS", "10.0.0.0/8, 172.16.0.0/12")

	cfg, err := Load()
	require.NoError(t, err)
	assert.Len(t, cfg.TrustedProxyCIDRs, 2)
}

func TestLoad_InvalidCIDR(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_TRUSTED_PROXY_CIDRS", "not-a-cidr")

	_, err := Load()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid trusted proxy CIDR")
}

func TestLoad_CustomValues(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_APP_NAME", "custom-api")
	setEnv(t, "JM_API_SERVER_PORT", "9000")
	setEnv(t, "JM_API_DEBUG", "true")
	setEnv(t, "JM_API_ALLOW_ORIGINS", "http://localhost:3000,http://example.com")
	setEnv(t, "JM_API_DB_POOL_MAX_CONNS", "50")
	setEnv(t, "JM_API_DB_POOL_MIN_CONNS", "10")

	cfg, err := Load()
	require.NoError(t, err)
	assert.Equal(t, "custom-api", cfg.AppName)
	assert.Equal(t, 9000, cfg.ServerPort)
	assert.True(t, cfg.Debug)
	assert.Equal(t, []string{"http://localhost:3000", "http://example.com"}, cfg.AllowOrigins)
	assert.Equal(t, 50, cfg.DBPoolMaxConns)
	assert.Equal(t, 10, cfg.DBPoolMinConns)
}

func TestLoad_DBPoolLegacyEnvKeys(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "DB_POOL_MAX_CONNS", "40")
	setEnv(t, "DB_POOL_MIN_CONNS", "8")

	cfg, err := Load()
	require.NoError(t, err)
	assert.Equal(t, 40, cfg.DBPoolMaxConns)
	assert.Equal(t, 8, cfg.DBPoolMinConns)
}

func TestLoad_DBPoolValidation_MinExceedsMax(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_DB_POOL_MAX_CONNS", "5")
	setEnv(t, "JM_API_DB_POOL_MIN_CONNS", "10")

	_, err := Load()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "cannot exceed max")
}

func TestLoad_InvalidDBRetryMaxAttempts(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_DB_CONNECT_RETRY_MAX_ATTEMPTS", "0")

	_, err := Load()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "JM_API_DB_CONNECT_RETRY_MAX_ATTEMPTS")
}

func TestLoad_InvalidDBRetryDelayOrder(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_DB_CONNECT_RETRY_INITIAL_DELAY_SECONDS", "10")
	setEnv(t, "JM_API_DB_CONNECT_RETRY_MAX_DELAY_SECONDS", "2")

	_, err := Load()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "JM_API_DB_CONNECT_RETRY_MAX_DELAY_SECONDS")
}

func TestLoad_CustomDBRetryValues(t *testing.T) {
	setEnv(t, "JM_API_DATABASE_URL", "postgres://localhost/test")
	setEnv(t, "JM_API_DB_CONNECT_RETRY_ENABLED", "false")
	setEnv(t, "JM_API_DB_CONNECT_RETRY_MAX_ATTEMPTS", "8")
	setEnv(t, "JM_API_DB_CONNECT_RETRY_INITIAL_DELAY_SECONDS", "2")
	setEnv(t, "JM_API_DB_CONNECT_RETRY_MAX_DELAY_SECONDS", "12")

	cfg, err := Load()
	require.NoError(t, err)
	assert.False(t, cfg.DBConnectRetryEnabled)
	assert.Equal(t, 8, cfg.DBConnectRetryMaxAttempts)
	assert.Equal(t, 2*time.Second, cfg.DBConnectRetryInitialDelay)
	assert.Equal(t, 12*time.Second, cfg.DBConnectRetryMaxDelay)
}

func TestIsProd(t *testing.T) {
	c := &Config{Environment: "production"}
	assert.True(t, c.IsProd())

	c.Environment = "staging"
	assert.True(t, c.IsProd())

	c.Environment = "development"
	assert.False(t, c.IsProd())
}
