package dns

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"
)

type providerConfig struct {
	Domain string `json:"domain"`
	Prefix string `json:"prefix"`
	ID     string `json:"id,omitempty"`
	Key    string `json:"key,omitempty"`
	AK     string `json:"ak,omitempty"`
	SK     string `json:"sk,omitempty"`
	Region string `json:"region,omitempty"`
	TTL    int    `json:"ttl,omitempty"`
}

func loadConfig(path, provider string) (providerConfig, error) {
	var result providerConfig
	if path == "" {
		return result, fmt.Errorf("external DNS qualification requires --external-config PATH containing dns.%s test-domain credentials and an authorized prefix; no cloud request was made", provider)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return result, fmt.Errorf("read external DNS configuration: %w", err)
	}
	var config struct {
		DNS map[string]providerConfig `json:"dns"`
	}
	if err = json.Unmarshal(data, &config); err != nil {
		return result, fmt.Errorf("invalid external configuration JSON: %w", err)
	}
	var ok bool
	result, ok = config.DNS[provider]
	if !ok {
		return result, fmt.Errorf("external configuration missing dns.%s", provider)
	}
	if !regexp.MustCompile(`^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$`).MatchString(result.Domain) {
		return result, fmt.Errorf("dns.%s.domain must be an explicit lower-case test domain without wildcard or trailing dot", provider)
	}
	if !regexp.MustCompile(`^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$`).MatchString(result.Prefix) {
		return result, fmt.Errorf("dns.%s.prefix must be an authorized 3–32 character DNS label", provider)
	}
	if provider == "dnspod" && (result.ID == "" || result.Key == "") {
		return result, fmt.Errorf("dns.dnspod requires Tencent Cloud id and key")
	}
	if provider == "huawei" && (result.AK == "" || result.SK == "") {
		return result, fmt.Errorf("dns.huawei requires ak and sk")
	}
	if result.Region == "" {
		result.Region = "cn-south-1"
	}
	if result.TTL == 0 {
		result.TTL = 600
	}
	if result.TTL < 600 || result.TTL > 86400 {
		return result, fmt.Errorf("external DNS TTL must be between 600 and 86400 seconds")
	}
	return result, nil
}

func (p providerConfig) application(provider string) map[string]any {
	if provider == "dnspod" {
		return map[string]any{"type": provider, "domain": p.Domain, "id": p.ID, "key": p.Key}
	}
	return map[string]any{"type": provider, "domain": p.Domain, "ak": p.AK, "sk": p.SK, "region": p.Region}
}
