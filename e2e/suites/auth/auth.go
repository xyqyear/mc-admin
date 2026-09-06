package auth

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func Cases(recipes fixtures.Recipes) []engine.Case {
	return []engine.Case{
		{ID: "auth.sessions-and-permissions", Suite: "auth", Tags: []string{"smoke"}, Recipe: recipes.Base, Isolation: engine.Fresh, Timeout: time.Minute, Run: sessions},
		{ID: "auth.user-administration", Suite: "auth", Tags: []string{"regression"}, Recipe: recipes.Base, Isolation: engine.Fresh, Timeout: time.Minute, Run: userAdministration},
		{ID: "auth.code-login-and-csrf", Suite: "auth", Tags: []string{"regression"}, Recipe: recipes.Base, Isolation: engine.Fresh, Timeout: time.Minute, Run: codeLogin},
	}
}

func sessions(ctx context.Context, t *engine.Scope) error {
	anonymous, err := fixtures.Session(ctx, t, "")
	if err != nil {
		return err
	}
	if err = t.Step("anonymous requests and invalid login are rejected", func() error {
		if err := anonymous.JSON(ctx, "GET", "/api/user/me", nil, nil, 401); err != nil {
			return err
		}
		response, err := anonymous.Do(ctx, "POST", "/api/auth/token", []byte(url.Values{"username": {"e2e-owner"}, "password": {"invalid-password"}}.Encode()), http.Header{"Content-Type": {"application/x-www-form-urlencoded"}})
		if err != nil {
			return err
		}
		if err = anonymous.Expect(response, 401); err != nil {
			return err
		}
		return anonymous.JSON(ctx, "GET", "/api/user/me", nil, nil, 401)
	}); err != nil {
		return err
	}
	owner, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	admin, err := fixtures.Session(ctx, t, "admin")
	if err != nil {
		return err
	}
	if err = t.Step("real sessions enforce role boundaries", func() error {
		var me struct {
			Username string `json:"username"`
			Role     string `json:"role"`
		}
		if err := owner.JSON(ctx, "GET", "/api/user/me", nil, &me, 200); err != nil {
			return err
		}
		if me.Username != "e2e-owner" || me.Role != "owner" {
			return fmt.Errorf("unexpected owner identity: %+v", me)
		}
		if err := owner.JSON(ctx, "GET", "/api/admin/users", nil, nil, 200); err != nil {
			return err
		}
		return admin.JSON(ctx, "GET", "/api/admin/users", nil, nil, 403)
	}); err != nil {
		return err
	}
	if err = t.Step("missing CSRF rejects writes without creating a user", func() error {
		owner.CSRF = false
		defer func() { owner.CSRF = true }()
		if err := owner.JSON(ctx, "POST", "/api/admin/users", map[string]string{"username": "must-not-exist", "password": "temporary", "role": "admin"}, nil, 403); err != nil {
			return err
		}
		var users []map[string]any
		if err := owner.JSON(ctx, "GET", "/api/admin/users", nil, &users, 200); err != nil {
			return err
		}
		if len(users) != 2 {
			return fmt.Errorf("rejected request changed user inventory")
		}
		return nil
	}); err != nil {
		return err
	}
	return t.Step("logout clears the authenticated session", func() error {
		if err := owner.JSON(ctx, "POST", "/api/auth/logout", nil, nil, 204); err != nil {
			return err
		}
		return owner.JSON(ctx, "GET", "/api/user/me", nil, nil, 401)
	})
}
