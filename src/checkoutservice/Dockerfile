FROM golang:1.24-alpine AS builder
WORKDIR /build/src
COPY ./sdk/go/ /build/sdk/go/
COPY ./src/checkoutservice/ .
RUN go mod edit \
      -go=1.22 \
      -require github.com/nephele/vortiq-go-sdk@v0.0.0 \
      -require github.com/nephele/vortiq-go-sdk/bridge/logrus@v0.0.0 \
      -replace github.com/nephele/vortiq-go-sdk=/build/sdk/go \
      -replace github.com/nephele/vortiq-go-sdk/bridge/logrus=/build/sdk/go/bridge/logrus \
      -require github.com/sirupsen/logrus@v1.9.3 \
      -droprequire google.golang.org/genproto \
      -droprequire go.opencensus.io \
      -droprequire go.opentelemetry.io/otel \
      -droprequire go.opentelemetry.io/otel/sdk \
      -droprequire go.opentelemetry.io/otel/exporters/trace/jaeger \
      -droprequire go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc && \
    GONOSUMCHECK='*' GOFLAGS='-mod=mod' CGO_ENABLED=0 go build -ldflags "-s -w" -tags netgo -o /checkoutservice .

FROM alpine AS release
RUN apk add --no-cache ca-certificates procps
RUN GRPC_HEALTH_PROBE_VERSION=v0.2.0 && \
    wget -qO/bin/grpc_health_probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 && \
    chmod +x /bin/grpc_health_probe
COPY --from=builder /checkoutservice /checkoutservice
EXPOSE 5050
ENTRYPOINT ["/checkoutservice"]
