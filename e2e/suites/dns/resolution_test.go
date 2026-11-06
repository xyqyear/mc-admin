package dns

import (
	"context"
	"errors"
	"net"
	"strings"
	"sync/atomic"
	"testing"
	"testing/synctest"
	"time"

	wire "github.com/miekg/dns"

	"mc-admin/e2e/internal/api"
)

func TestCloudDNSDelaysInitialQueryAndRetainsPolling(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		started := time.Now()
		var attempts []time.Duration
		err := checkAfterDNSPropagation(t.Context(), func(ctx context.Context) error {
			deadline, ok := ctx.Deadline()
			if !ok || deadline.Sub(time.Now()) != 2*time.Minute {
				t.Fatal("propagation delay consumed the publication polling budget")
			}
			return api.Wait(ctx, 2*time.Second, "authoritative publication", func(context.Context) (bool, error) {
				attempts = append(attempts, time.Since(started))
				if len(attempts) < 3 {
					return false, errors.New("NXDOMAIN")
				}
				return true, nil
			})
		})
		if err != nil || len(attempts) != 3 || attempts[0] != 30*time.Second || attempts[2] != 34*time.Second {
			t.Fatalf("publication attempts=%v error=%v", attempts, err)
		}
	})
}

func TestCloudDNSInitialDelayHonorsCancellation(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		ctx, cancel := context.WithCancel(t.Context())
		go func() { time.Sleep(5 * time.Second); cancel() }()
		started := time.Now()
		called := false
		err := checkAfterDNSPropagation(ctx, func(context.Context) error { called = true; return nil })
		if !errors.Is(err, context.Canceled) || called || time.Since(started) != 5*time.Second {
			t.Fatalf("cancelled publication: called=%v elapsed=%s error=%v", called, time.Since(started), err)
		}
	})
}

func TestCloudDNSPublicationStillFailsAfterFullPollingBudget(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		started := time.Now()
		err := checkAfterDNSPropagation(t.Context(), func(ctx context.Context) error {
			return api.Wait(ctx, 2*time.Second, "authoritative publication", func(context.Context) (bool, error) {
				return false, errors.New("NXDOMAIN")
			})
		})
		if !errors.Is(err, context.DeadlineExceeded) || time.Since(started) != 150*time.Second {
			t.Fatalf("publication deadline: elapsed=%s error=%v", time.Since(started), err)
		}
	})
}

func TestDNSProbeRejectsNonAuthoritativeAndNegativeResponses(t *testing.T) {
	for _, mode := range []string{"authoritative", "recursive", "nxdomain", "servfail", "truncated"} {
		t.Run(mode, func(t *testing.T) {
			listener, err := net.Listen("tcp", "127.0.0.1:0")
			if err != nil {
				t.Fatal(err)
			}
			started := make(chan struct{})
			server := &wire.Server{Listener: listener, NotifyStartedFunc: func() { close(started) }, Handler: wire.HandlerFunc(func(w wire.ResponseWriter, q *wire.Msg) {
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
			})}
			go func() { _ = server.ActivateAndServe() }()
			<-started
			t.Cleanup(func() { _ = server.Shutdown() })
			ctx, cancel := context.WithTimeout(context.Background(), time.Second)
			defer cancel()
			answer, err := dnsQuery(ctx, listener.Addr().String(), "game.e2e.invalid", wire.TypeA, true)
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
	for _, mode := range []string{"converges", "stale", "wrong-host", "duplicate", "external-address"} {
		t.Run(mode, func(t *testing.T) {
			listener, err := net.Listen("tcp", "127.0.0.1:0")
			if err != nil {
				t.Fatal(err)
			}
			var srvQueries, addressQueries atomic.Int32
			started := make(chan struct{})
			server := &wire.Server{Listener: listener, NotifyStartedFunc: func() { close(started) }, Handler: wire.HandlerFunc(func(w wire.ResponseWriter, q *wire.Msg) {
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
					addressQueries.Add(1)
					ip := "127.0.0.1"
					if mode == "external-address" {
						ip = "192.0.2.1"
					}
					response.Answer = []wire.RR{&wire.A{Hdr: wire.RR_Header{Name: question.Name, Rrtype: wire.TypeA, Class: wire.ClassINET, Ttl: 600}, A: net.ParseIP(ip)}}
				}
				_ = w.WriteMsg(response)
			})}
			go func() { _ = server.ActivateAndServe() }()
			<-started
			t.Cleanup(func() { _ = server.Shutdown() })
			budget := 200 * time.Millisecond
			if mode == "converges" {
				budget = 5 * time.Second
			}
			ctx, cancel := context.WithTimeout(context.Background(), budget)
			defer cancel()
			address, err := trafficDestination(ctx, listener.Addr().String(), "game.e2e.invalid", 25566)
			if mode == "converges" {
				if err != nil || address != "127.0.0.1:25566" || srvQueries.Load() < 2 || addressQueries.Load() != 1 {
					t.Fatalf("convergence: address=%q error=%v SRV=%d A=%d", address, err, srvQueries.Load(), addressQueries.Load())
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
