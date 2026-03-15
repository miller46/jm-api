package service

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"math"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/model"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/sony/gobreaker"
)

const WebhookDeliveryTaskType = "webhook.delivery"

type WebhookDeliveryTaskPayload struct {
	WebhookID string          `json:"webhook_id"`
	EventType string          `json:"event_type"`
	Data      json.RawMessage `json:"data"`
}

type WebhookService struct {
	queries               *sqlc.Queries
	client                *http.Client
	circuitManager        *CircuitBreakerManager
	circuitBreakerEnabled bool
}

func NewWebhookService(q *sqlc.Queries, cbConfig *CircuitBreakerConfig) *WebhookService {
	dialer := &net.Dialer{Timeout: 5 * time.Second}
	transport := &http.Transport{
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			host, port, err := net.SplitHostPort(addr)
			if err != nil {
				return nil, fmt.Errorf("invalid address: %w", err)
			}
			ips, err := net.DefaultResolver.LookupIPAddr(ctx, host)
			if err != nil {
				return nil, fmt.Errorf("DNS lookup failed: %w", err)
			}
			for _, ip := range ips {
				if isPrivateIP(ip.IP) {
					return nil, fmt.Errorf("private IP addresses are not allowed")
				}
			}
			// Connect to the first resolved IP
			return dialer.DialContext(ctx, network, net.JoinHostPort(ips[0].IP.String(), port))
		},
	}

	svc := &WebhookService{
		queries: q,
		client: &http.Client{
			Timeout:   10 * time.Second,
			Transport: transport,
		},
		circuitBreakerEnabled: cbConfig != nil,
	}

	if cbConfig != nil {
		svc.circuitManager = NewCircuitBreakerManager(*cbConfig)
	}

	return svc
}

type WebhookEvent struct {
	ID             string      `json:"id"`
	Type           string      `json:"type"`
	CreatedAt      string      `json:"created_at"`
	IdempotencyKey string      `json:"idempotency_key"`
	Data           interface{} `json:"data"`
}

func ValidateWebhookURL(targetURL string) error {
	u, err := url.Parse(targetURL)
	if err != nil {
		return fmt.Errorf("invalid URL: %w", err)
	}

	if u.Scheme != "http" && u.Scheme != "https" {
		return fmt.Errorf("URL scheme must be http or https")
	}

	host := u.Hostname()
	if host == "" {
		return fmt.Errorf("URL must have a hostname")
	}

	lower := strings.ToLower(host)
	if lower == "localhost" || strings.HasSuffix(lower, ".local") {
		return fmt.Errorf("localhost and .local URLs are not allowed")
	}

	ips, err := net.LookupIP(host)
	if err != nil {
		return fmt.Errorf("cannot resolve hostname: %w", err)
	}

	for _, ip := range ips {
		if isPrivateIP(ip) {
			return fmt.Errorf("private IP addresses are not allowed")
		}
	}

	return nil
}

func isPrivateIP(ip net.IP) bool {
	privateRanges := []string{
		"10.0.0.0/8",
		"172.16.0.0/12",
		"192.168.0.0/16",
		"127.0.0.0/8",
		"169.254.0.0/16",
		"::1/128",
		"fc00::/7",
		"fe80::/10",
	}

	for _, cidr := range privateRanges {
		_, ipNet, _ := net.ParseCIDR(cidr)
		if ipNet.Contains(ip) {
			return true
		}
	}

	return ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() || ip.IsUnspecified()
}

func signPayload(secret string, payload []byte) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	return "sha256=" + hex.EncodeToString(mac.Sum(nil))
}

func (ws *WebhookService) DeliverEvent(ctx context.Context, webhook sqlc.Webhook, eventType string, data interface{}) error {
	event := WebhookEvent{
		ID:             model.GenerateID(),
		Type:           eventType,
		CreatedAt:      time.Now().UTC().Format(time.RFC3339),
		IdempotencyKey: model.GenerateID(),
		Data:           data,
	}

	payload, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("marshaling event: %w", err)
	}

	signature := signPayload(webhook.Secret, payload)

	maxAttempts := 5
	var lastErr error
	var statusCode int
	var responseBody string

	for attempt := 1; attempt <= maxAttempts; attempt++ {
		if attempt > 1 {
			backoff := time.Duration(math.Pow(2, float64(attempt-1))) * time.Second
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(backoff):
			}
		}

		statusCode, responseBody, lastErr = ws.doDelivery(ctx, webhook.ID, webhook.TargetUrl, payload, signature, eventType, event.ID)

		if lastErr == nil && statusCode >= 200 && statusCode < 300 {
			ws.logDelivery(ctx, webhook.ID, event.ID, eventType, true, attempt, &statusCode, responseBody, "")
			return nil
		}

		slog.Warn("webhook delivery attempt failed",
			"webhook_id", webhook.ID,
			"attempt", attempt,
			"status_code", statusCode,
			"error", lastErr,
		)
	}

	errMsg := ""
	if lastErr != nil {
		errMsg = lastErr.Error()
	}
	ws.logDelivery(ctx, webhook.ID, event.ID, eventType, false, maxAttempts, &statusCode, responseBody, errMsg)

	return fmt.Errorf("webhook delivery failed after %d attempts: %v", maxAttempts, lastErr)
}

func (ws *WebhookService) doDelivery(ctx context.Context, webhookID, targetURL string, payload []byte, signature, eventType, eventID string) (int, string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, targetURL, bytes.NewReader(payload))
	if err != nil {
		return 0, "", err
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Webhook-Signature", signature)
	req.Header.Set("X-Webhook-Event", eventType)
	req.Header.Set("X-Webhook-Delivery", eventID)

	var resp *http.Response
	if ws.circuitBreakerEnabled && ws.circuitManager != nil {
		resp, err = ws.circuitManager.DoHTTPRequest(ctx, webhookID, ws.client, req)
	} else {
		resp, err = ws.client.Do(req)
	}

	if err != nil {
		if errors.Is(err, gobreaker.ErrOpenState) {
			return 0, "", fmt.Errorf("circuit breaker open: %w", err)
		}
		return 0, "", err
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1000))

	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		return resp.StatusCode, string(body), nil
	}

	return resp.StatusCode, string(body), fmt.Errorf("non-2xx status: %d", resp.StatusCode)
}

func (ws *WebhookService) logDelivery(ctx context.Context, webhookID, eventID, eventType string, success bool, attempts int, statusCode *int, responseBody, errMessage string) {
	sc := pgtype.Int4{}
	if statusCode != nil {
		sc = pgtype.Int4{Int32: int32(*statusCode), Valid: true}
	}
	rb := pgtype.Text{}
	if responseBody != "" {
		rb = pgtype.Text{String: responseBody, Valid: true}
	}
	em := pgtype.Text{}
	if errMessage != "" {
		em = pgtype.Text{String: errMessage, Valid: true}
	}

	_, err := ws.queries.CreateWebhookDeliveryLog(ctx, sqlc.CreateWebhookDeliveryLogParams{
		ID:           model.GenerateID(),
		WebhookID:    webhookID,
		EventID:      eventID,
		EventType:    eventType,
		Success:      success,
		Attempts:     int32(attempts),
		StatusCode:   sc,
		ResponseBody: rb,
		ErrorMessage: em,
	})
	if err != nil {
		slog.Error("failed to log webhook delivery", "error", err)
	}
}

func (ws *WebhookService) DispatchEvent(ctx context.Context, eventType string, data interface{}) {
	eventTypeJSON, _ := json.Marshal([]string{eventType})

	webhooks, err := ws.queries.ListActiveWebhooksByEventType(ctx, eventTypeJSON)
	if err != nil {
		slog.Error("failed to list webhooks for event", "event_type", eventType, "error", err)
		return
	}

	for _, webhook := range webhooks {
		if err := ws.EnqueueDeliveryTask(ctx, webhook.ID, eventType, data); err != nil {
			slog.Error("failed to enqueue webhook delivery", "webhook_id", webhook.ID, "event_type", eventType, "error", err)
		}
	}
}

func (ws *WebhookService) EnqueueDeliveryTask(ctx context.Context, webhookID, eventType string, data interface{}) error {
	payload, err := marshalWebhookDeliveryTaskPayload(webhookID, eventType, data)
	if err != nil {
		return err
	}

	_, err = ws.queries.CreateTask(ctx, sqlc.CreateTaskParams{
		ID:      model.GenerateID(),
		Type:    WebhookDeliveryTaskType,
		Payload: payload,
	})
	if err != nil {
		return fmt.Errorf("creating webhook task: %w", err)
	}

	return nil
}

func marshalWebhookDeliveryTaskPayload(webhookID, eventType string, data interface{}) (json.RawMessage, error) {
	dataJSON, err := json.Marshal(data)
	if err != nil {
		return nil, fmt.Errorf("marshal webhook task data: %w", err)
	}

	payload, err := json.Marshal(WebhookDeliveryTaskPayload{
		WebhookID: webhookID,
		EventType: eventType,
		Data:      dataJSON,
	})
	if err != nil {
		return nil, fmt.Errorf("marshal webhook task payload: %w", err)
	}

	return payload, nil
}

// GetCircuitBreakerState returns the circuit breaker state for a webhook
func (ws *WebhookService) GetCircuitBreakerState(webhookID string) CircuitState {
	if ws.circuitManager == nil {
		return CircuitClosed
	}
	return ws.circuitManager.GetState(webhookID)
}

// GetAllCircuitBreakerStates returns all circuit breaker states
func (ws *WebhookService) GetAllCircuitBreakerStates() map[string]CircuitState {
	if ws.circuitManager == nil {
		return make(map[string]CircuitState)
	}
	return ws.circuitManager.GetAllStates()
}

// GetCircuitBreakerMetrics returns circuit breaker metrics
func (ws *WebhookService) GetCircuitBreakerMetrics() map[string]interface{} {
	if ws.circuitManager == nil {
		return map[string]interface{}{}
	}
	return ws.circuitManager.GetMetrics()
}

// ResetCircuitBreaker resets a circuit breaker for a specific webhook
func (ws *WebhookService) ResetCircuitBreaker(webhookID string) {
	if ws.circuitManager != nil {
		ws.circuitManager.Reset(webhookID)
	}
}

func (ws *WebhookService) HandleWebhookDeliveryTask(ctx context.Context, payload json.RawMessage) (json.RawMessage, error) {
	var taskPayload WebhookDeliveryTaskPayload
	if err := json.Unmarshal(payload, &taskPayload); err != nil {
		return nil, fmt.Errorf("unmarshal webhook task payload: %w", err)
	}

	if taskPayload.WebhookID == "" {
		return nil, fmt.Errorf("webhook_id is required")
	}
	if taskPayload.EventType == "" {
		return nil, fmt.Errorf("event_type is required")
	}

	webhook, err := ws.queries.GetWebhookByID(ctx, taskPayload.WebhookID)
	if err != nil {
		return nil, fmt.Errorf("get webhook: %w", err)
	}
	if !webhook.IsActive {
		return json.RawMessage(`{"status":"skipped","reason":"webhook_inactive"}`), nil
	}

	var data interface{}
	if len(taskPayload.Data) > 0 {
		if err := json.Unmarshal(taskPayload.Data, &data); err != nil {
			return nil, fmt.Errorf("unmarshal webhook task data: %w", err)
		}
	}

	if err := ws.DeliverEvent(ctx, webhook, taskPayload.EventType, data); err != nil {
		return nil, err
	}

	return json.RawMessage(`{"status":"delivered"}`), nil
}
