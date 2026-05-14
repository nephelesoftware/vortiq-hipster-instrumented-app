// Package zap connects Uber's zap logger to the Vortiq OTel LoggerProvider.
//
// Usage:
//
//	import vortiqzap "github.com/nephele/vortiq-go-sdk/bridge/zap"
//
//	shutdown := vortiq.Init("my-service", vortiqzap.Bridge())
package zap

import (
	otelzap "go.opentelemetry.io/contrib/bridges/otelzap"
	"go.uber.org/zap"

	vortiq "github.com/nephele/vortiq-go-sdk"
)

// Bridge returns an InitOption that replaces the global zap logger
// with an OTel-bridged core.
func Bridge() vortiq.InitOption {
	return vortiq.WithPostInit(func(serviceName string) {
		core := otelzap.NewCore(serviceName)
		logger := zap.New(core)
		zap.ReplaceGlobals(logger)
	})
}
