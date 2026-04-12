package middleware

import (
	"database/sql"

	"go.nhat.io/otelsql"
)

// OpenSQL opens a database connection with OpenTelemetry instrumentation.
// It registers a wrapped driver and opens a connection using it.
func OpenSQL(driverName, dsn string) (*sql.DB, error) {
	wrappedDriver, err := otelsql.Register(driverName)
	if err != nil {
		return nil, err
	}
	return sql.Open(wrappedDriver, dsn)
}
