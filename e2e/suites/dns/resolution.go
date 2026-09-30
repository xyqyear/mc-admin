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

func dnsQuery(ctx context.Context, endpoint, name string, kind uint16, authoritative bool) (*wire.Msg, error) {
	query := new(wire.Msg).SetQuestion(wire.Fqdn(name), kind)
	query.RecursionDesired = !authoritative
	client := &wire.Client{Net: "tcp", Timeout: 3 * time.Second}
	response, _, err := client.ExchangeContext(ctx, query, endpoint)
	if err != nil {
		return nil, err
	}
	if response.Truncated || response.Rcode != wire.RcodeSuccess || (authoritative && !response.Authoritative) {
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

func authoritativeServers(ctx context.Context, domain string) ([]string, error) {
	nameservers, err := net.DefaultResolver.LookupNS(ctx, domain)
	if err != nil {
		return nil, err
	}
	var addresses []string
	for _, server := range nameservers {
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
		return nil, fmt.Errorf("zone %s has no public delegation", domain)
	}
	return addresses, nil
}

func checkAuthoritative(ctx context.Context, t *engine.Scope, config providerConfig, expected map[string]string) error {
	deadline, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()
	servers, err := authoritativeServers(deadline, config.Domain)
	if err != nil {
		return fmt.Errorf("public zone delegation: %w", err)
	}
	names := make([]string, 0, len(expected))
	for key := range expected {
		names = append(names, key)
	}
	sort.Strings(names)
	return api.Wait(deadline, 2*time.Second, "authoritative DNS publication", func(probe context.Context) (bool, error) {
		for _, server := range servers {
			for _, key := range names {
				parts := strings.SplitN(key, "|", 2)
				host := strings.Replace(parts[0], "*.", fixtures.ServerOf(t.Env).ID+".", 1) + "." + config.Domain
				kind := wire.StringToType[parts[1]]
				answer, err := dnsQuery(probe, server, host, kind, true)
				if err != nil {
					return false, err
				}
				values := answerValues(answer, host, kind)
				if len(values) != 1 || values[0] != expected[key] {
					return false, fmt.Errorf("DNS %s %s returned %v; expected %s", host, parts[1], values, expected[key])
				}
			}
		}
		t.Recorder.Event("authoritative_dns", map[string]any{"nameservers": servers, "records": expected})
		return true, nil
	})
}

func dnsTraffic(ctx context.Context, t *engine.Scope, config providerConfig, host, motd string, expectedPort int) error {
	servers, err := authoritativeServers(ctx, config.Domain)
	if err != nil {
		return err
	}
	srv, err := dnsQuery(ctx, servers[0], "_minecraft._tcp."+host, wire.TypeSRV, true)
	if err != nil {
		return err
	}
	var target *wire.SRV
	for _, answer := range srv.Answer {
		if record, ok := answer.(*wire.SRV); ok && strings.EqualFold(record.Hdr.Name, wire.Fqdn("_minecraft._tcp."+host)) {
			target = record
		}
	}
	if target == nil || int(target.Port) != expectedPort || target.Target != wire.Fqdn(host) {
		return fmt.Errorf("unexpected Minecraft SRV destination")
	}
	address, err := dnsQuery(ctx, servers[0], target.Target, wire.TypeA, true)
	if err != nil {
		return err
	}
	values := answerValues(address, target.Target, wire.TypeA)
	if len(values) != 1 || values[0] != "127.0.0.1" {
		return fmt.Errorf("DNS-derived traffic destination is outside the owned loopback listener: %v", values)
	}
	return assertTraffic(ctx, t, net.JoinHostPort(values[0], fmt.Sprint(target.Port)), host, motd, int(target.Port))
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
