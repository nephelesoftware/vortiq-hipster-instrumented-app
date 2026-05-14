package vortiq

import (
	"context"
	"testing"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/log"
	sdklog "go.opentelemetry.io/otel/sdk/log"
	"go.opentelemetry.io/otel/sdk/log/logtest"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
)

// captureProcessor stores every record passed to OnEmit for inspection.
type captureProcessor struct {
	records  []*sdklog.Record
	shutdown bool
	flush    bool
}

func (c *captureProcessor) OnEmit(_ context.Context, record *sdklog.Record) error {
	c.records = append(c.records, record)
	return nil
}

func (c *captureProcessor) Shutdown(_ context.Context) error {
	c.shutdown = true
	return nil
}

func (c *captureProcessor) ForceFlush(_ context.Context) error {
	c.flush = true
	return nil
}

// newTestRecord returns a Record with no attribute limits so that string values
// are not silently truncated to zero length (the zero-value limit for a bare
// sdklog.Record). Tests MUST use this helper to create records.
func newTestRecord(body string) sdklog.Record {
	return logtest.RecordFactory{
		Body:                      log.StringValue(body),
		AttributeValueLengthLimit: -1, // unlimited
		AttributeCountLimit:       -1, // unlimited
	}.NewRecord()
}

// attrValue returns the string value of an attribute key on a record, or "".
func attrValue(record *sdklog.Record, key string) string {
	var val string
	record.WalkAttributes(func(kv log.KeyValue) bool {
		if string(kv.Key) == key {
			val = kv.Value.AsString()
			return false
		}
		return true
	})
	return val
}

// hasAttrKey returns true if the record has an attribute with the given key.
func hasAttrKey(record *sdklog.Record, key string) bool {
	found := false
	record.WalkAttributes(func(kv log.KeyValue) bool {
		if string(kv.Key) == key {
			found = true
			return false
		}
		return true
	})
	return found
}

// TestVortiqLogProcessor_StampsParentAttrs verifies that when a log is emitted
// inside a recording span with an endpoint in context, the processor stamps
// vortiq.parent.service_name, vortiq.parent.endpoint_name, and
// vortiq.parent.endpoint_type on the record.
func TestVortiqLogProcessor_StampsParentAttrs(t *testing.T) {
	// Build a TracerProvider with an in-memory exporter so spans are "recording".
	exp := tracetest.NewInMemoryExporter()
	tp := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exp))
	tracer := tp.Tracer("test")

	// Build a resource with service.name and vortiq.service.id.
	res := resource.NewWithAttributes(
		semconv.SchemaURL,
		semconv.ServiceNameKey.String("cart-service"),
		attribute.String("vortiq.service.id", "svc-abc-123"),
	)

	cap := &captureProcessor{}
	proc := NewVortiqLogProcessor(cap, res)

	// Start a real recording span.
	ctx, span := tracer.Start(context.Background(), "checkout")
	defer span.End()

	// Inject endpoint.
	ctx = WithEndpoint(ctx, "/cart/checkout", "HTTP")

	// Emit a log record with unlimited attribute limits.
	rec := newTestRecord("test log")
	if err := proc.OnEmit(ctx, &rec); err != nil {
		t.Fatalf("OnEmit returned error: %v", err)
	}

	if len(cap.records) != 1 {
		t.Fatalf("expected 1 captured record, got %d", len(cap.records))
	}
	r := cap.records[0]

	if got := attrValue(r, "vortiq.parent.service_name"); got != "cart-service" {
		t.Errorf("vortiq.parent.service_name = %q, want %q", got, "cart-service")
	}
	if got := attrValue(r, "vortiq.parent.endpoint_name"); got != "/cart/checkout" {
		t.Errorf("vortiq.parent.endpoint_name = %q, want %q", got, "/cart/checkout")
	}
	if got := attrValue(r, "vortiq.parent.endpoint_type"); got != "HTTP" {
		t.Errorf("vortiq.parent.endpoint_type = %q, want %q", got, "HTTP")
	}
}

// TestVortiqLogProcessor_NoSpan verifies that when there is no recording span
// in the context, no vortiq.parent.* attributes are added.
func TestVortiqLogProcessor_NoSpan(t *testing.T) {
	res := resource.NewWithAttributes(
		semconv.SchemaURL,
		semconv.ServiceNameKey.String("cart-service"),
	)

	cap := &captureProcessor{}
	proc := NewVortiqLogProcessor(cap, res)

	// Bare context — no span.
	rec := newTestRecord("no span log")
	if err := proc.OnEmit(context.Background(), &rec); err != nil {
		t.Fatalf("OnEmit returned error: %v", err)
	}

	if len(cap.records) != 1 {
		t.Fatalf("expected 1 captured record, got %d", len(cap.records))
	}
	r := cap.records[0]

	for _, key := range []string{
		"vortiq.parent.service_name",
		"vortiq.parent.service_id",
		"vortiq.parent.endpoint_name",
		"vortiq.parent.endpoint_type",
	} {
		if hasAttrKey(r, key) {
			t.Errorf("expected no attribute %q on record without span, but found it", key)
		}
	}
}

// TestVortiqLogProcessor_DelegatesShutdown verifies that Shutdown and
// ForceFlush are forwarded to the inner processor.
func TestVortiqLogProcessor_DelegatesShutdown(t *testing.T) {
	cap := &captureProcessor{}
	proc := NewVortiqLogProcessor(cap, nil)

	if err := proc.Shutdown(context.Background()); err != nil {
		t.Fatalf("Shutdown error: %v", err)
	}
	if !cap.shutdown {
		t.Error("Shutdown was not delegated to inner processor")
	}

	if err := proc.ForceFlush(context.Background()); err != nil {
		t.Fatalf("ForceFlush error: %v", err)
	}
	if !cap.flush {
		t.Error("ForceFlush was not delegated to inner processor")
	}
}
