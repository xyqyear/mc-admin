package dns

import (
	"encoding/json"
	"fmt"
	"os"
)

type providerConfig struct {
	Domain           string `json:"domain"`
	ID               string `json:"id,omitempty"`
	Key              string `json:"key,omitempty"`
	AK               string `json:"ak,omitempty"`
	SK               string `json:"sk,omitempty"`
	Region           string `json:"region,omitempty"`
	TTL              int    `json:"ttl,omitempty"`
	ManagedSubDomain string `json:"managed_sub_domain,omitempty"`
}

func loadConfig(path, provider string) (providerConfig, error) {
	var result providerConfig
	if path == "" {
		return result, fmt.Errorf("external DNS tests require --external-config PATH containing dns.%s credentials", provider)
	}
	if provider != "dnspod" && provider != "huawei" {
		return result, fmt.Errorf("unsupported DNS provider %q", provider)
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
	if result.Domain == "" {
		return result, fmt.Errorf("dns.%s requires domain", provider)
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
	return result, nil
}

func (p providerConfig) scope(environmentID string) string {
	scope := environmentID
	if p.ManagedSubDomain != "" {
		scope += "." + p.ManagedSubDomain
	}
	return scope
}

func (p providerConfig) application(provider string) map[string]any {
	if provider == "dnspod" {
		return map[string]any{"type": provider, "domain": p.Domain, "id": p.ID, "key": p.Key}
	}
	return map[string]any{"type": provider, "domain": p.Domain, "ak": p.AK, "sk": p.SK, "region": p.Region}
}
