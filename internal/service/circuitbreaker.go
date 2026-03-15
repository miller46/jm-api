package service

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"sync"
	"time"

	"github.com/sony/gobreaker"
)

// CircuitBreakerConfig holds configuration for circuit breakers
type CircuitBreakerConfig struct {
	MaxRequests        uint32        // Max requests in half-open state
	Interval           time.Duration // Statistical window
	Timeout            time.Duration // Request timeout
	FailureThreshold   float64       // Trip circuit at this failure rate (0-1)
	MinRequests        uint32        // Min requests before tripping
	ConsecutiveFailure uint32        // Trip after this many consecutive failures
	OpenDuration       time.Duration // How long to stay open before half-open
}

// DefaultCircuitBreakerConfig returns default configuration
func DefaultCircuitBreakerConfig() CircuitBreakerConfig {
	return CircuitBreakerConfig{
		MaxRequests:        100,
		Interval:           10 * time.Second,
		Timeout:            30 * time.Second,
		FailureThreshold:   0.6, // 60%
		MinRequests:        3,
		ConsecutiveFailure: 5,
		OpenDuration:       30 * time.Second,
	}
}

// CircuitState represents the state of a circuit breaker
type CircuitState int

const (
	CircuitClosed   CircuitState = iota // Normal operation
	CircuitOpen                         // Failing fast
	CircuitHalfOpen                     // Testing recovery
)

func (s CircuitState) String() string {
	switch s {
	case CircuitClosed:
		return "closed"
	case CircuitOpen:
		return "open"
	case CircuitHalfOpen:
		return "half-open"
	default:
		return "unknown"
	}
}

// CircuitBreakerManager manages per-subscriber circuit breakers
type CircuitBreakerManager struct {
	config   CircuitBreakerConfig
	circuits sync.Map // subscriberID -> *gobreaker.CircuitBreaker
	metrics  *CircuitBreakerMetrics
}

// CircuitBreakerMetrics tracks circuit breaker metrics
type CircuitBreakerMetrics struct {
	stateChanges    map[string]int // subscriber -> count
	allowedRequests map[string]int // subscriber -> count
	blockedRequests map[string]int // subscriber -> count
	mu              sync.RWMutex
}

// NewCircuitBreakerMetrics creates a new metrics collector
func NewCircuitBreakerMetrics() *CircuitBreakerMetrics {
	return &CircuitBreakerMetrics{
		stateChanges:    make(map[string]int),
		allowedRequests: make(map[string]int),
		blockedRequests: make(map[string]int),
	}
}

// RecordStateChange records a circuit state change
func (m *CircuitBreakerMetrics) RecordStateChange(subscriberID string, from, to CircuitState) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.stateChanges[subscriberID]++
	slog.Info("circuit breaker state changed",
		"subscriber_id", subscriberID,
		"from", from,
		"to", to,
	)
}

// RecordAllowed records an allowed request
func (m *CircuitBreakerMetrics) RecordAllowed(subscriberID string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.allowedRequests[subscriberID]++
}

// RecordBlocked records a blocked request
func (m *CircuitBreakerMetrics) RecordBlocked(subscriberID string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.blockedRequests[subscriberID]++
}

// GetMetrics returns current metrics
func (m *CircuitBreakerMetrics) GetMetrics() map[string]interface{} {
	m.mu.RLock()
	defer m.mu.RUnlock()

	return map[string]interface{}{
		"state_changes":    copyMap(m.stateChanges),
		"allowed_requests": copyMap(m.allowedRequests),
		"blocked_requests": copyMap(m.blockedRequests),
	}
}

func copyMap(m map[string]int) map[string]int {
	result := make(map[string]int, len(m))
	for k, v := range m {
		result[k] = v
	}
	return result
}

// NewCircuitBreakerManager creates a new circuit breaker manager
func NewCircuitBreakerManager(config CircuitBreakerConfig) *CircuitBreakerManager {
	return &CircuitBreakerManager{
		config:  config,
		metrics: NewCircuitBreakerMetrics(),
	}
}

// GetCircuitBreaker gets or creates a circuit breaker for a subscriber
func (m *CircuitBreakerManager) GetCircuitBreaker(subscriberID string) *gobreaker.CircuitBreaker {
	if cb, ok := m.circuits.Load(subscriberID); ok {
		return cb.(*gobreaker.CircuitBreaker)
	}

	settings := gobreaker.Settings{
		Name:        fmt.Sprintf("webhook-%s", subscriberID),
		MaxRequests: m.config.MaxRequests,
		Interval:    m.config.Interval,
		Timeout:     m.config.Timeout,
		ReadyToTrip: func(counts gobreaker.Counts) bool {
			// Trip if we've seen enough requests AND (failure rate exceeds threshold OR consecutive failures too high)
			if counts.Requests < m.config.MinRequests {
				return false
			}
			failureRate := float64(counts.TotalFailures) / float64(counts.Requests)
			if failureRate >= m.config.FailureThreshold {
				return true
			}
			if counts.ConsecutiveFailures >= m.config.ConsecutiveFailure {
				return true
			}
			return false
		},
		OnStateChange: func(name string, from gobreaker.State, to gobreaker.State) {
			m.metrics.RecordStateChange(subscriberID, gobreakerStateToCircuitState(from), gobreakerStateToCircuitState(to))
		},
	}

	cb := gobreaker.NewCircuitBreaker(settings)
	actual, loaded := m.circuits.LoadOrStore(subscriberID, cb)
	if loaded {
		return actual.(*gobreaker.CircuitBreaker)
	}
	return cb
}

// Execute executes a function with circuit breaker protection
func (m *CircuitBreakerManager) Execute(ctx context.Context, subscriberID string, fn func() error) error {
	cb := m.GetCircuitBreaker(subscriberID)

	_, err := cb.Execute(func() (interface{}, error) {
		return nil, fn()
	})

	if err == gobreaker.ErrOpenState {
		m.metrics.RecordBlocked(subscriberID)
		return fmt.Errorf("circuit breaker open for subscriber %s: %w", subscriberID, err)
	}

	m.metrics.RecordAllowed(subscriberID)
	return err
}

// DoHTTPRequest executes an HTTP request with circuit breaker protection
func (m *CircuitBreakerManager) DoHTTPRequest(ctx context.Context, subscriberID string, client *http.Client, req *http.Request) (*http.Response, error) {
	cb := m.GetCircuitBreaker(subscriberID)

	result, err := cb.Execute(func() (interface{}, error) {
		// Clone request to avoid issues with body reuse
		reqCopy := req.Clone(ctx)
		resp, err := client.Do(reqCopy)
		if err != nil {
			return nil, err
		}
		// For circuit breaker purposes, treat non-2xx as errors
		if resp.StatusCode >= 500 {
			// Server errors count as failures
			return resp, fmt.Errorf("server error: %d", resp.StatusCode)
		}
		return resp, nil
	})

	if err == gobreaker.ErrOpenState {
		m.metrics.RecordBlocked(subscriberID)
		return nil, fmt.Errorf("circuit breaker open for subscriber %s: %w", subscriberID, err)
	}

	if err != nil {
		return nil, err
	}

	m.metrics.RecordAllowed(subscriberID)
	return result.(*http.Response), nil
}

// GetState returns the current state of a subscriber's circuit breaker
func (m *CircuitBreakerManager) GetState(subscriberID string) CircuitState {
	if cb, ok := m.circuits.Load(subscriberID); ok {
		return gobreakerStateToCircuitState(cb.(*gobreaker.CircuitBreaker).State())
	}
	return CircuitClosed // Default to closed if no circuit exists yet
}

// GetAllStates returns the state of all circuit breakers
func (m *CircuitBreakerManager) GetAllStates() map[string]CircuitState {
	states := make(map[string]CircuitState)
	m.circuits.Range(func(key, value interface{}) bool {
		subscriberID := key.(string)
		cb := value.(*gobreaker.CircuitBreaker)
		states[subscriberID] = gobreakerStateToCircuitState(cb.State())
		return true
	})
	return states
}

// GetMetrics returns circuit breaker metrics
func (m *CircuitBreakerManager) GetMetrics() map[string]interface{} {
	return m.metrics.GetMetrics()
}

// gobreakerStateToCircuitState converts gobreaker state to our CircuitState
func gobreakerStateToCircuitState(state gobreaker.State) CircuitState {
	switch state {
	case gobreaker.StateClosed:
		return CircuitClosed
	case gobreaker.StateOpen:
		return CircuitOpen
	case gobreaker.StateHalfOpen:
		return CircuitHalfOpen
	default:
		return CircuitClosed
	}
}

// Reset resets a specific circuit breaker
func (m *CircuitBreakerManager) Reset(subscriberID string) {
	m.circuits.Delete(subscriberID)
	slog.Info("circuit breaker reset", "subscriber_id", subscriberID)
}
