package service

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestDefaultCircuitBreakerConfig(t *testing.T) {
	cfg := DefaultCircuitBreakerConfig()

	assert.Equal(t, uint32(100), cfg.MaxRequests)
	assert.Equal(t, 10*time.Second, cfg.Interval)
	assert.Equal(t, 30*time.Second, cfg.Timeout)
	assert.Equal(t, 0.6, cfg.FailureThreshold)
	assert.Equal(t, uint32(3), cfg.MinRequests)
	assert.Equal(t, uint32(5), cfg.ConsecutiveFailure)
	assert.Equal(t, 30*time.Second, cfg.OpenDuration)
}

func TestCircuitState_String(t *testing.T) {
	assert.Equal(t, "closed", CircuitClosed.String())
	assert.Equal(t, "open", CircuitOpen.String())
	assert.Equal(t, "half-open", CircuitHalfOpen.String())
	assert.Equal(t, "unknown", CircuitState(99).String())
}

func TestCircuitBreakerManager_GetCircuitBreaker(t *testing.T) {
	cfg := DefaultCircuitBreakerConfig()
	mgr := NewCircuitBreakerManager(cfg)

	// Get a circuit breaker for subscriber
	cb1 := mgr.GetCircuitBreaker("sub-1")
	require.NotNil(t, cb1)

	// Getting same subscriber returns same circuit breaker
	cb2 := mgr.GetCircuitBreaker("sub-1")
	require.NotNil(t, cb2)
	assert.Equal(t, cb1, cb2)

	// Different subscriber gets different circuit breaker
	cb3 := mgr.GetCircuitBreaker("sub-2")
	require.NotNil(t, cb3)
	assert.NotEqual(t, cb1, cb3)
}

func TestCircuitBreakerManager_Execute(t *testing.T) {
	cfg := DefaultCircuitBreakerConfig()
	cfg.FailureThreshold = 0.5
	cfg.MinRequests = 2
	cfg.ConsecutiveFailure = 3
	mgr := NewCircuitBreakerManager(cfg)

	t.Run("successful execution", func(t *testing.T) {
		err := mgr.Execute(context.Background(), "test-sub-1", func() error {
			return nil
		})
		assert.NoError(t, err)
	})

	t.Run("failed execution", func(t *testing.T) {
		err := mgr.Execute(context.Background(), "test-sub-2", func() error {
			return fmt.Errorf("test error")
		})
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "test error")
	})

	t.Run("circuit opens after failures", func(t *testing.T) {
		subID := "test-sub-3"
		failCount := 0

		// Trigger enough failures to open the circuit
		for i := 0; i < 5; i++ {
			err := mgr.Execute(context.Background(), subID, func() error {
				return fmt.Errorf("intentional failure")
			})
			if err != nil && i >= 3 {
				failCount++
			}
		}

		// Circuit should be open now - subsequent requests should fail fast
		err := mgr.Execute(context.Background(), subID, func() error {
			return nil
		})
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "circuit breaker open")
	})
}

func TestCircuitBreakerManager_DoHTTPRequest(t *testing.T) {
	cfg := DefaultCircuitBreakerConfig()
	cfg.FailureThreshold = 0.5
	cfg.MinRequests = 2
	mgr := NewCircuitBreakerManager(cfg)
	client := &http.Client{Timeout: 5 * time.Second}

	t.Run("successful request", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`{"ok": true}`))
		}))
		defer server.Close()

		req, err := http.NewRequest("GET", server.URL, nil)
		require.NoError(t, err)

		resp, err := mgr.DoHTTPRequest(context.Background(), "http-success", client, req)
		require.NoError(t, err)
		assert.Equal(t, http.StatusOK, resp.StatusCode)
		resp.Body.Close()
	})

	t.Run("server error counts as failure", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		subID := "http-error"

		// Trigger multiple failures to open circuit
		for i := 0; i < 5; i++ {
			req, _ := http.NewRequest("GET", server.URL, nil)
			mgr.DoHTTPRequest(context.Background(), subID, client, req)
		}

		// Circuit should be open
		req, _ := http.NewRequest("GET", server.URL, nil)
		_, err := mgr.DoHTTPRequest(context.Background(), subID, client, req)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "circuit breaker open")
	})

	t.Run("client error does not count as failure", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusBadRequest)
		}))
		defer server.Close()

		subID := "http-client-error"

		// Multiple 400s should not trip circuit
		for i := 0; i < 10; i++ {
			req, _ := http.NewRequest("GET", server.URL, nil)
			resp, err := mgr.DoHTTPRequest(context.Background(), subID, client, req)
			require.NoError(t, err, "client errors should not fail circuit breaker")
			assert.Equal(t, http.StatusBadRequest, resp.StatusCode)
			resp.Body.Close()
		}

		// Circuit should still be closed
		state := mgr.GetState(subID)
		assert.Equal(t, CircuitClosed, state)
	})
}

func TestCircuitBreakerManager_GetState(t *testing.T) {
	cfg := DefaultCircuitBreakerConfig()
	mgr := NewCircuitBreakerManager(cfg)

	// Unknown subscriber returns closed
	state := mgr.GetState("unknown")
	assert.Equal(t, CircuitClosed, state)

	// After creating circuit, still closed
	_ = mgr.GetCircuitBreaker("known")
	state = mgr.GetState("known")
	assert.Equal(t, CircuitClosed, state)
}

func TestCircuitBreakerManager_GetAllStates(t *testing.T) {
	cfg := DefaultCircuitBreakerConfig()
	mgr := NewCircuitBreakerManager(cfg)

	// Create some circuits
	_ = mgr.GetCircuitBreaker("sub-1")
	_ = mgr.GetCircuitBreaker("sub-2")
	_ = mgr.GetCircuitBreaker("sub-3")

	states := mgr.GetAllStates()
	assert.Len(t, states, 3)
	assert.Equal(t, CircuitClosed, states["sub-1"])
	assert.Equal(t, CircuitClosed, states["sub-2"])
	assert.Equal(t, CircuitClosed, states["sub-3"])
}

func TestCircuitBreakerManager_Reset(t *testing.T) {
	cfg := DefaultCircuitBreakerConfig()
	cfg.FailureThreshold = 0.1
	cfg.MinRequests = 1
	mgr := NewCircuitBreakerManager(cfg)

	subID := "reset-test"

	// Trigger failures to open circuit
	for i := 0; i < 5; i++ {
		mgr.Execute(context.Background(), subID, func() error {
			return fmt.Errorf("failure")
		})
	}

	// Verify circuit is open
	state := mgr.GetState(subID)
	assert.Equal(t, CircuitOpen, state)

	// Reset the circuit
	mgr.Reset(subID)

	// Circuit should be gone (returns closed for unknown)
	state = mgr.GetState(subID)
	assert.Equal(t, CircuitClosed, state)
}

func TestCircuitBreakerManager_PerSubscriberIsolation(t *testing.T) {
	cfg := DefaultCircuitBreakerConfig()
	cfg.FailureThreshold = 0.5
	cfg.MinRequests = 2
	mgr := NewCircuitBreakerManager(cfg)

	// Open circuit for subscriber 1
	for i := 0; i < 5; i++ {
		mgr.Execute(context.Background(), "isolated-1", func() error {
			return fmt.Errorf("failure")
		})
	}

	// Subscriber 1 should have open circuit
	assert.Equal(t, CircuitOpen, mgr.GetState("isolated-1"))

	// Subscriber 2 should still have closed circuit
	assert.Equal(t, CircuitClosed, mgr.GetState("isolated-2"))

	// Requests to subscriber 2 should still work
	err := mgr.Execute(context.Background(), "isolated-2", func() error {
		return nil
	})
	assert.NoError(t, err)
}

func TestCircuitBreakerMetrics(t *testing.T) {
	metrics := NewCircuitBreakerMetrics()

	// Record some events
	metrics.RecordStateChange("sub-1", CircuitClosed, CircuitOpen)
	metrics.RecordStateChange("sub-1", CircuitOpen, CircuitHalfOpen)
	metrics.RecordStateChange("sub-2", CircuitClosed, CircuitOpen)

	metrics.RecordAllowed("sub-1")
	metrics.RecordAllowed("sub-1")
	metrics.RecordAllowed("sub-2")

	metrics.RecordBlocked("sub-1")
	metrics.RecordBlocked("sub-1")

	// Get metrics
	m := metrics.GetMetrics()

	stateChanges := m["state_changes"].(map[string]int)
	assert.Equal(t, 2, stateChanges["sub-1"])
	assert.Equal(t, 1, stateChanges["sub-2"])

	allowed := m["allowed_requests"].(map[string]int)
	assert.Equal(t, 2, allowed["sub-1"])
	assert.Equal(t, 1, allowed["sub-2"])

	blocked := m["blocked_requests"].(map[string]int)
	assert.Equal(t, 2, blocked["sub-1"])
	assert.NotContains(t, blocked, "sub-2")
}

func TestCircuitBreakerManager_ConcurrentAccess(t *testing.T) {
	cfg := DefaultCircuitBreakerConfig()
	mgr := NewCircuitBreakerManager(cfg)

	var wg sync.WaitGroup
	subscriberCount := 10
	requestsPerSubscriber := 100

	for i := 0; i < subscriberCount; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			subID := fmt.Sprintf("concurrent-%d", id)

			for j := 0; j < requestsPerSubscriber; j++ {
				mgr.Execute(context.Background(), subID, func() error {
					return nil
				})
			}
		}(i)
	}

	wg.Wait()

	// Verify all subscribers have circuits
	states := mgr.GetAllStates()
	assert.Len(t, states, subscriberCount)

	// Verify metrics
	metrics := mgr.GetMetrics()
	allowed := metrics["allowed_requests"].(map[string]int)
	for i := 0; i < subscriberCount; i++ {
		subID := fmt.Sprintf("concurrent-%d", i)
		assert.Equal(t, requestsPerSubscriber, allowed[subID])
	}
}

func TestWebhookService_CircuitBreakerDisabled(t *testing.T) {
	ws := NewWebhookService(nil, nil)
	assert.False(t, ws.circuitBreakerEnabled)
	assert.Nil(t, ws.circuitManager)

	// Methods should return safe defaults when disabled
	state := ws.GetCircuitBreakerState("any-id")
	assert.Equal(t, CircuitClosed, state)

	states := ws.GetAllCircuitBreakerStates()
	assert.Empty(t, states)

	metrics := ws.GetCircuitBreakerMetrics()
	assert.Empty(t, metrics)

	// Reset should not panic
	ws.ResetCircuitBreaker("any-id")
}

func TestWebhookService_CircuitBreakerEnabled(t *testing.T) {
	cfg := DefaultCircuitBreakerConfig()
	ws := NewWebhookService(nil, &cfg)

	assert.True(t, ws.circuitBreakerEnabled)
	assert.NotNil(t, ws.circuitManager)

	// Should return empty states initially
	states := ws.GetAllCircuitBreakerStates()
	assert.Empty(t, states)

	// After using a subscriber, state should be trackable
	state := ws.GetCircuitBreakerState("test-webhook-id")
	assert.Equal(t, CircuitClosed, state)
}

func TestWebhookService_CircuitBreakerIntegration(t *testing.T) {
	// Create a test server that fails
	failureCount := atomic.Int32{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		count := failureCount.Add(1)
		if count <= 10 {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	cfg := CircuitBreakerConfig{
		MaxRequests:        100,
		Interval:           10 * time.Second,
		Timeout:            5 * time.Second,
		FailureThreshold:   0.6,
		MinRequests:        3,
		ConsecutiveFailure: 5,
		OpenDuration:       1 * time.Second,
	}

	ws := NewWebhookService(nil, &cfg)

	webhookID := "test-circuit-webhook"
	targetURL := server.URL

	// First few deliveries should fail but not trip circuit immediately
	for i := 0; i < 3; i++ {
		_, _, err := ws.doDelivery(context.Background(), webhookID, targetURL, []byte(`{}`), "sig", "event", "delivery-id")
		assert.Error(t, err) // Server returns 500
	}

	// More failures to trip the circuit
	for i := 0; i < 5; i++ {
		_, _, _ = ws.doDelivery(context.Background(), webhookID, targetURL, []byte(`{}`), "sig", "event", fmt.Sprintf("delivery-%d", i))
	}

	// Circuit should now be open - requests should fail fast
	_, _, err := ws.doDelivery(context.Background(), webhookID, targetURL, []byte(`{}`), "sig", "event", "final-delivery")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "circuit breaker")
}
