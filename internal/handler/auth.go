package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jack/jm-api-go/internal/middleware"
	"github.com/jack/jm-api-go/internal/model"
	"github.com/jack/jm-api-go/internal/service"
)

type AuthHandler struct {
	authService *service.AuthService
}

func NewAuthHandler(authService *service.AuthService) *AuthHandler {
	return &AuthHandler{authService: authService}
}

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type signupRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	var req loginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
		return
	}

	req.Email = strings.TrimSpace(strings.ToLower(req.Email))
	if req.Email == "" || req.Password == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "email and password are required"})
		return
	}

	user, err := h.authService.Login(r.Context(), req.Email, req.Password)
	if err != nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid credentials"})
		return
	}

	accessToken, expiresIn, err := h.authService.CreateAccessToken(user.ID, service.WithUserClaims(user.Email, user.IsAdmin))
	if err != nil {
		writeInternalError(w, r, "create access token", err)
		return
	}

	refreshToken, jti, expiresAt, err := h.authService.CreateRefreshToken(user.ID)
	if err != nil {
		writeInternalError(w, r, "create refresh token", err)
		return
	}

	if err := h.authService.PersistRefreshToken(r.Context(), jti, user.ID, expiresAt, r.UserAgent(), r.RemoteAddr); err != nil {
		writeInternalError(w, r, "persist refresh token", err)
		return
	}

	csrfToken := service.GenerateCSRFToken()

	http.SetCookie(w, &http.Cookie{
		Name:     "refresh_token",
		Value:    refreshToken,
		Path:     "/",
		Expires:  expiresAt,
		HttpOnly: true,
		Secure:   true,
		SameSite: http.SameSiteStrictMode,
	})

	http.SetCookie(w, &http.Cookie{
		Name:     "csrf_token",
		Value:    csrfToken,
		Path:     "/",
		Expires:  expiresAt,
		HttpOnly: false,
		Secure:   true,
		SameSite: http.SameSiteStrictMode,
	})

	writeJSON(w, http.StatusOK, model.TokenResponse{
		AccessToken: accessToken,
		TokenType:   "bearer",
		ExpiresIn:   expiresIn,
	})
}

func (h *AuthHandler) Signup(w http.ResponseWriter, r *http.Request) {
	var req signupRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
		return
	}

	req.Email = strings.TrimSpace(strings.ToLower(req.Email))
	if req.Email == "" || req.Password == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "email and password are required"})
		return
	}

	if len(req.Password) < 8 || len(req.Password) > 128 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "password must be between 8 and 128 characters"})
		return
	}

	if !strings.Contains(req.Email, "@") {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid email format"})
		return
	}

	user, err := h.authService.Signup(r.Context(), req.Email, req.Password)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			writeJSON(w, http.StatusConflict, map[string]string{"error": "email already registered"})
			return
		}
		writeInternalError(w, r, "signup user", err)
		return
	}

	writeJSON(w, http.StatusCreated, model.UserResponse{
		ID:       user.ID,
		Email:    user.Email,
		IsActive: user.IsActive,
		IsAdmin:  user.IsAdmin,
	})
}

func (h *AuthHandler) Refresh(w http.ResponseWriter, r *http.Request) {
	// Get refresh token from cookie
	cookie, err := r.Cookie("refresh_token")
	if err != nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "no refresh token"})
		return
	}

	// Validate CSRF
	csrfCookie, err := r.Cookie("csrf_token")
	if err != nil {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "missing CSRF cookie"})
		return
	}
	csrfHeader := r.Header.Get("X-CSRF-Token")
	if !service.ValidateCSRF(csrfCookie.Value, csrfHeader) {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "CSRF validation failed"})
		return
	}

	claims, err := h.authService.ValidateRefreshToken(cookie.Value)
	if err != nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid refresh token"})
		return
	}

	jti, _ := claims["jti"].(string)
	userID, _ := claims["sub"].(string)

	// Check for replay
	replayed, err := h.authService.DetectReplay(r.Context(), jti, userID)
	if err != nil {
		writeInternalError(w, r, "detect refresh token replay", err)
		return
	}
	if replayed {
		clearAuthCookies(w)
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "token reuse detected, all sessions revoked"})
		return
	}

	// Check token state
	state, _ := h.authService.GetRefreshTokenState(r.Context(), jti)
	if state != "active" {
		clearAuthCookies(w)
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "refresh token is " + state})
		return
	}

	// Rotate
	newRefreshToken, _, refreshExpiry, err := h.authService.RotateRefreshToken(r.Context(), jti, userID, r.UserAgent(), r.RemoteAddr)
	if err != nil {
		writeInternalError(w, r, "rotate refresh token", err)
		return
	}

	// Load user to embed claims in access token
	user, err := h.authService.GetUserByID(r.Context(), userID)
	if err != nil {
		writeInternalError(w, r, "load user during refresh", err)
		return
	}

	accessToken, expiresIn, err := h.authService.CreateAccessToken(userID, service.WithUserClaims(user.Email, user.IsAdmin))
	if err != nil {
		writeInternalError(w, r, "create access token", err)
		return
	}

	csrfToken := service.GenerateCSRFToken()

	http.SetCookie(w, &http.Cookie{
		Name:     "refresh_token",
		Value:    newRefreshToken,
		Path:     "/",
		Expires:  refreshExpiry,
		HttpOnly: true,
		Secure:   true,
		SameSite: http.SameSiteStrictMode,
	})

	http.SetCookie(w, &http.Cookie{
		Name:     "csrf_token",
		Value:    csrfToken,
		Path:     "/",
		Expires:  refreshExpiry,
		HttpOnly: false,
		Secure:   true,
		SameSite: http.SameSiteStrictMode,
	})

	writeJSON(w, http.StatusOK, model.TokenResponse{
		AccessToken: accessToken,
		TokenType:   "bearer",
		ExpiresIn:   expiresIn,
	})
}

func (h *AuthHandler) Logout(w http.ResponseWriter, r *http.Request) {
	cookie, err := r.Cookie("refresh_token")
	if err == nil {
		claims, err := h.authService.ValidateRefreshToken(cookie.Value)
		if err == nil {
			if jti, ok := claims["jti"].(string); ok {
				h.authService.RevokeSession(r.Context(), jti)
			}
		}
	}

	clearAuthCookies(w)
	w.WriteHeader(http.StatusNoContent)
}

func (h *AuthHandler) Me(w http.ResponseWriter, r *http.Request) {
	authUser := middleware.GetUser(r.Context())
	if authUser == nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "not authenticated"})
		return
	}

	user, err := h.authService.GetUserByID(r.Context(), authUser.ID)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "user not found"})
		return
	}

	writeJSON(w, http.StatusOK, model.UserResponse{
		ID:       user.ID,
		Email:    user.Email,
		IsActive: user.IsActive,
		IsAdmin:  user.IsAdmin,
	})
}

func (h *AuthHandler) Sessions(w http.ResponseWriter, r *http.Request) {
	authUser := middleware.GetUser(r.Context())
	if authUser == nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "not authenticated"})
		return
	}

	sessions, err := h.authService.ListUserSessions(r.Context(), authUser.ID)
	if err != nil {
		writeInternalError(w, r, "list user sessions", err)
		return
	}

	// Get current JTI from refresh cookie
	currentJTI := ""
	if cookie, err := r.Cookie("refresh_token"); err == nil {
		if claims, err := h.authService.ValidateRefreshToken(cookie.Value); err == nil {
			currentJTI, _ = claims["jti"].(string)
		}
	}

	infos := make([]model.SessionInfo, 0, len(sessions))
	for _, s := range sessions {
		infos = append(infos, model.SessionInfo{
			TokenJTI:  s.TokenJti,
			IssuedAt:  s.IssuedAt,
			ExpiresAt: s.ExpiresAt,
			RevokedAt: s.RevokedAt,
			Current:   s.TokenJti == currentJTI,
		})
	}

	writeJSON(w, http.StatusOK, model.SessionListResponse{Sessions: infos})
}

func (h *AuthHandler) RevokeSession(w http.ResponseWriter, r *http.Request) {
	authUser := middleware.GetUser(r.Context())
	if authUser == nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "not authenticated"})
		return
	}

	jti := chi.URLParam(r, "jti")
	if jti == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "session jti required"})
		return
	}

	// Verify session ownership
	session, err := h.authService.GetSession(r.Context(), jti)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "session not found"})
		return
	}
	if session.UserID != authUser.ID {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "session not found"})
		return
	}

	if err := h.authService.RevokeSession(r.Context(), jti); err != nil {
		writeInternalError(w, r, "revoke session", err)
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func (h *AuthHandler) RevokeOtherSessions(w http.ResponseWriter, r *http.Request) {
	authUser := middleware.GetUser(r.Context())
	if authUser == nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "not authenticated"})
		return
	}

	// Get current JTI
	currentJTI := ""
	if cookie, err := r.Cookie("refresh_token"); err == nil {
		if claims, err := h.authService.ValidateRefreshToken(cookie.Value); err == nil {
			currentJTI, _ = claims["jti"].(string)
		}
	}

	revoked, err := h.authService.RevokeOtherSessions(r.Context(), authUser.ID, currentJTI)
	if err != nil {
		writeInternalError(w, r, "revoke other sessions", err)
		return
	}

	writeJSON(w, http.StatusOK, map[string]int64{"revoked": revoked})
}

func clearAuthCookies(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     "refresh_token",
		Value:    "",
		Path:     "/",
		MaxAge:   -1,
		HttpOnly: true,
		Secure:   true,
		SameSite: http.SameSiteStrictMode,
	})
	http.SetCookie(w, &http.Cookie{
		Name:     "csrf_token",
		Value:    "",
		Path:     "/",
		MaxAge:   -1,
		HttpOnly: false,
		Secure:   true,
		SameSite: http.SameSiteStrictMode,
	})
}
