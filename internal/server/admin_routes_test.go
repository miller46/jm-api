package server

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/jack/jm-api-go/internal/middleware"
	"github.com/stretchr/testify/assert"
)

func TestAdminScheduledJobsRoutes_NonAdminCanReadButCannotMutate(t *testing.T) {
	r := chi.NewRouter()
	authMW := middleware.Auth([]string{testJWTKey})
	csrfMW := middleware.CSRF

	ok := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	r.Route("/api/v1", func(r chi.Router) {
		r.Route("/admin", func(r chi.Router) {
			r.Use(authMW)
			r.Use(csrfMW)

			r.With(middleware.RequireAdmin).Get("/break/status", ok)

			r.Route("/scheduled-jobs", func(r chi.Router) {
				r.Get("/", ok)
				r.With(middleware.RequireAdmin).Post("/", ok)
			})
		})
	})

	t.Run("list jobs is allowed", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/scheduled-jobs", nil)
		req.Header.Set("Authorization", "Bearer "+newAccessToken(t, false))
		res := httptest.NewRecorder()

		r.ServeHTTP(res, req)
		assert.Equal(t, http.StatusOK, res.Code)
	})

	t.Run("create job is forbidden", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/scheduled-jobs", nil)
		req.Header.Set("Authorization", "Bearer "+newAccessToken(t, false))
		res := httptest.NewRecorder()

		r.ServeHTTP(res, req)
		assert.Equal(t, http.StatusForbidden, res.Code)
	})

	t.Run("break status remains admin-only", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/break/status", nil)
		req.Header.Set("Authorization", "Bearer "+newAccessToken(t, false))
		res := httptest.NewRecorder()

		r.ServeHTTP(res, req)
		assert.Equal(t, http.StatusForbidden, res.Code)
	})
}

func TestScheduledJobsAliasRoutes_NonAdminCanReadButCannotMutate(t *testing.T) {
	r := chi.NewRouter()
	authMW := middleware.Auth([]string{testJWTKey})
	csrfMW := middleware.CSRF

	ok := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	r.Route("/api/v1", func(r chi.Router) {
		r.Route("/scheduled_jobs", func(r chi.Router) {
			r.Use(authMW)
			r.Use(csrfMW)

			r.Get("/", ok)
			r.With(middleware.RequireAdmin).Post("/", ok)
		})
	})

	t.Run("list jobs via alias is allowed", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/scheduled_jobs", nil)
		req.Header.Set("Authorization", "Bearer "+newAccessToken(t, false))
		res := httptest.NewRecorder()

		r.ServeHTTP(res, req)
		assert.Equal(t, http.StatusOK, res.Code)
	})

	t.Run("create job via alias is forbidden", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodPost, "/api/v1/scheduled_jobs", nil)
		req.Header.Set("Authorization", "Bearer "+newAccessToken(t, false))
		res := httptest.NewRecorder()

		r.ServeHTTP(res, req)
		assert.Equal(t, http.StatusForbidden, res.Code)
	})
}
