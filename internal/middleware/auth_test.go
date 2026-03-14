package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
)

func makeTestToken(t *testing.T, key string, claims jwt.MapClaims) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenStr, err := token.SignedString([]byte(key))
	if err != nil {
		t.Fatal(err)
	}
	return tokenStr
}

func TestAuth_ValidToken(t *testing.T) {
	key := "test-secret-key"
	tokenStr := makeTestToken(t, key, jwt.MapClaims{
		"sub":      "user123",
		"type":     "access",
		"email":    "test@example.com",
		"is_admin": true,
		"exp":      time.Now().Add(time.Hour).Unix(),
	})

	handler := Auth([]string{key})(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		user := GetUser(r.Context())
		assert.NotNil(t, user)
		assert.Equal(t, "user123", user.ID)
		assert.Equal(t, "test@example.com", user.Email)
		assert.True(t, user.IsAdmin)
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer "+tokenStr)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
}

func TestAuth_MissingHeader(t *testing.T) {
	handler := Auth([]string{"key"})(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("should not reach handler")
	}))

	req := httptest.NewRequest("GET", "/", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusUnauthorized, rr.Code)
}

func TestAuth_InvalidToken(t *testing.T) {
	handler := Auth([]string{"key"})(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("should not reach handler")
	}))

	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer invalid.token.here")
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusUnauthorized, rr.Code)
}

func TestAuth_RefreshTokenRejected(t *testing.T) {
	key := "test-secret-key"
	tokenStr := makeTestToken(t, key, jwt.MapClaims{
		"sub":  "user123",
		"type": "refresh",
		"exp":  time.Now().Add(time.Hour).Unix(),
	})

	handler := Auth([]string{key})(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("should not reach handler")
	}))

	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer "+tokenStr)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusUnauthorized, rr.Code)
}

func TestAuth_ExpiredToken(t *testing.T) {
	key := "test-secret-key"
	tokenStr := makeTestToken(t, key, jwt.MapClaims{
		"sub":  "user123",
		"type": "access",
		"exp":  time.Now().Add(-time.Hour).Unix(),
	})

	handler := Auth([]string{key})(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("should not reach handler")
	}))

	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer "+tokenStr)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusUnauthorized, rr.Code)
}

func TestAuth_KeyRotation(t *testing.T) {
	oldKey := "old-key"
	newKey := "new-key"
	tokenStr := makeTestToken(t, oldKey, jwt.MapClaims{
		"sub":  "user123",
		"type": "access",
		"exp":  time.Now().Add(time.Hour).Unix(),
	})

	handler := Auth([]string{newKey, oldKey})(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		user := GetUser(r.Context())
		assert.Equal(t, "user123", user.ID)
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer "+tokenStr)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
}

func TestRequireAdmin_Forbidden(t *testing.T) {
	handler := RequireAdmin(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("should not reach handler")
	}))

	req := httptest.NewRequest("GET", "/", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusForbidden, rr.Code)
}
