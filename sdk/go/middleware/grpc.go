package middleware

import (
	"context"

	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"google.golang.org/grpc"
	"google.golang.org/grpc/stats"
	vortiq "github.com/nephele/vortiq-go-sdk"
)

// GRPCServer returns a grpc.ServerOption that instruments the gRPC server with
// OpenTelemetry tracing and injects the endpoint context (gRPC method name)
// so that VortiqLogProcessor can stamp vortiq.parent.endpoint_name on every
// log record emitted inside a handler.
func GRPCServer() grpc.ServerOption {
	return grpc.StatsHandler(&endpointInjectingHandler{
		inner: otelgrpc.NewServerHandler(),
	})
}

// GRPCClient returns a grpc.DialOption that instruments the gRPC client.
func GRPCClient() grpc.DialOption {
	return grpc.WithStatsHandler(otelgrpc.NewClientHandler())
}

// endpointInjectingHandler is a stats.Handler that wraps otelgrpc's server
// handler and injects the gRPC full method name as endpoint context.
// TagRPC is called after otelgrpc creates the span, so the span is already
// active when we stamp the endpoint.
type endpointInjectingHandler struct {
	inner stats.Handler
}

func (h *endpointInjectingHandler) TagRPC(ctx context.Context, info *stats.RPCTagInfo) context.Context {
	// Let otelgrpc create/attach the span first.
	ctx = h.inner.TagRPC(ctx, info)
	// Stamp endpoint so VortiqLogProcessor can attach it to log records.
	return vortiq.WithEndpoint(ctx, info.FullMethodName, "RPC")
}

func (h *endpointInjectingHandler) HandleRPC(ctx context.Context, s stats.RPCStats) {
	h.inner.HandleRPC(ctx, s)
}

func (h *endpointInjectingHandler) TagConn(ctx context.Context, info *stats.ConnTagInfo) context.Context {
	return h.inner.TagConn(ctx, info)
}

func (h *endpointInjectingHandler) HandleConn(ctx context.Context, s stats.ConnStats) {
	h.inner.HandleConn(ctx, s)
}
