package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"slices"
	"strings"
	"testing"

	"mc-admin/e2e/internal/engine"
)

func TestAPIHistoryRejectsInvalidPayloadWithoutHidingCurrentCases(t *testing.T) {
	path := filepath.Join(t.TempDir(), "history.json")
	fallback, _, err := restoredCosts("", "regression", "context")
	if err != nil {
		t.Fatal(err)
	}
	valid := map[string]any{"schema_version": 1, "component": "api", "profile": "regression", "compatibility": "context", "audited": true, "source": map[string]any{"run_id": "123", "sha": strings.Repeat("a", 40)}, "costs": map[string]any{"version": 1, "measurement": "api-lifecycle-v2", "default_seconds": 23, "cases": map[string]any{"unknown.case": 12}, "recipes": map[string]any{}, "shard_overhead_seconds": 2}}
	for _, mutation := range []string{"valid", "negative", "unaudited", "other-profile", "other-context", "other-measurement", "null-source", "invalid-group", "zero-default", "bad-json"} {
		t.Run(mutation, func(t *testing.T) {
			data, _ := json.Marshal(valid)
			var envelope map[string]any
			_ = json.Unmarshal(data, &envelope)
			switch mutation {
			case "negative":
				envelope["costs"].(map[string]any)["cases"] = map[string]any{"unknown.case": -1}
			case "unaudited":
				envelope["audited"] = false
			case "other-profile":
				envelope["profile"] = "qualification"
			case "other-context":
				envelope["compatibility"] = "other"
			case "other-measurement":
				envelope["costs"].(map[string]any)["measurement"] = "assertions-only"
			case "null-source":
				envelope["source"] = nil
			case "invalid-group":
				envelope["costs"].(map[string]any)["groups"] = map[string]any{"recipe:base": map[string]any{"seconds": 0, "members": []string{"unknown.case"}}}
			case "zero-default":
				envelope["costs"].(map[string]any)["default_seconds"] = 0
			}
			data, _ = json.Marshal(envelope)
			if mutation == "bad-json" {
				data = []byte("{")
			}
			if err := os.WriteFile(path, data, 0600); err != nil {
				t.Fatal(err)
			}
			costs, source, err := restoredCosts(path, "regression", "context")
			if err != nil {
				t.Fatal(err)
			}
			if mutation == "valid" {
				if costs.DefaultSeconds != 23 || len(source) == 0 || costs.Cases["unknown.case"] != 12 {
					t.Fatal("compatible audited history was not restored")
				}
			} else if !reflect.DeepEqual(costs, fallback) || len(source) != 0 {
				t.Fatal("invalid history changed fallback or blocked current execution")
			}
		})
	}
}
func TestAPIQualificationPlanRequiresCurrentHuaweiCases(t *testing.T) {
	path := filepath.Join(t.TempDir(), "plan.json")
	if code := ciPlan([]string{"--profile", "qualification", "--revision", strings.Repeat("a", 40), "--backend-image", "sha256:image", "--output", path}); code != 0 {
		t.Fatalf("planning returned %d", code)
	}
	plan, err := loadRunPlan(path)
	if err != nil {
		t.Fatal(err)
	}
	var cloud []string
	for _, entry := range plan.Catalog {
		if entry.Capability == "huawei" {
			cloud = append(cloud, entry.ID)
		}
		if entry.Capability == "dnspod" || slices.Contains(entry.Tags, "mojang") {
			t.Fatal("implicit optional external provider in qualification")
		}
	}
	if !slices.Contains(cloud, "dns.huawei-minecraft-connectivity") || !slices.Contains(cloud, "dns.huawei-reconciliation") {
		t.Fatal("required real Huawei business cases absent")
	}
	if err = plan.Validate(currentCatalog(), "qualification"); err != nil {
		t.Fatal(err)
	}
	if plan.Validate(currentCatalog(), "regression") == nil {
		t.Fatal("protected cloud plan accepted in ordinary PR context")
	}
	ordinaryShard := 0
	for _, shard := range plan.Shards {
		if shard.Capability == "ordinary" {
			ordinaryShard = shard.Index
			break
		}
	}
	if ordinaryShard == 0 {
		t.Fatal("qualification lacks ordinary execution")
	}
	output := t.TempDir()
	if code := mainCode([]string{"run", "--execution-plan", path, "--profile", "qualification", "--revision", "wrong", "--backend-image", "sha256:image", "--shard", fmt.Sprintf("%d/%d", ordinaryShard, len(plan.Shards)), "--output", output, "--run-id", "rejected-source"}); code != 2 {
		t.Fatal("wrong source was not rejected before Docker access")
	}
	if _, err = os.Stat(filepath.Join(output, "rejected-source")); !os.IsNotExist(err) {
		t.Fatal("source rejection created an owned runtime or manifest")
	}
	ordinary, _ := engine.ProfileCases(currentCatalog(), "regression")
	for _, test := range ordinary {
		if test.Capability != "" {
			t.Fatal("ordinary PR contains cloud capability")
		}
	}
}
