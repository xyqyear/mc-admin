package dns

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestExternalConfigRequiresProviderCredentials(t *testing.T) {
	if _, err := loadConfig("", "dnspod"); err == nil {
		t.Fatal("missing external config was accepted")
	}
	for _, test := range []struct {
		name, provider, data string
	}{
		{"invalid-json", "huawei", "{"},
		{"missing-provider", "huawei", `{"dns":{}}`},
		{"unsupported-provider", "other", `{"dns":{"other":{"domain":"example.com"}}}`},
		{"missing-domain", "huawei", `{"dns":{"huawei":{"ak":"test-ak","sk":"test-sk"}}}`},
		{"missing-huawei-ak", "huawei", `{"dns":{"huawei":{"domain":"example.com","sk":"test-sk"}}}`},
		{"missing-huawei-sk", "huawei", `{"dns":{"huawei":{"domain":"example.com","ak":"test-ak"}}}`},
		{"missing-dnspod-id", "dnspod", `{"dns":{"dnspod":{"domain":"example.com","key":"test-key"}}}`},
		{"missing-dnspod-key", "dnspod", `{"dns":{"dnspod":{"domain":"example.com","id":"test-id"}}}`},
	} {
		t.Run(test.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "external.json")
			if err := os.WriteFile(path, []byte(test.data), 0600); err != nil {
				t.Fatal(err)
			}
			if _, err := loadConfig(path, test.provider); err == nil {
				t.Fatal("incomplete provider configuration was accepted")
			}
		})
	}
}

func TestExternalConfigUsesEnvironmentNamesAndOptionalParent(t *testing.T) {
	for _, test := range []struct {
		name, provider string
		config         providerConfig
		scope          string
		ttl            int
	}{
		{"defaults", "dnspod", providerConfig{Domain: "example.com", ID: "test-id", Key: "test-key"}, "012345abcdef", 600},
		{"custom-parent", "huawei", providerConfig{Domain: "Example.COM.", ManagedSubDomain: "custom_parent.nested", AK: "test-ak", SK: "test-sk", TTL: 60}, "012345abcdef.custom_parent.nested", 60},
	} {
		t.Run(test.name, func(t *testing.T) {
			data, err := json.Marshal(map[string]any{"dns": map[string]any{test.provider: test.config}})
			if err != nil {
				t.Fatal(err)
			}
			path := filepath.Join(t.TempDir(), "external.json")
			if err = os.WriteFile(path, data, 0600); err != nil {
				t.Fatal(err)
			}
			config, err := loadConfig(path, test.provider)
			if err != nil {
				t.Fatal(err)
			}
			if config.Domain != test.config.Domain || config.ManagedSubDomain != test.config.ManagedSubDomain || config.TTL != test.ttl || config.Region != "cn-south-1" {
				t.Fatalf("unexpected provider configuration: %+v", config)
			}
			if actual := config.scope("012345abcdef"); actual != test.scope {
				t.Fatalf("scope=%q expected=%q", actual, test.scope)
			}
			if config.scope("abcdef012345") == test.scope {
				t.Fatal("different environments shared DNS record names")
			}
		})
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
