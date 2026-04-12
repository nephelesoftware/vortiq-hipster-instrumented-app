// Package vortiq — log processor and endpoint context helpers.
package vortiq

import (
	"context"

	"go.opentelemetry.io/otel/log"
	sdklog "go.opentelemetry.io/otel/sdk/log"
	"go.opentelemetry.io/otel/sdk/resource"
	"go.opentelemetry.io/otel/trace"
)

// ─── Endpoint context ────────────────────────────────────────────────────────

type endpointContextKey struct{}

// EndpointInfo carries the logical endpoint name and type for a request.
type EndpointInfo struct {
	Name string
	Type string
}

// WithEndpoint stores endpoint information in the context so that
// VortiqLogProcessor can stamp it on every log record emitted inside the span.
func WithEndpoint(ctx context.Context, name, endpointType string) context.Context {
	return context.WithValue(ctx, endpointContextKey{}, &EndpointInfo{Name: name, Type: endpointType})
}

// EndpointFromContext retrieves the EndpointInfo stored by WithEndpoint.
// Returns nil when no endpoint is in context.
func EndpointFromContext(ctx context.Context) *EndpointInfo {
	v, _ := ctx.Value(endpointContextKey{}).(*EndpointInfo)
	return v
}

// ─── VortiqLogProcessor ───────────────────────────────────────────────────────

// VortiqLogProcessor is an OTel SDK log processor that stamps
// vortiq.parent.* attributes on every log record emitted inside an active span.
// When there is no recording span the record is passed through unmodified.
type VortiqLogProcessor struct {
	inner       sdklog.Processor
	serviceName string
	serviceID   string
}

// NewVortiqLogProcessor returns a VortiqLogProcessor that delegates to inner
// after stamping the vortiq.parent.* context attributes.
//
// serviceName and serviceID are read from the resource once at construction
// time so that attribute extraction is not repeated per-record.
func NewVortiqLogProcessor(inner sdklog.Processor, res *resource.Resource) *VortiqLogProcessor {
	p := &VortiqLogProcessor{inner: inner}
	if res != nil {
		for _, kv := range res.Attributes() {
			switch string(kv.Key) {
			case "service.name":
				p.serviceName = kv.Value.AsString()
			case "vortiq.service.id":
				p.serviceID = kv.Value.AsString()
			}
		}
	}
	return p
}

// OnEmit stamps vortiq.parent.* attributes when a recording span is active,
// then delegates to the inner processor.
func (p *VortiqLogProcessor) OnEmit(ctx context.Context, record *sdklog.Record) error {
	if trace.SpanFromContext(ctx).IsRecording() {
		attrs := make([]log.KeyValue, 0, 4)

		if p.serviceName != "" {
			attrs = append(attrs, log.String("vortiq.parent.service_name", p.serviceName))
		}
		if p.serviceID != "" {
			attrs = append(attrs, log.String("vortiq.parent.service_id", p.serviceID))
		}

		if ep := EndpointFromContext(ctx); ep != nil {
			if ep.Name != "" {
				attrs = append(attrs, log.String("vortiq.parent.endpoint_name", ep.Name))
			}
			if ep.Type != "" {
				attrs = append(attrs, log.String("vortiq.parent.endpoint_type", ep.Type))
			}
		}

		if len(attrs) > 0 {
			record.AddAttributes(attrs...)
		}
	}
	return p.inner.OnEmit(ctx, record)
}

// Shutdown delegates to the inner processor.
func (p *VortiqLogProcessor) Shutdown(ctx context.Context) error {
	return p.inner.Shutdown(ctx)
}

// ForceFlush delegates to the inner processor.
func (p *VortiqLogProcessor) ForceFlush(ctx context.Context) error {
	return p.inner.ForceFlush(ctx)
}

// Compile-time assertion: VortiqLogProcessor must satisfy sdklog.Processor.
var _ sdklog.Processor = (*VortiqLogProcessor)(nil)

