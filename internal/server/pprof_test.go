package server

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"github.com/jack/jm-api-go/internal/middleware"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const testJWTKey = "test-signing-key"

func TestRegisterPprofRoutes_RequiresAuthentication(t *testing.T) {
	r := chi.NewRouter()
	registerPprofRoutes(r, middleware.Auth([]string{testJWTKey}))

	req := httptest.NewRequest(http.MethodGet, "/debug/pprof/", nil)
	res := httptest.NewRecorder()

	r.ServeHTTP(res, req)

	assert.Equal(t, http.StatusUnauthorized, res.Code)
}

func TestRegisterPprofRoutes_RequiresAdmin(t *testing.T) {
	r := chi.NewRouter()
	registerPprofRoutes(r, middleware.Auth([]string{testJWTKey}))

	req := httptest.NewRequest(http.MethodGet, "/debug/pprof/", nil)
	req.Header.Set("Authorization", "Bearer "+newAccessToken(t, false))
	res := httptest.NewRecorder()

	r.ServeHTTP(res, req)

	assert.Equal(t, http.StatusForbidden, res.Code)
}

func TestRegisterPprofRoutes_ExposesProfilesForAdmin(t *testing.T) {
	r := chi.NewRouter()
	registerPprofRoutes(r, middleware.Auth([]string{testJWTKey}))

	tests := []string{
		"/debug/pprof/",
		"/debug/pprof/heap",
		"/debug/pprof/goroutine",
		"/debug/pprof/mutex",
		"/debug/pprof/profile?seconds=1",
	}

	for _, path := range tests {
		t.Run(path, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, path, nil)
			req.Header.Set("Authorization", "Bearer "+newAccessToken(t, true))
			res := httptest.NewRecorder()

			r.ServeHTTP(res, req)

			assert.Equal(t, http.StatusOK, res.Code)
		})
	}
}

func newAccessToken(t *testing.T, isAdmin bool) string {
	t.Helper()

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":      "user_123",
		"email":    "admin@example.com",
		"is_admin": isAdmin,
		"type":     "access",
	})
	tokenString, err := token.SignedString([]byte(testJWTKey))
	require.NoError(t, err)
	return tokenString
}
