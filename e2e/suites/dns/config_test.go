package dns

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestExternalConfigRequiresExplicitAuthorizationScope(t *testing.T) {
	if _, err := loadConfig("", "dnspod"); err == nil {
		t.Fatal("missing external config was accepted")
	}
	for _, test := range []struct {
		domain, prefix string
		valid          bool
	}{{"test.example.com", "e2e", true}, {"*.example.com", "e2e", false}, {"test.example.com", "", false}, {"test.example.com", "../escape", false}, {"test.example.com", "e2e.scope", false}, {"test.example.com.", "e2e", false}} {
		t.Run(test.domain+"-"+test.prefix, func(t *testing.T) {
			data, err := json.Marshal(map[string]any{"dns": map[string]any{"dnspod": providerConfig{Domain: test.domain, Prefix: test.prefix, ID: "test-id", Key: "test-key"}}})
			if err != nil {
				t.Fatal(err)
			}
			path := filepath.Join(t.TempDir(), "external.json")
			if err = os.WriteFile(path, data, 0600); err != nil {
				t.Fatal(err)
			}
			config, err := loadConfig(path, "dnspod")
			if (err == nil) != test.valid {
				t.Fatalf("valid=%v err=%v", test.valid, err)
			}
			if test.valid && config.TTL != 600 {
				t.Fatalf("unexpected default TTL %d", config.TTL)
			}
			if _, err = loadConfig(path, "huawei"); err == nil {
				t.Fatal("missing provider was accepted")
			}
		})
	}
}
