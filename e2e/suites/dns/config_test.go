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

func TestExternalScopeStaysBelowAuthorizedParent(t *testing.T) {
	config := providerConfig{Domain: "example.com", Prefix: "run", ManagedSubDomain: "e2e-test-mc", AK: "test-ak", SK: "test-sk"}
	if actual := config.scope("012345abcdef"); actual != "run-012345abcdef.e2e-test-mc" {
		t.Fatal(actual)
	}
	for _, parent := range []string{"e2e-test-mc", "nested.e2e-test-mc", "*.e2e-test-mc", "e2e-test-mc.", "../escape"} {
		config.ManagedSubDomain = parent
		data, _ := json.Marshal(map[string]any{"dns": map[string]any{"huawei": config}})
		path := filepath.Join(t.TempDir(), "config.json")
		if err := os.WriteFile(path, data, 0600); err != nil {
			t.Fatal(err)
		}
		_, err := loadConfig(path, "huawei")
		valid := parent == "e2e-test-mc" || parent == "nested.e2e-test-mc"
		if (err == nil) != valid {
			t.Fatalf("parent=%q err=%v", parent, err)
		}
	}
}

func TestUnknownCloudStateCannotLookConverged(t *testing.T) {
	for _, body := range []string{
		`{"initialized":true,"dns_diff":null,"router_diff":null}`,
		`{"initialized":true,"state":"degraded","dns_known":false,"router_known":true,"dns_diff":null,"router_diff":{}}`,
		`{"initialized":true,"state":"empty","dns_known":true,"router_known":true,"empty_desired":true}`,
		`{"initialized":true,"state":"ready","dns_known":true,"router_known":true,"issues":["failed"]}`,
	} {
		var observed status
		if err := json.Unmarshal([]byte(body), &observed); err != nil {
			t.Fatal(err)
		}
		if observed.clean() {
			t.Fatalf("unknown state passed: %s", body)
		}
	}
	var ready status
	if err := json.Unmarshal([]byte(`{"initialized":true,"state":"ready","dns_known":true,"router_known":true,"dns_diff":{},"router_diff":{}}`), &ready); err != nil {
		t.Fatal(err)
	}
	if !ready.clean() {
		t.Fatal("ready state rejected")
	}
}
