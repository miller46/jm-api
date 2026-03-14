package observability

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestSetupLogging_DoesNotPanic(t *testing.T) {
	assert.NotPanics(t, func() {
		SetupLogging("INFO", true, 1.0)
	})
	assert.NotPanics(t, func() {
		SetupLogging("DEBUG", false, 0.5)
	})
	assert.NotPanics(t, func() {
		SetupLogging("ERROR", true, 1.0)
	})
	assert.NotPanics(t, func() {
		SetupLogging("WARN", true, 1.0)
	})
}
