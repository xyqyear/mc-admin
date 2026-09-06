package auth

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

var credentialFrame = regexp.MustCompile(`(?:>|<)\s+TEXT\b[^\n]*"(?:code|ticket)"\s*:`)

func credentialLogValues(value string) []string {
	if value == "" {
		return nil
	}
	values := []string{value}
	// Transport debug logs can elide the middle of a credential before evidence redaction.
	for length := 12; length < len(value); length++ {
		values = append(values, value[:length], value[len(value)-length:])
	}
	return values
}

func loginLogExposures(content, code, ticket string) []string {
	exposed := []string{}
	for _, credential := range []struct{ name, value string }{{"code", code}, {"ticket", ticket}} {
		for _, value := range credentialLogValues(credential.value) {
			if strings.Contains(content, value) {
				exposed = append(exposed, credential.name)
				break
			}
		}
	}
	if credentialFrame.MatchString(content) {
		exposed = append(exposed, "credential frame")
	}
	return exposed
}

func codeLoginLogs(ctx context.Context, t *engine.Scope, code, ticket string) error {
	backend := fixtures.BackendOf(t.Env)
	applicationLog, err := backend.Docker.Run(ctx, "logs", backend.Name)
	if err != nil {
		return err
	}
	auditLog, err := os.ReadFile(filepath.Join(t.Env.Dir, "logs", "operations.log"))
	if err != nil {
		return err
	}
	exposed := []string{}
	for _, source := range []struct{ name, content string }{{"application log", applicationLog}, {"audit log", string(auditLog)}} {
		if strings.TrimSpace(source.content) == "" {
			return fmt.Errorf("owned %s is empty", source.name)
		}
		for _, credential := range loginLogExposures(source.content, code, ticket) {
			exposed = append(exposed, source.name+": "+credential)
		}
	}
	if len(exposed) > 0 {
		return fmt.Errorf("login credential values appeared in %s", strings.Join(exposed, "; "))
	}
	seen := map[string]bool{}
	for _, line := range strings.Split(strings.TrimSpace(string(auditLog)), "\n") {
		var entry struct {
			Path   string         `json:"path"`
			Status int            `json:"status_code"`
			Body   map[string]any `json:"request_body"`
		}
		if err = json.Unmarshal([]byte(line), &entry); err != nil {
			return fmt.Errorf("invalid audit record: %w", err)
		}
		if entry.Status != 200 {
			continue
		}
		field := ""
		switch entry.Path {
		case "/api/auth/verifyCode":
			field = "code"
		case "/api/auth/code/complete":
			field = "ticket"
		default:
			continue
		}
		if entry.Body[field] != "***MASKED***" {
			return fmt.Errorf("successful login audit record did not mask its %s field", field)
		}
		seen[field] = true
	}
	if !seen["code"] || !seen["ticket"] {
		return fmt.Errorf("successful verification and completion audit records are required")
	}
	return nil
}
