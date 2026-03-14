package middleware

import (
	"net/http"
	"sync/atomic"
)

type ShutdownGuard struct {
	shuttingDown atomic.Bool
	activeReqs   atomic.Int64
}

func NewShutdownGuard() *ShutdownGuard {
	return &ShutdownGuard{}
}

func (sg *ShutdownGuard) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if sg.shuttingDown.Load() {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusServiceUnavailable)
			w.Write([]byte(`{"error":"server is shutting down"}`))
			return
		}
		sg.activeReqs.Add(1)
		defer sg.activeReqs.Add(-1)
		next.ServeHTTP(w, r)
	})
}

func (sg *ShutdownGuard) StartShutdown() {
	sg.shuttingDown.Store(true)
}

func (sg *ShutdownGuard) ActiveRequests() int64 {
	return sg.activeReqs.Load()
}

func (sg *ShutdownGuard) IsShuttingDown() bool {
	return sg.shuttingDown.Load()
}
