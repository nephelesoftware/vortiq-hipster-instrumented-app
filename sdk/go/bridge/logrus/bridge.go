// Package logrus connects the logrus logger to the Vortiq OTel LoggerProvider.
//
// Usage:
//
//	import vortiqlogrus "github.com/nephele/vortiq-go-sdk/bridge/logrus"
//
//	shutdown := vortiq.Init("my-service", vortiqlogrus.Bridge())
package logrus

import (
	"github.com/sirupsen/logrus"
	otellogrus "go.opentelemetry.io/contrib/bridges/otellogrus"

	vortiq "github.com/nephele/vortiq-go-sdk"
)

// Bridge returns an InitOption that registers an OTel log hook on the
// global logrus logger.
func Bridge() vortiq.InitOption {
	return vortiq.WithPostInit(func(serviceName string) {
		logrus.AddHook(otellogrus.NewHook(serviceName))
	})
}
