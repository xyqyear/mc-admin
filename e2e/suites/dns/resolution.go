package dns

import (
	"context"
	"fmt"
	"net"
	"sort"
	"strings"
	"time"

	wire "github.com/miekg/dns"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func dnsQuery(ctx context.Context, endpoint, name string, kind uint16) (*wire.Msg, error) {
	query := new(wire.Msg).SetQuestion(wire.Fqdn(name), kind)
	query.RecursionDesired = false
	client := &wire.Client{Net: "udp", Timeout: 3 * time.Second}
	response, _, err := client.ExchangeContext(ctx, query, endpoint)
	if err != nil {
		return nil, err
	}
	if response.Truncated || response.Rcode != wire.RcodeSuccess || !response.Authoritative {
		return nil, fmt.Errorf("DNS %s type=%s rcode=%s authoritative=%v from %s", name, wire.TypeToString[kind], wire.RcodeToString[response.Rcode], response.Authoritative, endpoint)
	}
	return response, nil
}

func answerValues(response *wire.Msg, name string, kind uint16) []string {
	var values []string
	for _, answer := range response.Answer {
		if !strings.EqualFold(answer.Header().Name, wire.Fqdn(name)) || answer.Header().Rrtype != kind {
			continue
		}
		switch record := answer.(type) {
		case *wire.A:
			values = append(values, record.A.String())
		case *wire.AAAA:
			values = append(values, record.AAAA.String())
		case *wire.CNAME:
			values = append(values, strings.TrimSuffix(record.Target, "."))
		case *wire.SRV:
			values = append(values, fmt.Sprintf("%d %d %d %s", record.Priority, record.Weight, record.Port, strings.TrimSuffix(record.Target, ".")))
		}
	}
	sort.Strings(values)
	return values
}

func selectAuthorities(provider string, nameservers []*net.NS) []*net.NS {
	if provider != "huawei" {
		return nameservers
	}
	var overseas []*net.NS
	for _, server := range nameservers {
		switch strings.ToLower(strings.TrimSuffix(server.Host, ".")) {
		case "ns1.huaweicloud-dns.net", "ns1.huaweicloud-dns.org":
			overseas = append(overseas, server)
		}
	}
	return overseas
}

func authoritativeServers(ctx context.Context, config providerConfig) ([]string, error) {
	nameservers, err := net.DefaultResolver.LookupNS(ctx, config.Domain)
	if err != nil {
		return nil, err
	}
	var addresses []string
	for _, server := range selectAuthorities(config.provider, nameservers) {
		ips, err := net.DefaultResolver.LookupIP(ctx, "ip4", server.Host)
		if err != nil {
			return nil, err
		}
		if len(ips) == 0 {
			return nil, fmt.Errorf("nameserver %s has no IPv4 address", server.Host)
		}
		addresses = append(addresses, net.JoinHostPort(ips[0].String(), "53"))
	}
	if len(addresses) == 0 {
		return nil, fmt.Errorf("zone %s has no selected public authority for %s", config.Domain, config.provider)
	}
	return addresses, nil
}

func waitDNSValues(ctx context.Context, endpoint, name string, kind uint16, validate func([]string) error) ([]string, error) {
	var values []string
	description := fmt.Sprintf("authoritative DNS %s %s at %s", name, wire.TypeToString[kind], endpoint)
	err := api.Wait(ctx, 2*time.Second, description, func(probe context.Context) (bool, error) {
		answer, err := dnsQuery(probe, endpoint, name, kind)
		if err != nil {
			return false, err
		}
		observed := answerValues(answer, name, kind)
		if err = validate(observed); err != nil {
			return false, err
		}
		values = observed
		return true, nil
	})
	return values, err
}

func checkAuthoritative(ctx context.Context, t *engine.Scope, config providerConfig, expected map[string]string) error {
	deadline, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()
	servers, err := authoritativeServers(deadline, config)
	if err != nil {
		return fmt.Errorf("public zone delegation: %w", err)
	}
	names := make([]string, 0, len(expected))
	for key := range expected {
		names = append(names, key)
	}
	sort.Strings(names)
	for _, server := range servers {
		for _, key := range names {
			parts := strings.SplitN(key, "|", 2)
			host := strings.Replace(parts[0], "*.", fixtures.ServerOf(t.Env).ID+".", 1) + "." + config.Domain
			kind := wire.StringToType[parts[1]]
			_, err := waitDNSValues(deadline, server, host, kind, func(values []string) error {
				if len(values) != 1 || values[0] != expected[key] {
					return fmt.Errorf("returned %v; expected %s", values, expected[key])
				}
				return nil
			})
			if err != nil {
				return err
			}
		}
	}
	t.Recorder.Event("authoritative_dns", map[string]any{"nameservers": servers, "transport": "udp", "records": expected})
	return nil
}

func dnsTraffic(ctx context.Context, t *engine.Scope, config providerConfig, host, motd string, expectedPort int) error {
	servers, err := authoritativeServers(ctx, config)
	if err != nil {
		return err
	}
	address, err := trafficDestination(ctx, servers[0], host, expectedPort)
	if err != nil {
		return err
	}
	return assertTraffic(ctx, t, address, host, motd, expectedPort)
}

func trafficDestination(ctx context.Context, endpoint, host string, expectedPort int) (string, error) {
	deadline, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()
	values, err := waitDNSValues(deadline, endpoint, "_minecraft._tcp."+host, wire.TypeSRV, func(values []string) error {
		expected := fmt.Sprintf("0 5 %d %s", expectedPort, strings.TrimSuffix(host, "."))
		if len(values) != 1 || values[0] != expected {
			return fmt.Errorf("returned %v; expected %s", values, expected)
		}
		return nil
	})
	if err != nil {
		return "", err
	}
	fields := strings.Fields(values[0])
	ips, err := waitDNSValues(deadline, endpoint, fields[3], wire.TypeA, func(ips []string) error {
		if len(ips) == 0 {
			return fmt.Errorf("returned no A record")
		}
		if len(ips) != 1 || ips[0] != "127.0.0.1" {
			return api.Permanent(fmt.Errorf("DNS-derived traffic destination is outside the owned loopback listener: %v", ips))
		}
		return nil
	})
	if err != nil {
		return "", err
	}
	return net.JoinHostPort(ips[0], fields[2]), nil
}

func checkRecursive(ctx context.Context, t *engine.Scope, host string, port int) error {
	deadline, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()
	return api.Wait(deadline, 2*time.Second, "recursive Minecraft SRV publication", func(probe context.Context) (bool, error) {
		_, records, err := net.DefaultResolver.LookupSRV(probe, "minecraft", "tcp", host)
		if err != nil {
			return false, err
		}
		if len(records) != 1 || records[0].Target != wire.Fqdn(host) || int(records[0].Port) != port {
			return false, fmt.Errorf("recursive SRV destination has not converged")
		}
		t.Recorder.Event("recursive_dns", map[string]any{"hostname": host, "target": records[0].Target, "port": records[0].Port})
		return true, nil
	})
}
