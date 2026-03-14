package observability

import (
	"context"
	"log/slog"
	"math/rand/v2"
	"os"
	"strings"
)

var sensitiveKeys = map[string]bool{
	"password":      true,
	"password_hash": true,
	"token":         true,
	"secret":        true,
	"access_token":  true,
	"refresh_token": true,
	"authorization": true,
}

func SetupLogging(level string, jsonOutput bool, sampleRate float64) {
	var lvl slog.Level
	switch strings.ToUpper(level) {
	case "DEBUG":
		lvl = slog.LevelDebug
	case "WARN", "WARNING":
		lvl = slog.LevelWarn
	case "ERROR":
		lvl = slog.LevelError
	default:
		lvl = slog.LevelInfo
	}

	opts := &slog.HandlerOptions{
		Level: lvl,
		ReplaceAttr: func(groups []string, a slog.Attr) slog.Attr {
			if sensitiveKeys[strings.ToLower(a.Key)] {
				a.Value = slog.StringValue("[REDACTED]")
			}
			return a
		},
	}

	var handler slog.Handler
	if jsonOutput {
		handler = slog.NewJSONHandler(os.Stdout, opts)
	} else {
		handler = slog.NewTextHandler(os.Stdout, opts)
	}

	if sampleRate < 1.0 {
		handler = &samplingHandler{inner: handler, rate: sampleRate}
	}

	slog.SetDefault(slog.New(handler))
}

type samplingHandler struct {
	inner slog.Handler
	rate  float64
}

func (h *samplingHandler) Enabled(ctx context.Context, level slog.Level) bool {
	return h.inner.Enabled(ctx, level)
}

func (h *samplingHandler) Handle(ctx context.Context, r slog.Record) error {
	if r.Level >= slog.LevelWarn {
		return h.inner.Handle(ctx, r)
	}
	if rand.Float64() < h.rate {
		return h.inner.Handle(ctx, r)
	}
	return nil
}

func (h *samplingHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return &samplingHandler{inner: h.inner.WithAttrs(attrs), rate: h.rate}
}

func (h *samplingHandler) WithGroup(name string) slog.Handler {
	return &samplingHandler{inner: h.inner.WithGroup(name), rate: h.rate}
}
