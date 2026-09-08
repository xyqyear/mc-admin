package evidence

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRedactionCoversNestedFieldsAndEmbeddedSecrets(t *testing.T) {
	path := filepath.Join(t.TempDir(), "trace.jsonl")
	redactor := &Redactor{}
	escapedSecret := "secret-with-\"quotes\\and\nnewline"
	redactor.Add("random-known-secret", escapedSecret)
	recorder, err := Open(path, redactor)
	if err != nil {
		t.Fatal(err)
	}
	recorder.Event("request", map[string]any{"password": "unknown-sensitive-value", "nested": map[string]any{"X-CSRF-Token": "csrf-secret", "access_key": "cloud-key", "code": "one-time-code", "sk": "cloud-secret", "ak": "cloud-access"}, "yaml": "RCON_PASSWORD=random-known-secret", "escaped": "prefix " + escapedSecret + " suffix", "safe": "keep"})
	if err = recorder.Close(); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	for _, secret := range []string{"unknown-sensitive-value", "csrf-secret", "random-known-secret", "cloud-key", "secret-with-", "one-time-code", "cloud-secret", "cloud-access"} {
		if strings.Contains(string(data), secret) {
			t.Fatalf("leaked %s", secret)
		}
	}
	if !json.Valid(data) || !strings.Contains(string(data), "keep") {
		t.Fatal("redaction broke diagnostic JSON")
	}
}
