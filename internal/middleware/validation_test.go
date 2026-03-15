package middleware

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/go-playground/validator/v10"
	"github.com/stretchr/testify/assert"
)

type validationTestRequest struct {
	Email string `json:"email" validate:"required,email"`
	Role  string `json:"role" validate:"oneof=admin user"`
}

func TestValidateBody_Success(t *testing.T) {
	v := NewRequestValidator()

	h := ValidateBody[validationTestRequest](v)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		req, ok := GetValidatedBody[validationTestRequest](r.Context())
		assert.True(t, ok)
		assert.Equal(t, "user@example.com", req.Email)
		assert.Equal(t, "admin", req.Role)
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodPost, "/", strings.NewReader(`{"email":"user@example.com","role":"admin"}`))
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
}

func TestValidateBody_InvalidJSON(t *testing.T) {
	v := NewRequestValidator()
	h := ValidateBody[validationTestRequest](v)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodPost, "/", strings.NewReader(`{"email":`))
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusBadRequest, rr.Code)

	var resp map[string]any
	assert.NoError(t, json.Unmarshal(rr.Body.Bytes(), &resp))
	assert.Equal(t, "validation_failed", resp["error"])
}

func TestValidateBody_ValidationFailure(t *testing.T) {
	v := NewRequestValidator()
	h := ValidateBody[validationTestRequest](v)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodPost, "/", strings.NewReader(`{"email":"not-an-email","role":"owner"}`))
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusBadRequest, rr.Code)

	var resp struct {
		Error   string `json:"error"`
		Message string `json:"message"`
		Details []struct {
			Field string `json:"field"`
			Rule  string `json:"rule"`
		} `json:"details"`
	}
	assert.NoError(t, json.Unmarshal(rr.Body.Bytes(), &resp))
	assert.Equal(t, "validation_failed", resp.Error)
	assert.Equal(t, "Request validation failed", resp.Message)
	assert.Len(t, resp.Details, 2)
	assert.Equal(t, "email", resp.Details[0].Field)
	assert.Equal(t, "email", resp.Details[0].Rule)
}

func TestRequestValidator_CustomValidationRule(t *testing.T) {
	type customRequest struct {
		Code string `json:"code" validate:"required,alpha2"`
	}

	v := NewRequestValidator()
	err := v.RegisterValidation("alpha2", func(fl validator.FieldLevel) bool {
		value := fl.Field().String()
		if len(value) != 2 {
			return false
		}
		for _, c := range value {
			if c < 'A' || c > 'Z' {
				return false
			}
		}
		return true
	})
	assert.NoError(t, err)

	h := ValidateBody[customRequest](v)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodPost, "/", strings.NewReader(`{"code":"abc"}`))
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusBadRequest, rr.Code)
}
