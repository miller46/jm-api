package service

import (
	"context"
	"encoding/json"
	"math"
	"net"
	"testing"
	"time"

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
	payload := []byte(`{"test": true}`)
	sig1 := signPayload("secret", payload, 1700000000)
	sig2 := signPayload("secret", payload, 1700000000)
	sig3 := signPayload("other-secret", payload, 1700000000)
	sig4 := signPayload("secret", payload, 1700000001)

	assert.Equal(t, sig1, sig2)
	assert.NotEqual(t, sig1, sig3)
	assert.NotEqual(t, sig1, sig4)
	assert.Contains(t, sig1, "t=1700000000,v1=")
}

func TestVerifyWebhookSignature(t *testing.T) {
	payload := []byte(`{"id":"evt_1","type":"bot.created"}`)
	secret := "supersecret"
	now := time.Unix(1700000100, 0).UTC()
	signature := SignWebhookPayloadAt(secret, payload, 1700000000)

	valid, _ := VerifyWebhookSignatureDetailed(secret, payload, signature, now, 5*time.Minute)
	assert.True(t, valid)

	valid, errMsg := VerifyWebhookSignatureDetailed("wrong-secret", payload, signature, now, 5*time.Minute)
	assert.False(t, valid)
	assert.Equal(t, "signature mismatch", errMsg)

	valid, errMsg = VerifyWebhookSignatureDetailed(secret, []byte(`{"id":"evt_2"}`), signature, now, 5*time.Minute)
	assert.False(t, valid)
	assert.Equal(t, "signature mismatch", errMsg)

	valid, errMsg = VerifyWebhookSignatureDetailed(secret, payload, "sha256=bad", now, 5*time.Minute)
	assert.False(t, valid)
	assert.Contains(t, errMsg, "format")
}

func TestVerifyWebhookSignatureDetailed_ExpiredTimestamp(t *testing.T) {
	payload := []byte(`{"id":"evt_1"}`)
	secret := "supersecret"
	signature := SignWebhookPayloadAt(secret, payload, 1700000000)

	valid, errMsg := VerifyWebhookSignatureDetailed(secret, payload, signature, time.Unix(1700000400, 0).UTC(), 5*time.Minute)
	assert.False(t, valid)
	assert.Equal(t, "signature timestamp outside allowed tolerance", errMsg)
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

func TestRetryBackoffWithJitter_Bounds(t *testing.T) {
	testCases := []struct {
		name    string
		attempt int
		base    time.Duration
	}{
		{name: "attempt-1", attempt: 1, base: 1 * time.Second},
		{name: "attempt-2", attempt: 2, base: 2 * time.Second},
		{name: "attempt-3", attempt: 3, base: 4 * time.Second},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			minExpected := time.Duration(float64(tc.base) * 0.8)
			maxExpected := time.Duration(float64(tc.base) * 1.2)

			gotMin := retryBackoffWithJitter(tc.attempt, 0.0)
			gotMax := retryBackoffWithJitter(tc.attempt, 1.0)

			assert.Equal(t, minExpected, gotMin)
			assert.Equal(t, maxExpected, gotMax)
		})
	}
}

func TestRetryBackoffWithJitter_Distribution(t *testing.T) {
	const samples = 1000
	const attempt = 4 // base = 8s

	base := time.Duration(math.Pow(2, float64(attempt-1))) * time.Second
	minExpected := time.Duration(float64(base) * 0.8)
	maxExpected := time.Duration(float64(base) * 1.2)

	var sum time.Duration
	seen := make(map[time.Duration]struct{})

	for i := 0; i < samples; i++ {
		random := float64(i) / float64(samples-1)
		d := retryBackoffWithJitter(attempt, random)

		assert.GreaterOrEqual(t, d, minExpected)
		assert.LessOrEqual(t, d, maxExpected)

		sum += d
		seen[d] = struct{}{}
	}

	average := time.Duration(int64(sum) / samples)
	delta := time.Duration(float64(base) * 0.01) // 1%
	assert.InDelta(t, float64(base), float64(average), float64(delta))
	assert.Greater(t, len(seen), 100, "jitter should produce a broad range of delay values")
}
