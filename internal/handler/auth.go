package handler

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jack/jm-api-go/internal/httperr"
	"github.com/jack/jm-api-go/internal/middleware"
	"github.com/jack/jm-api-go/internal/model"
	"github.com/jack/jm-api-go/internal/service"
)

type AuthHandler struct {
	authService  *service.AuthService
	errorHandler *httperr.Handler
}

func NewAuthHandler(authService *service.AuthService, errorHandler *httperr.Handler) *AuthHandler {
	return &AuthHandler{
		authService:  authService,
		errorHandler: errorHandler,
	}
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
		h.errorHandler.RespondError(w, r, httperr.ErrInvalidRequestBody.WithInternal(err))
		return
	}

	req.Email = strings.TrimSpace(strings.ToLower(req.Email))
	if req.Email == "" || req.Password == "" {
		h.errorHandler.RespondError(w, r, httperr.ErrMissingField("email and password"))
		return
	}

	user, err := h.authService.Login(r.Context(), req.Email, req.Password)
	if err != nil {
		// Don't leak whether email exists or password is wrong
		h.errorHandler.RespondError(w, r, httperr.ErrInvalidCredentials.WithInternal(err))
		return
	}

	accessToken, expiresIn, err := h.authService.CreateAccessToken(user.ID, service.WithUserClaims(user.Email, user.IsAdmin))
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrInternalServer.WithInternal(err).WithLogAttrs(
			SlogString("operation", "create_access_token"),
		))
		return
	}

	refreshToken, jti, expiresAt, err := h.authService.CreateRefreshToken(user.ID)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrInternalServer.WithInternal(err).WithLogAttrs(
			SlogString("operation", "create_refresh_token"),
		))
		return
	}

	if err := h.authService.PersistRefreshToken(r.Context(), jti, user.ID, expiresAt, r.UserAgent(), r.RemoteAddr); err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrInternalServer.WithInternal(err).WithLogAttrs(
			SlogString("operation", "persist_refresh_token"),
		))
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
		h.errorHandler.RespondError(w, r, httperr.ErrInvalidRequestBody.WithInternal(err))
		return
	}

	req.Email = strings.TrimSpace(strings.ToLower(req.Email))
	if req.Email == "" || req.Password == "" {
		h.errorHandler.RespondError(w, r, httperr.ErrMissingField("email and password"))
		return
	}

	if len(req.Password) < 8 || len(req.Password) > 128 {
		h.errorHandler.RespondError(w, r, httperr.ErrValidationFailed("password must be between 8 and 128 characters"))
		return
	}

	if !strings.Contains(req.Email, "@") {
		h.errorHandler.RespondError(w, r, httperr.ErrInvalidField("email"))
		return
	}

	user, err := h.authService.Signup(r.Context(), req.Email, req.Password)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			h.errorHandler.RespondError(w, r, httperr.ErrDuplicate("email"))
			return
		}
		h.errorHandler.RespondError(w, r, httperr.ErrInternalServer.WithInternal(err).WithLogAttrs(
			SlogString("operation", "create_user"),
		))
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
		h.errorHandler.RespondError(w, r, httperr.ErrInvalidToken)
		return
	}

	// Validate CSRF
	csrfCookie, err := r.Cookie("csrf_token")
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrCSRFInvalid.WithInternal(errors.New("missing CSRF cookie")))
		return
	}
	csrfHeader := r.Header.Get("X-CSRF-Token")
	if !service.ValidateCSRF(csrfCookie.Value, csrfHeader) {
		h.errorHandler.RespondError(w, r, httperr.ErrCSRFInvalid)
		return
	}

	claims, err := h.authService.ValidateRefreshToken(cookie.Value)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrInvalidToken.WithInternal(err))
		return
	}

	jti, _ := claims["jti"].(string)
	userID, _ := claims["sub"].(string)

	// Check for replay
	replayed, err := h.authService.DetectReplay(r.Context(), jti, userID)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrInternalServer.WithInternal(err).WithLogAttrs(
			SlogString("operation", "detect_replay"),
		))
		return
	}
	if replayed {
		clearAuthCookies(w)
		h.errorHandler.RespondError(w, r, httperr.ErrInvalidToken.WithInternal(errors.New("token reuse detected")))
		return
	}

	// Check token state
	state, _ := h.authService.GetRefreshTokenState(r.Context(), jti)
	if state != "active" {
		clearAuthCookies(w)
		h.errorHandler.RespondError(w, r, httperr.ErrInvalidToken.WithInternal(errors.New("refresh token state: "+state)))
		return
	}

	// Rotate
	newRefreshToken, _, refreshExpiry, err := h.authService.RotateRefreshToken(r.Context(), jti, userID, r.UserAgent(), r.RemoteAddr)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrInternalServer.WithInternal(err).WithLogAttrs(
			SlogString("operation", "rotate_refresh_token"),
		))
		return
	}

	// Load user to embed claims in access token
	user, err := h.authService.GetUserByID(r.Context(), userID)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrNotFound("user").WithInternal(err))
		return
	}

	accessToken, expiresIn, err := h.authService.CreateAccessToken(userID, service.WithUserClaims(user.Email, user.IsAdmin))
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrInternalServer.WithInternal(err).WithLogAttrs(
			SlogString("operation", "create_access_token"),
		))
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
		h.errorHandler.RespondError(w, r, httperr.ErrUnauthorized)
		return
	}

	user, err := h.authService.GetUserByID(r.Context(), authUser.ID)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrNotFound("user").WithInternal(err))
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
		h.errorHandler.RespondError(w, r, httperr.ErrUnauthorized)
		return
	}

	sessions, err := h.authService.ListUserSessions(r.Context(), authUser.ID)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrInternalServer.WithInternal(err).WithLogAttrs(
			SlogString("operation", "list_sessions"),
		))
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
		h.errorHandler.RespondError(w, r, httperr.ErrUnauthorized)
		return
	}

	jti := chi.URLParam(r, "jti")
	if jti == "" {
		h.errorHandler.RespondError(w, r, httperr.ErrMissingField("session jti"))
		return
	}

	// Verify session ownership
	session, err := h.authService.GetSession(r.Context(), jti)
	if err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrNotFound("session").WithInternal(err))
		return
	}
	if session.UserID != authUser.ID {
		// Return not found to avoid leaking existence of other users' sessions
		h.errorHandler.RespondError(w, r, httperr.ErrNotFound("session"))
		return
	}

	if err := h.authService.RevokeSession(r.Context(), jti); err != nil {
		h.errorHandler.RespondError(w, r, httperr.ErrInternalServer.WithInternal(err).WithLogAttrs(
			SlogString("operation", "revoke_session"),
		))
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func (h *AuthHandler) RevokeOtherSessions(w http.ResponseWriter, r *http.Request) {
	authUser := middleware.GetUser(r.Context())
	if authUser == nil {
		h.errorHandler.RespondError(w, r, httperr.ErrUnauthorized)
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
		h.errorHandler.RespondError(w, r, httperr.ErrInternalServer.WithInternal(err).WithLogAttrs(
			SlogString("operation", "revoke_other_sessions"),
		))
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

// SlogString is a helper for creating slog.Attr from string values
func SlogString(key, value string) slog.Attr {
	return slog.String(key, value)
}
