// Package slog connects Go's standard slog to the Vortiq OTel LoggerProvider.
//
// Usage:
//
//	import vortiqslog "github.com/nephele/vortiq-go-sdk/bridge/slog"
//
//	shutdown := vortiq.Init("my-service", vortiqslog.Bridge())
package slog

import (
	"log/slog"

	otelslog "go.opentelemetry.io/contrib/bridges/otelslog"

	vortiq "github.com/nephele/vortiq-go-sdk"
)

// Bridge returns an InitOption that replaces the default slog handler
// with an OTel bridge.
func Bridge() vortiq.InitOption {
	return vortiq.WithPostInit(func(serviceName string) {
		slog.SetDefault(slog.New(otelslog.NewHandler(serviceName)))
	})
}
