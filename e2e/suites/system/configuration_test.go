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
		{"invalid update persisted", `{"dns_ttl":90}`, true},
		{"missing acknowledged field", `{}`, false},
		{"valid persistence", `{"dns_ttl":45}`, false},
		{"invalid update rejected", `{"dns_ttl":45}`, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path != "/api/settings/dns" {
					t.Errorf("unexpected request %s", r.URL)
				}
				if r.Method == "PUT" {
					w.WriteHeader(422)
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
