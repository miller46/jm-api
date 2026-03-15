package middleware

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"reflect"
	"strings"

	"github.com/go-playground/validator/v10"
)

const validatedBodyKey contextKey = "validated_body"

type ValidationErrorDetail struct {
	Field   string `json:"field"`
	Rule    string `json:"rule"`
	Message string `json:"message"`
}

type validationErrorResponse struct {
	Error   string                  `json:"error"`
	Message string                  `json:"message"`
	Details []ValidationErrorDetail `json:"details"`
}

type RequestValidator struct {
	validator *validator.Validate
}

func NewRequestValidator() *RequestValidator {
	v := validator.New()
	v.RegisterTagNameFunc(func(field reflect.StructField) string {
		jsonTag := strings.Split(field.Tag.Get("json"), ",")[0]
		if jsonTag == "" || jsonTag == "-" {
			return field.Name
		}
		return jsonTag
	})

	return &RequestValidator{validator: v}
}

func (v *RequestValidator) RegisterValidation(tag string, fn validator.Func) error {
	return v.validator.RegisterValidation(tag, fn)
}

func ValidateBody[T any](reqValidator *RequestValidator) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var req T
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				writeValidationError(w, []ValidationErrorDetail{{
					Field:   "body",
					Rule:    "json",
					Message: "Request body must be valid JSON",
				}})
				return
			}

			if err := reqValidator.validator.Struct(req); err != nil {
				var validationErrors validator.ValidationErrors
				if !errors.As(err, &validationErrors) {
					writeValidationError(w, []ValidationErrorDetail{{
						Field:   "body",
						Rule:    "validation",
						Message: "Request validation failed",
					}})
					return
				}

				details := make([]ValidationErrorDetail, 0, len(validationErrors))
				for _, fieldErr := range validationErrors {
					details = append(details, ValidationErrorDetail{
						Field:   fieldErr.Field(),
						Rule:    fieldErr.Tag(),
						Message: validationMessage(fieldErr),
					})
				}
				writeValidationError(w, details)
				return
			}

			ctx := context.WithValue(r.Context(), validatedBodyKey, &req)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func GetValidatedBody[T any](ctx context.Context) (*T, bool) {
	req, ok := ctx.Value(validatedBodyKey).(*T)
	return req, ok
}

func writeValidationError(w http.ResponseWriter, details []ValidationErrorDetail) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusBadRequest)
	_ = json.NewEncoder(w).Encode(validationErrorResponse{
		Error:   "validation_failed",
		Message: "Request validation failed",
		Details: details,
	})
}

func validationMessage(err validator.FieldError) string {
	field := strings.Title(err.Field())
	switch err.Tag() {
	case "required":
		return fmt.Sprintf("%s is required", field)
	case "min":
		return fmt.Sprintf("%s must be at least %s characters", field, err.Param())
	case "max":
		return fmt.Sprintf("%s must be at most %s characters", field, err.Param())
	case "email":
		return fmt.Sprintf("%s must be a valid email", field)
	case "url":
		return fmt.Sprintf("%s must be a valid URL", field)
	case "uuid":
		return fmt.Sprintf("%s must be a valid UUID", field)
	case "oneof":
		return fmt.Sprintf("%s must be one of: %s", field, strings.ReplaceAll(err.Param(), " ", ", "))
	default:
		return fmt.Sprintf("%s failed validation rule %s", field, err.Tag())
	}
}
