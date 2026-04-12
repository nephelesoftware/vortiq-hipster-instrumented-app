// Package middleware provides convenience wrappers for common Go framework
// instrumentation using OpenTelemetry contrib packages.
package middleware

import (
	"net/http"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	vortiq "github.com/nephele/vortiq-go-sdk"
)

// HTTP wraps an http.Handler with OpenTelemetry tracing and metrics.
// The endpoint name is injected into the context (via vortiq.WithEndpoint)
// INSIDE otelhttp so that the span is already active when the endpoint context
// is set — enabling VortiqLogProcessor to stamp vortiq.parent.endpoint_name
// on log records emitted by the handler.
func HTTP(handler http.Handler, opts ...otelhttp.Option) http.Handler {
	return otelhttp.NewHandler(endpointInjector(handler), "", opts...)
}

// HTTPFunc wraps an http.HandlerFunc with OpenTelemetry tracing and metrics.
func HTTPFunc(handler http.HandlerFunc, opts ...otelhttp.Option) http.Handler {
	return otelhttp.NewHandler(endpointInjector(handler), "", opts...)
}

// HTTPTransport wraps an http.RoundTripper with OpenTelemetry tracing for outgoing HTTP calls.
func HTTPTransport(base http.RoundTripper, opts ...otelhttp.Option) http.RoundTripper {
	return otelhttp.NewTransport(base, opts...)
}

// endpointInjector wraps a handler to inject endpoint context after otelhttp
// has created the span but before the inner handler runs.
// On Go 1.22+ r.Pattern carries the registered route pattern; on earlier
// versions we fall back to r.URL.Path.
func endpointInjector(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		route := r.Pattern
		if route == "" {
			route = r.URL.Path
		}
		ctx := vortiq.WithEndpoint(r.Context(), route, "HTTP")
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}
