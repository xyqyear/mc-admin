package coverage

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"mc-admin/e2e/internal/engine"
)

const schemaFixture = `{"openapi":"3.1.0","paths":{"/api/items/{item_id}":{"get":{"operationId":"read_item"}},"/api/items/special":{"get":{"operationId":"special"}},"/api/items":{"post":{"operationId":"create_item"}},"/api/no-traffic":{"get":{}}}}`

func TestParameterWithLiteralSuffixMatchesMapTiles(t *testing.T) {
	m := newMatcher([]*Operation{newOperation("GET", "/api/servers/{server_id}/map/tiles/{x}/{z}.png", "tile")})
	for _, path := range []string{"/api/servers/example/map/tiles/0/0.png", "/api/servers/example/map/tiles/-1/2.png"} {
		if m.match("GET", path) == nil {
			t.Fatalf("missing parameter suffix match: %s", path)
		}
	}
	for _, path := range []string{"/api/servers/example/map/tiles/0/.png", "/api/servers/example/map/tiles/0/1Xpng", "/api/servers/example/map/tiles/0/1.png/extra"} {
		if m.match("GET", path) != nil {
			t.Fatalf("invalid parameter suffix accepted: %s", path)
		}
	}
}

func TestMountedAPISchemaUsesServerPath(t *testing.T) {
	operations, err := schemaOperations([]byte(`{"servers":[{"url":"/api"}],"paths":{"/system/health":{"get":{"operationId":"health"}}}}`))
	if err != nil {
		t.Fatal(err)
	}
	matcher := newMatcher(operations)
	if op := matcher.match("GET", "/api/system/health"); op == nil || op.OperationID != "health" {
		t.Fatal("mounted API path missing")
	}
	if matcher.match("GET", "/system/health") != nil || matcher.match("WS", "/api/events") == nil {
		t.Fatal("schema prefix must apply only to relative HTTP operations")
	}
}

func TestEarlierLiteralSegmentWinsOverParameterNameLength(t *testing.T) {
	operations, err := schemaOperations([]byte(`{"paths":{"/api/players/uuid/{uuid}":{"get":{"operationId":"player_uuid"}},"/api/players/{player_db_id}/sessions":{"get":{"operationId":"player_sessions"}}}}`))
	if err != nil {
		t.Fatal(err)
	}
	matcher := newMatcher(operations)
	if op := matcher.match("GET", "/api/players/uuid/sessions"); op == nil || op.OperationID != "player_uuid" {
		t.Fatal("earlier literal segment shadowed by parameter name length")
	}
	if op := matcher.match("GET", "/api/players/123/sessions"); op == nil || op.OperationID != "player_sessions" {
		t.Fatal("ordinary session request did not match")
	}
}

func trace(kind, method, path string, status int) string {
	data, _ := json.Marshal(map[string]any{"kind": kind, "data": map[string]any{"method": method, "path": path, "status": status}})
	return string(data) + "\n"
}

func runFixture(t *testing.T, root, name string, report engine.Report, schema string, traces map[string]string) string {
	t.Helper()
	dir := filepath.Join(root, name)
	for _, path := range []string{"cases", "environments/env"} {
		if err := os.MkdirAll(filepath.Join(dir, path), 0700); err != nil {
			t.Fatal(err)
		}
	}
	data, err := json.Marshal(report)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(dir, "results.json"), data, 0600); err != nil {
		t.Fatal(err)
	}
	if schema != "" {
		if err = os.WriteFile(filepath.Join(dir, "environments/env/openapi.json"), []byte(schema), 0600); err != nil {
			t.Fatal(err)
		}
	}
	for id, content := range traces {
		if err = os.WriteFile(filepath.Join(dir, "cases", id+".jsonl"), []byte(content), 0600); err != nil {
			t.Fatal(err)
		}
	}
	return dir
}

func singleReport(ids ...string) engine.Report {
	report := engine.Report{RunID: "one", Image: "sha256:application", Plan: engine.Plan{ShardIndex: 1, ShardCount: 1}}
	for _, id := range ids {
		report.Plan.Catalog = append(report.Plan.Catalog, engine.Entry{ID: id, Shard: 1})
		report.Plan.Order = append(report.Plan.Order, id)
		report.Results = append(report.Results, engine.Result{ID: id, Status: "passed"})
	}
	return report
}

func findOperation(t *testing.T, summary Summary, method, path string) Operation {
	t.Helper()
	for _, operation := range summary.Operations {
		if operation.Method == method && operation.Path == path {
			return operation
		}
	}
	t.Fatalf("operation not found: %s %s", method, path)
	return Operation{}
}

func TestPassedResponseCategoriesTemplateMatchingAndFixtureExclusion(t *testing.T) {
	root := t.TempDir()
	report := singleReport("case.passed", "case.failed")
	report.Results[1].Status = "failed"
	passed := trace("http", "GET", "/api/items/special?token=private", 200) + trace("http", "GET", "/api/items/a", 401) + trace("http", "GET", "/api/items/b", 302) + trace("sse_open", "POST", "/api/items", 200) + trace("websocket_open", "", "/api/events", 101) + trace("http", "GET", "/api/not-documented", 404) + `{"kind":"custom","data":[1,2,3]}` + "\n"
	dir := runFixture(t, root, "one", report, schemaFixture, map[string]string{"case.passed": passed, "case.failed": trace("http", "GET", "/api/items/failure", 200)})
	if err := os.WriteFile(filepath.Join(dir, "environments/env/trace.jsonl"), []byte(trace("http", "GET", "/api/no-traffic", 200)), 0600); err != nil {
		t.Fatal(err)
	}
	summary, err := Write([]string{dir}, filepath.Join(root, "out"))
	if err != nil {
		t.Fatal(err)
	}
	if !summary.CasesComplete || summary.AllCasesPassed || summary.PassedCases != 1 || !summary.ShardsComplete {
		t.Fatalf("incorrect case completeness: %+v", summary)
	}
	if summary.OperationCount != 7 || summary.SuccessfulOperations != 3 || summary.RejectedOnlyOperations != 1 || summary.UnobservedOperations != 3 {
		t.Fatalf("incorrect operation counts: %+v", summary)
	}
	dynamic := findOperation(t, summary, "GET", "/api/items/{item_id}")
	if len(dynamic.SuccessfulCases) != 0 || len(dynamic.RejectedCases) != 1 || len(dynamic.OtherResponseCases) != 1 || len(dynamic.FailedCases) != 1 {
		t.Fatalf("incorrect classifications: %+v", dynamic)
	}
	if len(findOperation(t, summary, "GET", "/api/items/special").SuccessfulCases) != 1 {
		t.Fatal("literal route shadowed by template")
	}
	if len(findOperation(t, summary, "GET", "/api/no-traffic").SuccessfulCases) != 0 {
		t.Fatal("fixture trace counted as case coverage")
	}
	if len(summary.Unmatched) != 1 || strings.Contains(summary.Unmatched[0].Path, "?") {
		t.Fatal("unmatched path contains query")
	}
	for _, file := range []string{"coverage.json", "coverage.md"} {
		if _, err := os.Stat(filepath.Join(root, "out", file)); err != nil {
			t.Fatal(err)
		}
	}
}

func TestShardUnionAndMissingCases(t *testing.T) {
	root := t.TempDir()
	catalog := []engine.Entry{{ID: "case.first", Shard: 1}, {ID: "case.second", Shard: 2}}
	first := engine.Report{RunID: "first", Image: "image", Plan: engine.Plan{ShardIndex: 1, ShardCount: 2, Catalog: catalog, Order: []string{"case.first"}}, Results: []engine.Result{{ID: "case.first", Status: "passed"}}}
	second := engine.Report{RunID: "second", Image: "image", Plan: engine.Plan{ShardIndex: 2, ShardCount: 2, Catalog: catalog, Order: []string{"case.second"}}, Results: []engine.Result{{ID: "case.second", Status: "passed"}}}
	a := runFixture(t, root, "first", first, schemaFixture, map[string]string{"case.first": trace("http", "GET", "/api/items/a", 200)})
	b := runFixture(t, root, "second", second, "", map[string]string{"case.second": trace("http", "POST", "/api/items", 201)})
	partial, err := Write([]string{a}, filepath.Join(root, "partial"))
	if err != nil {
		t.Fatal(err)
	}
	if partial.CasesComplete || partial.ShardsComplete || len(partial.MissingCaseIDs) != 1 || partial.MissingCaseIDs[0] != "case.second" || len(partial.MissingShardIndexes) != 1 {
		t.Fatalf("partial report claims completeness: %+v", partial)
	}
	combined, err := Write([]string{a, b}, filepath.Join(root, "combined"))
	if err != nil {
		t.Fatal(err)
	}
	if !combined.CasesComplete || !combined.ShardsComplete || !combined.AllCasesPassed || combined.RecordedCases != 2 {
		t.Fatalf("union incomplete: %+v", combined)
	}
	if combined.SuccessfulOperations != 2 {
		t.Fatalf("union operation count=%d", combined.SuccessfulOperations)
	}
}

func TestRejectIncompatibleAndDuplicateInputs(t *testing.T) {
	for _, kind := range []string{"image", "schema", "catalog", "shard-count", "duplicate-shard", "duplicate-case", "duplicate-run", "unplanned", "missing-schema", "missing-passed-trace"} {
		t.Run(kind, func(t *testing.T) {
			root := t.TempDir()
			first := singleReport("case.first", "case.second")
			first.Plan.ShardCount = 2
			first.Plan.Catalog[1].Shard = 2
			first.Plan.Order = []string{"case.first"}
			first.Results = first.Results[:1]
			second := singleReport("case.first", "case.second")
			second.RunID = "two"
			second.Plan.ShardIndex = 2
			second.Plan.ShardCount = 2
			second.Plan.Catalog[1].Shard = 2
			second.Plan.Order = []string{"case.second"}
			second.Results = second.Results[1:]
			secondSchema := schemaFixture
			firstSchema := schemaFixture
			firstTraces := map[string]string{"case.first": ""}
			switch kind {
			case "image":
				second.Image = "different"
			case "schema":
				secondSchema = strings.Replace(schemaFixture, "read_item", "changed", 1)
			case "catalog":
				second.Plan.Catalog[0].Recipe = "different"
			case "shard-count":
				second.Plan.ShardCount = 3
			case "duplicate-shard":
				second.Plan.ShardIndex = 1
				second.Plan.Order = []string{"case.first"}
				second.Results = []engine.Result{{ID: "case.first", Status: "passed"}}
			case "duplicate-case":
				first.Results = append(first.Results, first.Results[0])
			case "duplicate-run":
				second.RunID = first.RunID
			case "unplanned":
				second.Results[0].ID = "case.unknown"
			case "missing-schema":
				firstSchema = ""
				secondSchema = ""
			case "missing-passed-trace":
				firstTraces = nil
			}
			a := runFixture(t, root, "a", first, firstSchema, firstTraces)
			b := runFixture(t, root, "b", second, secondSchema, map[string]string{"case.second": ""})
			if _, err := Write([]string{a, b}, filepath.Join(root, "out")); err == nil {
				t.Fatalf("accepted invalid %s inputs", kind)
			}
		})
	}
}

func TestFailedMissingTraceAndMissingResultRemainExplicit(t *testing.T) {
	root := t.TempDir()
	report := singleReport("case.failed", "case.absent")
	report.Results = report.Results[:1]
	report.Results[0].Status = "failed"
	dir := runFixture(t, root, "one", report, schemaFixture, nil)
	summary, err := Write([]string{dir}, filepath.Join(root, "out"))
	if err != nil {
		t.Fatal(err)
	}
	if summary.CasesComplete || summary.AllCasesPassed || len(summary.MissingCaseIDs) != 1 || len(summary.MissingTraceCaseIDs) != 1 || summary.SuccessfulOperations != 0 {
		t.Fatalf("missing evidence was hidden: %+v", summary)
	}
}

func TestWebSocketErrorsAndServerFailuresAreNotSuccess(t *testing.T) {
	root := t.TempDir()
	report := singleReport("case.negative")
	dir := runFixture(t, root, "one", report, schemaFixture, map[string]string{"case.negative": trace("websocket_open", "", "/api/events", 403) + trace("http", "GET", "/api/items/failed", 500) + trace("http", "GET", "/api/items/network", 0)})
	summary, err := Write([]string{dir}, filepath.Join(root, "out"))
	if err != nil {
		t.Fatal(err)
	}
	if summary.SuccessfulOperations != 0 || summary.RejectedOnlyOperations != 1 {
		t.Fatalf("error counted as success: %+v", summary)
	}
	if len(findOperation(t, summary, "GET", "/api/items/{item_id}").OtherResponseCases) != 1 {
		t.Fatal("server/transport failure missing")
	}
}
