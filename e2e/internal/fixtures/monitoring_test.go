package fixtures

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"mc-admin/e2e/internal/api"
)

func TestWaitStatusRejectsHealthySampleFromBeforeRestart(t *testing.T) {
	var reads atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/monitoring" {
			t.Errorf("unexpected path %s", r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
			return
		}
		status, sampled := "HEALTHY", time.Now().UTC()
		switch reads.Add(1) {
		case 1:
			sampled = sampled.Add(-time.Minute)
		case 2:
			status = "STARTING"
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(MonitoringSnapshot{Servers: map[string]ServerSamples{
			"alpha": {Status: Sample[string]{Value: &status, Quality: "ready", SampledAt: &sampled}},
		}})
	}))
	defer server.Close()
	client := api.New(server.URL, nil)
	defer client.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := WaitStatus(ctx, client, "alpha", "healthy"); err != nil {
		t.Fatal(err)
	}
	if reads.Load() != 3 {
		t.Fatalf("accepted stale readiness before new server became healthy: %d reads", reads.Load())
	}
}
