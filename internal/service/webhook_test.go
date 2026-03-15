package service

import (
	"context"
	"encoding/json"
	"net"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
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

func TestVerifyWebhookSignature(t *testing.T) {
	payload := []byte(`{"id":"evt_1","type":"bot.created"}`)
	secret := "supersecret"
	signature := SignWebhookPayload(secret, payload)

	assert.True(t, VerifyWebhookSignature(secret, payload, signature))
	assert.False(t, VerifyWebhookSignature("wrong-secret", payload, signature))
	assert.False(t, VerifyWebhookSignature(secret, []byte(`{"id":"evt_2"}`), signature))
	assert.False(t, VerifyWebhookSignature(secret, payload, "sha256=bad"))
}

func TestMarshalWebhookDeliveryTaskPayload(t *testing.T) {
	payload, err := marshalWebhookDeliveryTaskPayload("wh_123", "bot.created", map[string]interface{}{"id": "bot_1"})
	require.NoError(t, err)

	var decoded WebhookDeliveryTaskPayload
	require.NoError(t, json.Unmarshal(payload, &decoded))
	assert.Equal(t, "wh_123", decoded.WebhookID)
	assert.Equal(t, "bot.created", decoded.EventType)

	var data map[string]interface{}
	require.NoError(t, json.Unmarshal(decoded.Data, &data))
	assert.Equal(t, "bot_1", data["id"])
}

func TestHandleWebhookDeliveryTask_InvalidPayload(t *testing.T) {
	ws := NewWebhookService(nil, nil)

	_, err := ws.HandleWebhookDeliveryTask(context.Background(), json.RawMessage(`{"event_type":"bot.created"}`))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "webhook_id is required")

	_, err = ws.HandleWebhookDeliveryTask(context.Background(), json.RawMessage(`{"webhook_id":"wh_123"}`))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "event_type is required")
}
