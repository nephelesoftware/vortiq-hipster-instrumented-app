# Vortiq Go SDK

Automatic OpenTelemetry instrumentation for Go applications.

## Installation

```bash
go get github.com/nephele/vortiq-go-sdk
```

## Quick Start

```go
package main

import (
    vortiq "github.com/nephele/vortiq-go-sdk"

    // Add OTel instrumentation for your frameworks:
    "go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
    "go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

func main() {
    // Initialize Vortiq instrumentation (one line)
    shutdown := vortiq.Init("my-service")
    defer shutdown()

    // gRPC server with automatic tracing
    s := grpc.NewServer(
        grpc.StatsHandler(otelgrpc.NewServerHandler()),
    )

    // HTTP server with automatic tracing
    http.Handle("/", otelhttp.NewHandler(myHandler, "my-endpoint"))

    // Your application code...
}
```

## What It Does

1. Configures OpenTelemetry TracerProvider, MeterProvider, and LoggerProvider
2. Exports traces/metrics/logs to the local Vortiq agent via OTLP gRPC (localhost:4317)
3. Announces the process to the agent for topology correlation
4. Sets up W3C TraceContext propagation

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `localhost:4317` | Agent OTLP gRPC endpoint |
| `OTEL_SERVICE_NAME` | Binary name | Override service name |
| `VORTIQ_AGENT_ENDPOINT` | `http://localhost:4318` | Agent HTTP endpoint for announce |

## Framework Instrumentation

Add OTel instrumentation libraries for automatic trace collection:

```bash
# gRPC
go get go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc

# net/http
go get go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp

# database/sql
go get go.opentelemetry.io/contrib/instrumentation/database/sql/otelsql

# Redis
go get go.opentelemetry.io/contrib/instrumentation/github.com/go-redis/redis/otelredis
```
