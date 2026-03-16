package observability

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var dbConnectionAttemptsTotal = promauto.NewCounterVec(
	prometheus.CounterOpts{
		Name: "db_connection_attempts_total",
		Help: "Total database connection attempts by result",
	},
	[]string{"result"},
)

func ObserveDBConnectionAttempt(result string) {
	dbConnectionAttemptsTotal.WithLabelValues(result).Inc()
}
