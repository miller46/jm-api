package middleware

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

type UserContextKey struct{}

type AuthUser struct {
	ID       string
	Email    string
	IsAdmin  bool
	IsActive bool
}

func Auth(signingKeys []string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			authHeader := r.Header.Get("Authorization")
			if authHeader == "" {
				writeAuthError(w, http.StatusUnauthorized, "missing authorization header")
				return
			}

			parts := strings.SplitN(authHeader, " ", 2)
			if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") {
				writeAuthError(w, http.StatusUnauthorized, "invalid authorization header format")
				return
			}
			tokenStr := parts[1]

			claims, err := validateAccessToken(tokenStr, signingKeys)
			if err != nil {
				writeAuthError(w, http.StatusUnauthorized, "invalid or expired token")
				return
			}

			tokenType, _ := claims["type"].(string)
			if tokenType != "access" {
				writeAuthError(w, http.StatusUnauthorized, "invalid token type")
				return
			}

			sub, _ := claims["sub"].(string)
			if sub == "" {
				writeAuthError(w, http.StatusUnauthorized, "invalid token claims")
				return
			}

			email, _ := claims["email"].(string)
			isAdmin, _ := claims["is_admin"].(bool)

			user := &AuthUser{
				ID:      sub,
				Email:   email,
				IsAdmin: isAdmin,
			}
			ctx := context.WithValue(r.Context(), UserContextKey{}, user)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func RequireAdmin(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		user := GetUser(r.Context())
		if user == nil || !user.IsAdmin {
			writeAuthError(w, http.StatusForbidden, "admin access required")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func GetUser(ctx context.Context) *AuthUser {
	user, _ := ctx.Value(UserContextKey{}).(*AuthUser)
	return user
}

func validateAccessToken(tokenStr string, signingKeys []string) (jwt.MapClaims, error) {
	var lastErr error
	for _, key := range signingKeys {
		token, err := jwt.Parse(tokenStr, func(token *jwt.Token) (interface{}, error) {
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, jwt.ErrSignatureInvalid
			}
			return []byte(key), nil
		})
		if err != nil {
			lastErr = err
			continue
		}
		if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
			return claims, nil
		}
	}
	return nil, lastErr
}

func writeAuthError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(map[string]string{"error": msg})
}
