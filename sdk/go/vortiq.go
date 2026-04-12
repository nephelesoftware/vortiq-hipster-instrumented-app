// Package vortiq provides automatic OpenTelemetry instrumentation for Go applications.
//
// Usage:
//
//	import "github.com/nephele/vortiq-go-sdk"
//
//	func main() {
//	    shutdown := vortiq.Init("my-service")
//	    defer shutdown()
//
//	    // Your application code — traces are collected automatically
//	    // for gRPC, HTTP, and database calls via OTel instrumentation.
//	}
//
// The SDK:
//   - Configures OpenTelemetry TracerProvider, MeterProvider, and LoggerProvider
//   - Exports traces/metrics/logs to the local Vortiq agent via OTLP (localhost:4317)
//   - Emits container.id so the agent's vortiq_trace_identity processor can
//     enrich every batch with the full three-level identity (service/instance/snapshot)
//   - Auto-discovers the agent endpoint (OTLP on localhost or K8s Service DNS)
//   - Respects standard OTEL_* environment variables for overrides
//
// # Identity model (three-level)
//
// Vortiq uses a three-level identity: ServiceID (stable) + InstanceID (per
// container/pod) + SnapshotID (per process lifecycle). The agent computes the
// authoritative identity during its periodic scan and the vortiq_trace_identity
// processor enriches every trace/metric/log batch with vortiq.service.id,
// vortiq.instance.id, and vortiq.snapshot.id before export.
//
// The SDK's job is to emit the minimum set of attributes the processor needs
// to find the right topology context:
//
//   - container.id       (for containerized processes — matched server-side)
//   - process.pid        (for bare metal fallback)
//   - k8s.pod.name       (for K8s pod matching)
//   - k8s.namespace.name (for K8s pod matching)
//   - k8s.container.name (for K8s pod matching)
//
// In addition, the SDK emits standard OTel semconv attributes so that
// non-Vortiq backends (and pre-enrichment debug views) see coherent identity:
//
//   - service.name        (resolved via P1→P2→P4 chain — same as agent)
//   - service.instance.id (POD_UID → container.id → hostname:pid)
//   - service.namespace   (from POD_NAMESPACE — for multi-tenant backends)
package vortiq

import (
	"context"
	"fmt"
	"os"
	"runtime"
	"runtime/debug"
	"strconv"
	"strings"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	otelruntime "go.opentelemetry.io/contrib/instrumentation/runtime"
	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetricgrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/log/global"
	"go.opentelemetry.io/otel/propagation"
	sdklog "go.opentelemetry.io/otel/sdk/log"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
)

// sdkVersion is the version of the Vortiq Go SDK.
const sdkVersion = "1.1.0"

// InitOption customises the behaviour of Init.
type InitOption func(cfg *initConfig)

// postInitFunc is called after all providers are registered.
// It receives the resolved service name so that log bridges can
// identify the service without duplicating the resolution logic.
type postInitFunc func(serviceName string)

type initConfig struct {
	postInits []postInitFunc
}

// WithPostInit registers a function that is called at the end of Init, after
// all OTel providers have been registered with the global API.  Use this to
// initialise log bridges (e.g. zap, logrus, slog) that need a LoggerProvider
// reference.
func WithPostInit(fn postInitFunc) InitOption {
	return func(cfg *initConfig) {
		cfg.postInits = append(cfg.postInits, fn)
	}
}

// Init initializes Vortiq OpenTelemetry instrumentation for a Go application.
// Returns a shutdown function that must be called on application exit (e.g., defer shutdown()).
//
// The serviceName parameter is a hint, not a declaration. Actual service name
// resolution follows the same priority chain the Vortiq agent uses for every
// runtime detector:
//
//	P1  OTEL_SERVICE_NAME              (user intent — highest authority)
//	P2a K8S_DEPLOYMENT_NAME            (from webhook downward API)
//	P2b k8s label: app.kubernetes.io/name
//	P2c k8s label: app
//	P2d COMPOSE_SERVICE                (Docker Compose)
//	P4  serviceName argument / Go binary name / os.Executable()
//
// This keeps SDK-reported service.name byte-identical to what the Vortiq agent
// would pick for the same process — no drift between client and server sides.
//
// Environment variable overrides:
//   - OTEL_EXPORTER_OTLP_ENDPOINT: Agent OTLP endpoint (default: localhost:4317)
//   - OTEL_SERVICE_NAME: Override service name (P1 in the chain)
//   - OTEL_TRACES_SAMPLER: Sampler type (default: parentbased_traceidratio)
//   - OTEL_TRACES_SAMPLER_ARG: Sampler argument (default: 1.0)
func Init(serviceName string, opts ...InitOption) func() {
	var cfg initConfig
	for _, opt := range opts {
		opt(&cfg)
	}
	ctx := context.Background()

	// Resolve service identity using the same P1→P2→P4 chain as the agent.
	serviceName = resolveServiceName(serviceName)
	serviceNamespace := resolveServiceNamespace()
	instanceID := resolveInstanceID()

	// Resolve OTLP endpoint
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		endpoint = "localhost:4317"
	}
	// Strip scheme if present (gRPC client doesn't want http://)
	endpoint = strings.TrimPrefix(endpoint, "http://")
	endpoint = strings.TrimPrefix(endpoint, "https://")

	// Build resource with service identity, runtime info, and K8s context.
	// The container.id attribute is the primary correlation key for the agent's
	// vortiq_trace_identity processor — it looks up the full 3-ID identity
	// (service/instance/snapshot) in the topology registry and enriches every
	// batch with vortiq.service.id, vortiq.instance.id, vortiq.snapshot.id.
	attrs := []attribute.KeyValue{
		semconv.ServiceName(serviceName),
		semconv.ServiceInstanceID(instanceID),
		semconv.TelemetrySDKLanguageGo,
		semconv.TelemetrySDKNameKey.String("vortiq"),
		semconv.TelemetrySDKVersionKey.String(sdkVersion),
		semconv.ProcessRuntimeName("go"),
		semconv.ProcessRuntimeVersion(runtime.Version()),
		semconv.ProcessPID(os.Getpid()),
	}

	if serviceNamespace != "" {
		attrs = append(attrs, semconv.ServiceNamespace(serviceNamespace))
	}

	// Auto-detect container ID from /proc/self/cgroup. This is the primary
	// correlation key used by the agent's vortiq_trace_identity processor to
	// look up the topology registry and enrich every batch with the full
	// three-level identity. Works for Docker, containerd, CRI-O, and cgroup v2.
	if cid := detectContainerID(); cid != "" {
		attrs = append(attrs, semconv.ContainerID(cid))
	}

	// Add K8s context from environment (set by webhook or downward API).
	// These attributes enable pod-level correlation even when container.id is
	// unavailable (some K8s configurations obscure it).
	if podName := os.Getenv("POD_NAME"); podName != "" {
		attrs = append(attrs, semconv.K8SPodName(podName))
	}
	if namespace := os.Getenv("POD_NAMESPACE"); namespace != "" {
		attrs = append(attrs, semconv.K8SNamespaceName(namespace))
	}
	if podUID := os.Getenv("POD_UID"); podUID != "" {
		attrs = append(attrs, semconv.K8SPodUID(podUID))
	}

	// Parse OTEL_RESOURCE_ATTRIBUTES for k8s.container.name and other K8s attrs
	if resAttrs := os.Getenv("OTEL_RESOURCE_ATTRIBUTES"); resAttrs != "" {
		for _, pair := range strings.Split(resAttrs, ",") {
			kv := strings.SplitN(pair, "=", 2)
			if len(kv) != 2 {
				continue
			}
			key, val := strings.TrimSpace(kv[0]), strings.TrimSpace(kv[1])
			switch key {
			case "k8s.container.name":
				attrs = append(attrs, semconv.K8SContainerName(val))
			case "k8s.pod.name":
				if os.Getenv("POD_NAME") == "" { // don't duplicate
					attrs = append(attrs, semconv.K8SPodName(val))
				}
			case "k8s.namespace.name":
				if os.Getenv("POD_NAMESPACE") == "" {
					attrs = append(attrs, semconv.K8SNamespaceName(val))
				}
			}
		}
	}

	res := resource.NewWithAttributes(semconv.SchemaURL, attrs...)

	var shutdowns []func(context.Context) error

	// Setup trace exporter
	traceExporter, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint(endpoint),
		otlptracegrpc.WithInsecure(),
	)
	if err != nil {
		fmt.Fprintf(os.Stderr, "[vortiq] Failed to create trace exporter: %v\n", err)
		return func() {}
	}

	tracerProvider := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(traceExporter),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.ParentBased(sdktrace.TraceIDRatioBased(1.0))),
	)
	otel.SetTracerProvider(tracerProvider)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))
	shutdowns = append(shutdowns, tracerProvider.Shutdown)

	// Setup metric exporter
	metricExporter, err := otlpmetricgrpc.New(ctx,
		otlpmetricgrpc.WithEndpoint(endpoint),
		otlpmetricgrpc.WithInsecure(),
	)
	if err == nil {
		meterProvider := sdkmetric.NewMeterProvider(
			sdkmetric.WithReader(sdkmetric.NewPeriodicReader(metricExporter,
				sdkmetric.WithInterval(15*time.Second),
			)),
			sdkmetric.WithResource(res),
		)
		otel.SetMeterProvider(meterProvider)
		shutdowns = append(shutdowns, meterProvider.Shutdown)

		// Start Go runtime metrics (GC, goroutines, memory, etc.)
		if err := otelruntime.Start(otelruntime.WithMinimumReadMemStatsInterval(10 * time.Second)); err != nil {
			fmt.Fprintf(os.Stderr, "[vortiq] Failed to start runtime metrics: %v\n", err)
		}
	}

	// Setup log exporter
	logExporter, err := otlploggrpc.New(ctx,
		otlploggrpc.WithEndpoint(endpoint),
		otlploggrpc.WithInsecure(),
	)
	if err == nil {
		loggerProvider := sdklog.NewLoggerProvider(
			sdklog.WithProcessor(NewVortiqLogProcessor(
				sdklog.NewBatchProcessor(logExporter),
				res,
			)),
			sdklog.WithResource(res),
		)
		global.SetLoggerProvider(loggerProvider)
		shutdowns = append(shutdowns, loggerProvider.Shutdown)
	}

	for _, fn := range cfg.postInits {
		fn(serviceName)
	}

	fmt.Fprintf(os.Stderr,
		"[vortiq] Go instrumentation initialized service=%q instance=%q namespace=%q endpoint=%s\n",
		serviceName, instanceID, serviceNamespace, endpoint)

	// Return shutdown function
	return func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		for _, shutdown := range shutdowns {
			if err := shutdown(ctx); err != nil {
				fmt.Fprintf(os.Stderr, "[vortiq] Shutdown error: %v\n", err)
			}
		}
	}
}

// resolveServiceName resolves the service name using the same P1→P2→P4
// priority chain the Vortiq agent applies in every runtime detector
// (pkg/discovery/snapshot_id.go ResolveServiceName).
//
// Priority:
//
//	P1  OTEL_SERVICE_NAME          (user intent — highest authority)
//	P2a K8S_DEPLOYMENT_NAME        (from webhook downward API)
//	P2b k8s label: app.kubernetes.io/name (from K8S_APP_NAME env var)
//	P2c k8s label: app             (from K8S_APP env var)
//	P2d COMPOSE_SERVICE            (Docker Compose)
//	P4  hint (function argument), Go binary name, os.Executable()
//
// Note: "unknown_service" prefix (the OTel default when nothing is set) is
// explicitly rejected to avoid picking up stray defaults.
func resolveServiceName(hint string) string {
	// P1: OTEL_SERVICE_NAME — user intent is highest authority.
	if envName := os.Getenv("OTEL_SERVICE_NAME"); envName != "" {
		if !strings.HasPrefix(envName, "unknown_service") {
			return envName
		}
	}

	// P2a: K8s deployment name (set by webhook if it has access to ownerReferences,
	// or by downward API on pods that expose the deployment label).
	if depName := os.Getenv("K8S_DEPLOYMENT_NAME"); depName != "" {
		return depName
	}

	// P2b: k8s label app.kubernetes.io/name (recommended label).
	if appName := os.Getenv("K8S_APP_NAME"); appName != "" {
		return appName
	}

	// P2c: k8s label "app" (de facto standard used by most Helm charts).
	if app := os.Getenv("K8S_APP"); app != "" {
		return app
	}

	// P2d: Docker Compose service name.
	if composeSvc := os.Getenv("COMPOSE_SERVICE"); composeSvc != "" {
		return composeSvc
	}

	// P4a: Hint from the Init() argument.
	if hint != "" {
		return hint
	}

	// P4b: Go build info (module path).
	if info, ok := debug.ReadBuildInfo(); ok && info.Path != "" {
		parts := strings.Split(info.Path, "/")
		return parts[len(parts)-1]
	}

	// P4c: Executable name.
	if exe, err := os.Executable(); err == nil {
		parts := strings.Split(exe, "/")
		if name := parts[len(parts)-1]; name != "" {
			return name
		}
	}

	return "go-service"
}

// resolveServiceNamespace resolves service.namespace from K8s namespace or
// Docker Compose project name. Returns empty string when neither is available
// (bare metal deployments typically don't have a namespace concept).
func resolveServiceNamespace() string {
	if ns := os.Getenv("POD_NAMESPACE"); ns != "" {
		return ns
	}
	// Parse OTEL_RESOURCE_ATTRIBUTES as fallback (webhook may set it there).
	if resAttrs := os.Getenv("OTEL_RESOURCE_ATTRIBUTES"); resAttrs != "" {
		for _, pair := range strings.Split(resAttrs, ",") {
			kv := strings.SplitN(pair, "=", 2)
			if len(kv) == 2 && strings.TrimSpace(kv[0]) == "k8s.namespace.name" {
				return strings.TrimSpace(kv[1])
			}
		}
	}
	// Docker Compose project name acts as a namespace for multi-service apps.
	if project := os.Getenv("COMPOSE_PROJECT_NAME"); project != "" {
		return project
	}
	return ""
}

// resolveInstanceID resolves service.instance.id with a fallback chain that
// produces a stable identifier for the lifecycle of this container/pod:
//
//	1. POD_UID          (K8s — stable across container restarts within the pod)
//	2. container.id     (Docker/containerd/CRI-O/podman — stable per container)
//	3. hostname:pid     (bare metal — unique per process)
//
// service.instance.id is required by OTel semantic conventions and is used by
// non-Vortiq backends (Jaeger, Tempo, vendor backends) to identify distinct
// replicas. Vortiq itself uses vortiq.instance.id which is added server-side
// by the agent's trace identity processor.
func resolveInstanceID() string {
	// Tier 1: K8s pod UID — the most stable identifier.
	if uid := os.Getenv("POD_UID"); uid != "" {
		return uid
	}
	// Parse OTEL_RESOURCE_ATTRIBUTES for k8s.pod.uid as a fallback.
	if resAttrs := os.Getenv("OTEL_RESOURCE_ATTRIBUTES"); resAttrs != "" {
		for _, pair := range strings.Split(resAttrs, ",") {
			kv := strings.SplitN(pair, "=", 2)
			if len(kv) == 2 && strings.TrimSpace(kv[0]) == "k8s.pod.uid" {
				if val := strings.TrimSpace(kv[1]); val != "" {
					return val
				}
			}
		}
	}

	// Tier 2: container.id from cgroup.
	if cid := detectContainerID(); cid != "" {
		return cid
	}

	// Tier 3: bare metal — hostname:pid.
	hostname, err := os.Hostname()
	if err != nil || hostname == "" {
		hostname = "unknown-host"
	}
	return fmt.Sprintf("%s:%d", hostname, os.Getpid())
}

// detectContainerID extracts the container ID using two methods:
//  1. /proc/self/cgroup — works on cgroup v1 (Docker, containerd, CRI-O)
//  2. /proc/self/mountinfo — fallback for cgroup v2 where cgroup shows only "0::/"
//
// Returns empty string if not running in a container.
func detectContainerID() string {
	// Method 1: cgroup (v1 and some v2 configurations)
	if data, err := os.ReadFile("/proc/self/cgroup"); err == nil {
		for _, line := range strings.Split(string(data), "\n") {
			parts := strings.Split(line, "/")
			if len(parts) < 2 {
				continue
			}
			last := parts[len(parts)-1]
			// Docker cgroup v2: "docker-<id>.scope"
			if strings.HasPrefix(last, "docker-") && strings.HasSuffix(last, ".scope") {
				id := strings.TrimPrefix(last, "docker-")
				id = strings.TrimSuffix(id, ".scope")
				if len(id) == 64 && isHex(id) {
					return id
				}
			}
			// Standard cgroup v1: last segment is 64-char hex container ID
			if len(last) == 64 && isHex(last) {
				return last
			}
		}
	}

	// Method 2: mountinfo — extract from Docker overlay mount paths.
	// /proc/self/mountinfo contains lines like:
	//   "... /var/lib/docker/containers/<container_id>/hostname /etc/hostname ..."
	if data, err := os.ReadFile("/proc/self/mountinfo"); err == nil {
		for _, line := range strings.Split(string(data), "\n") {
			// Look for /docker/containers/<64-hex-id>/ or /containers/<64-hex-id>/
			idx := strings.Index(line, "/containers/")
			if idx < 0 {
				continue
			}
			rest := line[idx+len("/containers/"):]
			if slashIdx := strings.Index(rest, "/"); slashIdx == 64 {
				id := rest[:64]
				if isHex(id) {
					return id
				}
			}
		}
	}

	return ""
}

// isHex checks if a string contains only hexadecimal characters.
func isHex(s string) bool {
	for _, c := range s {
		if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')) {
			return false
		}
	}
	return true
}

// Pid returns the current process ID as a string.
func Pid() string {
	return strconv.Itoa(os.Getpid())
}
