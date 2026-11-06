package dns

import (
	"context"
	"errors"
	"net"
	"slices"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	wire "github.com/miekg/dns"
)

func TestDNSProbeRejectsNonAuthoritativeAndNegativeResponses(t *testing.T) {
	for _, mode := range []string{"authoritative", "recursive", "nxdomain", "servfail", "truncated"} {
		t.Run(mode, func(t *testing.T) {
			endpoint := startAuthority(t, func(w wire.ResponseWriter, q *wire.Msg) {
				response := new(wire.Msg).SetReply(q)
				response.Authoritative = mode != "recursive"
				response.Truncated = mode == "truncated"
				if mode == "nxdomain" {
					response.Rcode = wire.RcodeNameError
				}
				if mode == "servfail" {
					response.Rcode = wire.RcodeServerFailure
				}
				if q.RecursionDesired {
					response.Rcode = wire.RcodeRefused
				}
				response.Answer = []wire.RR{&wire.A{Hdr: wire.RR_Header{Name: q.Question[0].Name, Rrtype: wire.TypeA, Class: wire.ClassINET, Ttl: 600}, A: net.ParseIP("192.0.2.1")}}
				_ = w.WriteMsg(response)
			})
			ctx, cancel := context.WithTimeout(context.Background(), time.Second)
			defer cancel()
			answer, err := dnsQuery(ctx, endpoint, "game.e2e.invalid", wire.TypeA)
			if mode != "authoritative" {
				if err == nil {
					t.Fatal("unsafe DNS answer accepted")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			values := answerValues(answer, "game.e2e.invalid", wire.TypeA)
			if len(values) != 1 || values[0] != "192.0.2.1" {
				t.Fatal(values)
			}
			if len(answerValues(answer, "unrelated.e2e.invalid", wire.TypeA)) != 0 {
				t.Fatal("unrelated answer accepted")
			}
		})
	}
}

func TestTrafficDNSWaitsForSelectedAuthority(t *testing.T) {
	for _, mode := range []string{"converges", "retry-address", "negative-address", "empty-address", "stale", "wrong-host", "duplicate", "external-address"} {
		t.Run(mode, func(t *testing.T) {
			var srvQueries, addressQueries atomic.Int32
			endpoint := startAuthority(t, func(w wire.ResponseWriter, q *wire.Msg) {
				response := new(wire.Msg).SetReply(q)
				response.Authoritative = true
				question := q.Question[0]
				if question.Qtype == wire.TypeSRV {
					count := srvQueries.Add(1)
					record := &wire.SRV{Hdr: wire.RR_Header{Name: question.Name, Rrtype: wire.TypeSRV, Class: wire.ClassINET, Ttl: 600}, Weight: 5, Port: 25566, Target: "game.e2e.invalid."}
					if mode == "stale" || (mode == "converges" && count == 1) {
						record.Port = 25565
					}
					if mode == "wrong-host" {
						record.Target = "other.e2e.invalid."
					}
					response.Answer = []wire.RR{record}
					if mode == "duplicate" {
						response.Answer = append(response.Answer, wire.Copy(record))
					}
				} else {
					count := addressQueries.Add(1)
					if mode == "retry-address" && count == 1 {
						return
					}
					if mode == "negative-address" && count == 1 {
						response.Rcode = wire.RcodeNameError
					}
					ip := "127.0.0.1"
					if mode == "external-address" {
						ip = "192.0.2.1"
					}
					response.Answer = []wire.RR{&wire.A{Hdr: wire.RR_Header{Name: question.Name, Rrtype: wire.TypeA, Class: wire.ClassINET, Ttl: 600}, A: net.ParseIP(ip)}}
					if mode == "empty-address" && count == 1 {
						response.Answer = nil
					}
				}
				_ = w.WriteMsg(response)
			})
			budget := 200 * time.Millisecond
			if mode == "converges" {
				budget = 5 * time.Second
			}
			if mode == "retry-address" || mode == "negative-address" || mode == "empty-address" {
				budget = 10 * time.Second
			}
			ctx, cancel := context.WithTimeout(context.Background(), budget)
			defer cancel()
			address, err := trafficDestination(ctx, endpoint, "game.e2e.invalid", 25566)
			if mode == "converges" {
				if err != nil || address != "127.0.0.1:25566" || srvQueries.Load() < 2 || addressQueries.Load() != 1 {
					t.Fatalf("convergence: address=%q error=%v SRV=%d A=%d", address, err, srvQueries.Load(), addressQueries.Load())
				}
				return
			}
			if mode == "retry-address" || mode == "negative-address" || mode == "empty-address" {
				if err != nil || address != "127.0.0.1:25566" || srvQueries.Load() != 1 || addressQueries.Load() != 2 {
					t.Fatalf("address retry: address=%q error=%v SRV=%d A=%d", address, err, srvQueries.Load(), addressQueries.Load())
				}
				return
			}
			if err == nil || address != "" {
				t.Fatalf("unsafe destination accepted: address=%q error=%v", address, err)
			}
			if mode == "external-address" {
				if !strings.Contains(err.Error(), "outside the owned loopback") || srvQueries.Load() != 1 {
					t.Fatalf("external destination did not fail immediately: %v", err)
				}
			} else if addressQueries.Load() != 0 || !strings.Contains(err.Error(), "expected 0 5 25566") {
				t.Fatalf("invalid SRV was used for address resolution: %v", err)
			}
		})
	}
}

func TestAuthoritySelection(t *testing.T) {
	for _, test := range []struct {
		name, provider string
		hosts, want    []string
	}{
		{"huawei-overseas", "huawei", []string{"ns1.huaweicloud-dns.com.", "ns1.huaweicloud-dns.net.", "ns1.huaweicloud-dns.cn.", "ns1.huaweicloud-dns.org."}, []string{"ns1.huaweicloud-dns.net.", "ns1.huaweicloud-dns.org."}},
		{"case-and-dot", "huawei", []string{"NS1.HUAWEICLOUD-DNS.NET", "NS1.HUAWEICLOUD-DNS.ORG."}, []string{"NS1.HUAWEICLOUD-DNS.NET", "NS1.HUAWEICLOUD-DNS.ORG."}},
		{"mainland-only", "huawei", []string{"ns1.huaweicloud-dns.com.", "ns1.huaweicloud-dns.cn."}, nil},
		{"unrelated-authorities", "huawei", []string{"ns1.huaweicloud-dns.net.example.com.", "ns1.example.com."}, nil},
		{"dnspod", "dnspod", []string{"ns1.example.com.", "ns2.example.com."}, []string{"ns1.example.com.", "ns2.example.com."}},
	} {
		t.Run(test.name, func(t *testing.T) {
			var servers []*net.NS
			for _, host := range test.hosts {
				servers = append(servers, &net.NS{Host: host})
			}
			var selected []string
			for _, server := range selectAuthorities(test.provider, servers) {
				selected = append(selected, server.Host)
			}
			if !slices.Equal(selected, test.want) {
				t.Fatalf("authorities=%v expected=%v", selected, test.want)
			}
		})
	}
}

func TestDNSRetryHonorsCancellationAndDeadline(t *testing.T) {
	for _, mode := range []string{"canceled", "deadline"} {
		t.Run(mode, func(t *testing.T) {
			var queries atomic.Int32
			endpoint := startAuthority(t, func(w wire.ResponseWriter, q *wire.Msg) {
				queries.Add(1)
			})
			ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
			defer cancel()
			want := context.DeadlineExceeded
			if mode == "canceled" {
				cancel()
				want = context.Canceled
			}
			started := time.Now()
			_, err := waitDNSValues(ctx, endpoint, "game.e2e.invalid", wire.TypeA, func([]string) error {
				t.Error("missing response was accepted")
				return nil
			})
			if !errors.Is(err, want) || time.Since(started) >= time.Second {
				t.Fatalf("query exceeded its context: %v", err)
			}
			if mode == "canceled" && queries.Load() != 0 {
				t.Fatal("canceled lookup issued a DNS query")
			}
		})
	}
}

func startAuthority(t *testing.T, handler wire.HandlerFunc) string {
	t.Helper()
	connection, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = connection.Close() })
	started := make(chan struct{})
	stopped := make(chan error, 1)
	server := &wire.Server{PacketConn: connection, Handler: handler, NotifyStartedFunc: func() { close(started) }}
	go func() { stopped <- server.ActivateAndServe() }()
	select {
	case <-started:
	case err := <-stopped:
		t.Fatalf("start UDP authority: %v", err)
	}
	t.Cleanup(func() {
		if err := server.Shutdown(); err != nil {
			t.Error(err)
		}
		if err := <-stopped; err != nil {
			t.Error(err)
		}
	})
	return connection.LocalAddr().String()
}
