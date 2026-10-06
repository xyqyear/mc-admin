package system

import (
	"context"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"

	"mc-admin/e2e/internal/api"
)

func TestConfigurationOracleRejectsBadPersistenceWithoutChangingBaseline(t *testing.T) {
	for _, test := range []struct {
		name, get string
		invalid   bool
	}{
		{"invalid update persisted", `{"config_data":{"dns_ttl":90}}`, true},
		{"missing acknowledged field", `{"config_data":{}}`, false},
		{"valid persistence", `{"config_data":{"dns_ttl":45}}`, false},
		{"invalid update rejected", `{"config_data":{"dns_ttl":45}}`, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path != "/api/config/modules/dns" {
					t.Errorf("unexpected request %s", r.URL)
				}
				if r.Method == "PUT" {
					w.WriteHeader(400)
					_, _ = w.Write([]byte(`{"detail":"invalid"}`))
					return
				}
				_, _ = w.Write([]byte(test.get))
			}))
			defer server.Close()
			client := api.New(server.URL, nil)
			defer client.Close()
			baseline := map[string]any{"dns_ttl": float64(45)}
			var err error
			if test.invalid {
				err = rejectConfigurationUpdate(context.Background(), client, "dns", map[string]any{"dns_ttl": -1}, baseline)
			} else {
				_, err = persistedConfiguration(context.Background(), client, "dns", baseline)
			}
			shouldFail := test.name == "invalid update persisted" || test.name == "missing acknowledged field"
			if (err != nil) != shouldFail {
				t.Fatalf("persistence error = %v, should fail = %v", err, shouldFail)
			}
			if !reflect.DeepEqual(baseline, map[string]any{"dns_ttl": float64(45)}) {
				t.Fatal("oracle modified its independent baseline")
			}
		})
	}
}
