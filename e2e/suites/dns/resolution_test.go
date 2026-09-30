package dns

import (
	"context"
	"net"
	"testing"
	"time"

	wire "github.com/miekg/dns"
)

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
