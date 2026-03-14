package service

import (
	"net"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestValidateWebhookURL_InvalidScheme(t *testing.T) {
	err := ValidateWebhookURL("ftp://example.com/webhook")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "scheme must be http or https")
}

func TestValidateWebhookURL_Localhost(t *testing.T) {
	err := ValidateWebhookURL("http://localhost/webhook")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "localhost")
}

func TestValidateWebhookURL_LocalDomain(t *testing.T) {
	err := ValidateWebhookURL("http://myhost.local/webhook")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), ".local")
}

func TestValidateWebhookURL_EmptyHost(t *testing.T) {
	err := ValidateWebhookURL("http:///webhook")
	assert.Error(t, err)
}

func TestValidateWebhookURL_NotAURL(t *testing.T) {
	err := ValidateWebhookURL("not-a-url")
	assert.Error(t, err)
}

func TestIsPrivateIP(t *testing.T) {
	tests := []struct {
		ip      string
		private bool
	}{
		{"10.0.0.1", true},
		{"172.16.0.1", true},
		{"192.168.1.1", true},
		{"127.0.0.1", true},
		{"8.8.8.8", false},
		{"1.1.1.1", false},
	}

	for _, tt := range tests {
		t.Run(tt.ip, func(t *testing.T) {
			ip := net.ParseIP(tt.ip)
			assert.Equal(t, tt.private, isPrivateIP(ip))
		})
	}
}

func TestSignPayload(t *testing.T) {
	sig1 := signPayload("secret", []byte(`{"test": true}`))
	sig2 := signPayload("secret", []byte(`{"test": true}`))
	sig3 := signPayload("other-secret", []byte(`{"test": true}`))

	assert.Equal(t, sig1, sig2)
	assert.NotEqual(t, sig1, sig3)
	assert.Contains(t, sig1, "sha256=")
}
