package auth

import (
	"fmt"
	"slices"
	"strings"
	"testing"

	"mc-admin/e2e/internal/evidence"
)

func TestLoginLogExposuresDetectsTruncatedTickets(t *testing.T) {
	const code = "12345678"
	const ticket = "abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJKLMNOP"
	for _, test := range []struct {
		name, content, expected string
	}{
		{"complete code", "Sending code " + code, "code"},
		{"complete ticket", `{"ticket":"` + ticket + `"}`, "ticket"},
		{"ticket prefix", "prefix=" + ticket[:20] + "...", "ticket"},
		{"ticket suffix", "suffix=..." + ticket[len(ticket)-21:], "ticket"},
		{"short credential frame", `DEBUG: > TEXT '{"type":"verified","ticket":"abc...XYZ"}'`, "credential frame"},
	} {
		t.Run(test.name, func(t *testing.T) {
			if !slices.Contains(loginLogExposures(test.content, code, ticket), test.expected) {
				t.Fatalf("missing %s exposure", test.expected)
			}
		})
	}
	if got := loginLogExposures("Login code sent to client\nLogin code expired\nstatus_code=200", code, ticket); len(got) != 0 {
		t.Fatalf("safe lifecycle messages were rejected: %v", got)
	}
}

func TestLoginCredentialFragmentsRedactTruncatedTransportEvidence(t *testing.T) {
	const ticket = "abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJKLMNOP"
	redactor := &evidence.Redactor{}
	redactor.Add(credentialLogValues(ticket)...)
	for _, widths := range [][2]int{{20, 21}, {12, 12}, {15, 17}} {
		line := fmt.Sprintf(`DEBUG: > TEXT '{"type":"verified","ticket":"%s...%s"}'`, ticket[:widths[0]], ticket[len(ticket)-widths[1]:])
		clean := redactor.Text(line)
		if strings.Count(clean, "[REDACTED]") != 2 || strings.Contains(clean, ticket[:12]) || strings.Contains(clean, ticket[len(ticket)-12:]) {
			t.Fatalf("truncated transport credential was not fully redacted for widths %v", widths)
		}
	}
}
