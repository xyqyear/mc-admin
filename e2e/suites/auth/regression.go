package auth

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"regexp"
	"strings"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

type publicUser struct {
	ID       int    `json:"id"`
	Username string `json:"username"`
	Role     string `json:"role"`
}

func userAdministration(ctx context.Context, t *engine.Scope) error {
	owner, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	admin, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	var me publicUser
	if err = owner.JSON(ctx, "GET", "/api/user/me", nil, &me, 200); err != nil {
		return err
	}
	password := fixtures.BackendOf(t.Env).Password + "-new"
	t.Recorder.Redactor.Add(password)
	input := map[string]any{"username": "e2e-managed", "password": password, "role": "admin"}
	var created publicUser
	if err = t.Step("owner creates a usable account and enforces uniqueness and roles", func() error {
		if err := admin.JSON(ctx, "POST", "/api/admin/users", input, nil, 403); err != nil {
			return err
		}
		if err := owner.JSON(ctx, "POST", "/api/admin/users", input, &created, 200); err != nil {
			return err
		}
		if created.ID <= 0 || created.Username != "e2e-managed" || created.Role != "admin" {
			return fmt.Errorf("unexpected created user: %+v", created)
		}
		if err := owner.JSON(ctx, "POST", "/api/admin/users", input, nil, 400); err != nil {
			return err
		}
		invalid := map[string]any{"username": "invalid-role", "password": password, "role": "root"}
		return owner.JSON(ctx, "POST", "/api/admin/users", invalid, nil, 422)
	}); err != nil {
		return err
	}
	managed, err := fixtures.Session(ctx, t, "")
	if err != nil {
		return err
	}
	if err = managed.Login(ctx, created.Username, password); err != nil {
		return err
	}
	var identity publicUser
	if err = managed.JSON(ctx, "GET", "/api/user/me", nil, &identity, 200); err != nil {
		return err
	}
	if identity.ID != created.ID {
		return fmt.Errorf("new account login returned another user")
	}
	return t.Step("deletion preserves the owner and removes credentials and inventory", func() error {
		path := fmt.Sprintf("/api/admin/users/%d", created.ID)
		if err := admin.JSON(ctx, "DELETE", path, nil, nil, 403); err != nil {
			return err
		}
		if err := owner.JSON(ctx, "DELETE", fmt.Sprintf("/api/admin/users/%d", me.ID), nil, nil, 400); err != nil {
			return err
		}
		if err := owner.JSON(ctx, "DELETE", path, nil, nil, 200); err != nil {
			return err
		}
		if err := owner.JSON(ctx, "DELETE", path, nil, nil, 404); err != nil {
			return err
		}
		var users []publicUser
		if err := owner.JSON(ctx, "GET", "/api/admin/users", nil, &users, 200); err != nil {
			return err
		}
		if len(users) != 2 {
			return fmt.Errorf("expected bootstrap accounts after deletion, got %d", len(users))
		}
		for _, user := range users {
			if user.ID == created.ID {
				return fmt.Errorf("deleted account remains listed")
			}
		}
		response, err := managed.Do(ctx, "POST", "/api/auth/token", []byte(url.Values{"username": {created.Username}, "password": {password}}.Encode()), http.Header{"Content-Type": {"application/x-www-form-urlencoded"}})
		if err != nil {
			return err
		}
		return managed.Expect(response, 401)
	})
}

func codeLogin(ctx context.Context, t *engine.Scope) error {
	browser, err := fixtures.Session(ctx, t, "")
	if err != nil {
		return err
	}
	owner, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	master, err := fixtures.Session(ctx, t, "")
	if err != nil {
		return err
	}
	master.Bearer = fixtures.BackendOf(t.Env).Master
	if err = browser.JSON(ctx, "POST", "/api/auth/code/complete", map[string]string{"ticket": "invalid-ticket"}, nil, 400); err != nil {
		return err
	}
	if err = owner.JSON(ctx, "POST", "/api/auth/verifyCode", map[string]string{"username": "e2e-admin", "code": "12345678"}, nil, 403); err != nil {
		return err
	}
	var ticket, code string
	if err = t.Step("master confirmation exchanges a numeric code for a one-time browser ticket", func() error {
		return browser.WebSocket(ctx, "/api/auth/code", func(event map[string]any) (bool, error) {
			switch event["type"] {
			case "code":
				code, _ = event["code"].(string)
				t.Recorder.Redactor.Add(code)
				if !regexp.MustCompile(`^\d{8}$`).MatchString(code) || event["timeout"] != float64(60) {
					return false, fmt.Errorf("invalid login code envelope")
				}
				if err := master.JSON(ctx, "POST", "/api/auth/verifyCode", map[string]string{"username": "missing-user", "code": code}, nil, 400); err != nil {
					return false, err
				}
				return false, master.JSON(ctx, "POST", "/api/auth/verifyCode", map[string]string{"username": "e2e-admin", "code": code}, nil, 200)
			case "verified":
				ticket, _ = event["ticket"].(string)
				t.Recorder.Redactor.Add(credentialLogValues(ticket)...)
				if ticket == "" {
					return false, fmt.Errorf("verification omitted completion ticket")
				}
				return true, nil
			default:
				return false, fmt.Errorf("unexpected login event type %v", event["type"])
			}
		})
	}); err != nil {
		return err
	}
	if err = master.JSON(ctx, "POST", "/api/auth/verifyCode", map[string]string{"username": "e2e-admin", "code": code}, nil, 400); err != nil {
		return err
	}
	var completed struct {
		User publicUser `json:"user"`
	}
	if err = browser.JSON(ctx, "POST", "/api/auth/code/complete", map[string]string{"ticket": ticket}, &completed, 200); err != nil {
		return err
	}
	if completed.User.Username != "e2e-admin" {
		return fmt.Errorf("ticket completed for wrong identity")
	}
	if err = browser.JSON(ctx, "POST", "/api/auth/code/complete", map[string]string{"ticket": ticket}, nil, 400); err != nil {
		return err
	}
	if err = t.Step("code login establishes session cookies and rejects mismatched CSRF", func() error {
		var me publicUser
		if err := browser.JSON(ctx, "GET", "/api/user/me", nil, &me, 200); err != nil {
			return err
		}
		if me.ID != completed.User.ID {
			return fmt.Errorf("cookie identity differs from completion")
		}
		browser.CSRF = false
		response, err := browser.Do(ctx, "POST", "/api/config/modules/world/reset", nil, http.Header{"X-CSRF-Token": {"incorrect"}})
		browser.CSRF = true
		if err != nil {
			return err
		}
		if err = browser.Expect(response, 403); err != nil {
			return err
		}
		if err = browser.JSON(ctx, "POST", "/api/config/modules/world/reset", nil, nil, 200); err != nil {
			return err
		}
		response, err = browser.Do(ctx, "POST", "/api/auth/logout", nil, nil)
		if err != nil {
			return err
		}
		if err = browser.Expect(response, 204); err != nil {
			return err
		}
		if !strings.Contains(strings.Join(response.Header.Values("Set-Cookie"), ";"), "Max-Age=0") {
			return fmt.Errorf("logout did not expire auth cookies")
		}
		return browser.JSON(ctx, "GET", "/api/user/me", nil, nil, 401)
	}); err != nil {
		return err
	}
	return t.Step("real login codes and completion tickets stay out of application and audit logs", func() error {
		return codeLoginLogs(ctx, t, code, ticket)
	})
}
