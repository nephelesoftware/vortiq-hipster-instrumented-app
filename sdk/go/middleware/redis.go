package middleware

import (
	"github.com/redis/go-redis/extra/redisotel/v9"
	"github.com/redis/go-redis/v9"
)

// InstrumentRedis adds OpenTelemetry tracing and metrics to a go-redis client.
func InstrumentRedis(rdb *redis.Client) error {
	if err := redisotel.InstrumentTracing(rdb); err != nil {
		return err
	}
	if err := redisotel.InstrumentMetrics(rdb); err != nil {
		return err
	}
	return nil
}
