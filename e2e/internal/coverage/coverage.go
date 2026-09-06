package coverage

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"sort"
	"strings"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/evidence"
)

type Operation struct {
	Method             string         `json:"method"`
	Path               string         `json:"path"`
	OperationID        string         `json:"operation_id,omitempty"`
	SuccessfulCases    []string       `json:"passed_success_cases"`
	RejectedCases      []string       `json:"passed_rejection_cases"`
	OtherResponseCases []string       `json:"passed_other_response_cases"`
	FailedCases        []string       `json:"failed_case_observations"`
	StatusCounts       map[string]int `json:"status_counts"`
}

type Unmatched struct {
	Method string `json:"method"`
	Path   string `json:"path"`
	CaseID string `json:"case_id"`
	Status int    `json:"status"`
}

type Summary struct {
	Generated                time.Time   `json:"generated"`
	RunIDs                   []string    `json:"run_ids"`
	Image                    string      `json:"application_image"`
	SchemaSHA256             string      `json:"schema_sha256"`
	SelectedCases            int         `json:"selected_cases"`
	RecordedCases            int         `json:"recorded_cases"`
	PassedCases              int         `json:"passed_cases"`
	CasesComplete            bool        `json:"selected_cases_complete"`
	AllCasesPassed           bool        `json:"all_selected_cases_passed"`
	ShardsComplete           bool        `json:"shards_complete"`
	MissingCaseIDs           []string    `json:"missing_case_ids"`
	MissingShardIndexes      []int       `json:"missing_shard_indexes"`
	MissingTraceCaseIDs      []string    `json:"missing_trace_case_ids"`
	RunErrors                []string    `json:"run_errors"`
	OperationCount           int         `json:"operation_count"`
	SuccessfulOperations     int         `json:"operations_with_passed_success_observation"`
	RejectedOnlyOperations   int         `json:"operations_with_rejection_but_no_passed_success"`
	UnobservedOperations     int         `json:"unobserved_operation_count"`
	MissingSuccessOperations []string    `json:"operations_without_passed_success_observation"`
	Operations               []Operation `json:"operations"`
	Unmatched                []Unmatched `json:"unmatched_observations"`
}

type source struct {
	dir    string
	report engine.Report
}

var safeCaseID = regexp.MustCompile(`^[a-z][a-z0-9_.-]+$`)

func Write(runDirs []string, outputDir string) (Summary, error) {
	summary, err := collect(runDirs)
	if err != nil {
		return summary, err
	}
	if outputDir == "" {
		return summary, fmt.Errorf("coverage output directory is required")
	}
	if err = os.MkdirAll(outputDir, 0700); err != nil {
		return summary, err
	}
	if err = evidence.WriteJSON(filepath.Join(outputDir, "coverage.json"), summary); err != nil {
		return summary, err
	}
	if err = os.WriteFile(filepath.Join(outputDir, "coverage.md"), []byte(markdown(summary)), 0600); err != nil {
		return summary, err
	}
	return summary, nil
}

func collect(runDirs []string) (Summary, error) {
	summary := Summary{Generated: time.Now().UTC(), RunIDs: []string{}, MissingCaseIDs: []string{}, MissingShardIndexes: []int{}, MissingTraceCaseIDs: []string{}, RunErrors: []string{}, MissingSuccessOperations: []string{}, Unmatched: []Unmatched{}}
	if len(runDirs) == 0 {
		return summary, fmt.Errorf("at least one run directory is required")
	}
	var sources []source
	var canonicalCatalog []engine.Entry
	var canonicalSchema []byte
	shardCount := 0
	shards := map[int]bool{}
	runs := map[string]bool{}
	caseSources := map[string]string{}
	for _, dir := range runDirs {
		data, err := os.ReadFile(filepath.Join(dir, "results.json"))
		if err != nil {
			return summary, err
		}
		var report engine.Report
		if err = json.Unmarshal(data, &report); err != nil {
			return summary, fmt.Errorf("%s: %w", dir, err)
		}
		if report.Image == "" || report.RunID == "" {
			return summary, fmt.Errorf("%s: missing application image or run identity", dir)
		}
		if runs[report.RunID] {
			return summary, fmt.Errorf("duplicate run ID %s", report.RunID)
		}
		runs[report.RunID] = true
		if summary.Image != "" && report.Image != summary.Image {
			return summary, fmt.Errorf("incompatible application images: %s and %s", summary.Image, report.Image)
		}
		summary.Image = report.Image
		catalog, err := validatePlan(report.Plan)
		if err != nil {
			return summary, fmt.Errorf("%s: %w", report.RunID, err)
		}
		if len(sources) == 0 {
			canonicalCatalog = catalog
			shardCount = report.Plan.ShardCount
		} else if shardCount != report.Plan.ShardCount || !reflect.DeepEqual(canonicalCatalog, catalog) {
			return summary, fmt.Errorf("incompatible shard selections or catalogs in run %s", report.RunID)
		}
		if shards[report.Plan.ShardIndex] {
			return summary, fmt.Errorf("duplicate shard index %d", report.Plan.ShardIndex)
		}
		shards[report.Plan.ShardIndex] = true
		planned := map[string]bool{}
		for _, id := range report.Plan.Order {
			planned[id] = true
		}
		for _, result := range report.Results {
			if !safeCaseID.MatchString(result.ID) || !planned[result.ID] {
				return summary, fmt.Errorf("unplanned case result %q in run %s", result.ID, report.RunID)
			}
			if prior, ok := caseSources[result.ID]; ok {
				return summary, fmt.Errorf("duplicate case result %s in runs %s and %s", result.ID, prior, report.RunID)
			}
			caseSources[result.ID] = report.RunID
			summary.RecordedCases++
			if result.Status == "passed" {
				summary.PassedCases++
			}
		}
		schemaFiles, err := filepath.Glob(filepath.Join(dir, "environments", "*", "openapi.json"))
		if err != nil {
			return summary, err
		}
		for _, file := range schemaFiles {
			schema, err := readSchema(file)
			if err != nil {
				return summary, err
			}
			if canonicalSchema != nil && string(canonicalSchema) != string(schema) {
				return summary, fmt.Errorf("incompatible OpenAPI schema in %s", file)
			}
			canonicalSchema = schema
		}
		summary.RunIDs = append(summary.RunIDs, report.RunID)
		for _, issue := range report.Errors {
			summary.RunErrors = append(summary.RunErrors, report.RunID+": "+issue)
		}
		sources = append(sources, source{dir: dir, report: report})
	}
	if canonicalSchema == nil {
		return summary, fmt.Errorf("no captured OpenAPI schema in the selected runs")
	}
	summary.SchemaSHA256 = fmt.Sprintf("%x", sha256.Sum256(canonicalSchema))
	summary.SelectedCases = len(canonicalCatalog)
	for _, entry := range canonicalCatalog {
		if _, ok := caseSources[entry.ID]; !ok {
			summary.MissingCaseIDs = append(summary.MissingCaseIDs, entry.ID)
		}
	}
	for shard := 1; shard <= shardCount; shard++ {
		if !shards[shard] {
			summary.MissingShardIndexes = append(summary.MissingShardIndexes, shard)
		}
	}
	summary.CasesComplete = len(summary.MissingCaseIDs) == 0
	summary.ShardsComplete = len(summary.MissingShardIndexes) == 0
	summary.AllCasesPassed = summary.CasesComplete && summary.PassedCases == summary.SelectedCases && len(summary.RunErrors) == 0
	operations, err := schemaOperations(canonicalSchema)
	if err != nil {
		return summary, err
	}
	matcher := newMatcher(operations)
	for _, src := range sources {
		for _, result := range src.report.Results {
			trace := filepath.Join(src.dir, "cases", result.ID+".jsonl")
			if err := readTrace(trace, result, matcher, &summary); err != nil {
				return summary, err
			}
		}
	}
	for _, operation := range matcher.operations {
		for _, values := range [][]string{operation.SuccessfulCases, operation.RejectedCases, operation.OtherResponseCases, operation.FailedCases} {
			sort.Strings(values)
		}
		if len(operation.SuccessfulCases) > 0 {
			summary.SuccessfulOperations++
		} else {
			summary.MissingSuccessOperations = append(summary.MissingSuccessOperations, operation.Method+" "+operation.Path)
			if len(operation.RejectedCases) > 0 {
				summary.RejectedOnlyOperations++
			}
		}
		if len(operation.StatusCounts) == 0 {
			summary.UnobservedOperations++
		}
		summary.Operations = append(summary.Operations, *operation)
	}
	sort.Slice(summary.Operations, func(i, j int) bool {
		a, b := summary.Operations[i], summary.Operations[j]
		if a.Path == b.Path {
			return a.Method < b.Method
		}
		return a.Path < b.Path
	})
	sort.Strings(summary.RunIDs)
	sort.Strings(summary.MissingSuccessOperations)
	sort.Strings(summary.MissingTraceCaseIDs)
	sort.Slice(summary.Unmatched, func(i, j int) bool {
		a, b := summary.Unmatched[i], summary.Unmatched[j]
		return fmt.Sprint(a.Method, a.Path, a.CaseID, a.Status) < fmt.Sprint(b.Method, b.Path, b.CaseID, b.Status)
	})
	summary.OperationCount = len(summary.Operations)
	return summary, nil
}

func validatePlan(plan engine.Plan) ([]engine.Entry, error) {
	if plan.ShardCount < 1 || plan.ShardIndex < 1 || plan.ShardIndex > plan.ShardCount || len(plan.Catalog) == 0 {
		return nil, fmt.Errorf("invalid shard plan")
	}
	catalog := append([]engine.Entry(nil), plan.Catalog...)
	sort.Slice(catalog, func(i, j int) bool { return catalog[i].ID < catalog[j].ID })
	ids := map[string]bool{}
	assigned := map[string]bool{}
	for index := range catalog {
		entry := &catalog[index]
		if !safeCaseID.MatchString(entry.ID) || ids[entry.ID] || entry.Shard < 1 || entry.Shard > plan.ShardCount {
			return nil, fmt.Errorf("invalid catalog case %q", entry.ID)
		}
		ids[entry.ID] = true
		entry.Tags = append([]string(nil), entry.Tags...)
		sort.Strings(entry.Tags)
		if entry.Shard == plan.ShardIndex {
			assigned[entry.ID] = true
		}
	}
	for _, id := range plan.Order {
		if !assigned[id] {
			return nil, fmt.Errorf("unexpected or duplicate planned case %s", id)
		}
		delete(assigned, id)
	}
	if len(assigned) > 0 {
		return nil, fmt.Errorf("plan order omits assigned cases")
	}
	return catalog, nil
}

func readSchema(file string) ([]byte, error) {
	data, err := os.ReadFile(file)
	if err != nil {
		return nil, err
	}
	var schema map[string]any
	if err = json.Unmarshal(data, &schema); err != nil {
		return nil, fmt.Errorf("%s: %w", file, err)
	}
	if _, ok := schema["paths"].(map[string]any); !ok {
		return nil, fmt.Errorf("%s: OpenAPI paths object missing", file)
	}
	return json.Marshal(schema)
}

func addCase(values *[]string, id string) {
	for _, value := range *values {
		if value == id {
			return
		}
	}
	*values = append(*values, id)
}

func markdown(summary Summary) string {
	var out strings.Builder
	out.WriteString("# API operation observations\n\nThese counts describe API responses observed in recorded cases. Route visitation does not prove complete feature behavior, and HTTP 4xx responses do not count as successful operation observations. Fixture setup traffic is excluded.\n\n")
	fmt.Fprintf(&out, "Application image: `%s`\n\nSelected cases: %d; recorded: %d; passed: %d. Case selection complete: **%t**; all selected cases passed: **%t**; shard reports complete: **%t**.\n\n", summary.Image, summary.SelectedCases, summary.RecordedCases, summary.PassedCases, summary.CasesComplete, summary.AllCasesPassed, summary.ShardsComplete)
	fmt.Fprintf(&out, "Operations: %d; observed with success in a passed case: %d; rejection without passed success: %d; unobserved: %d.\n\n", summary.OperationCount, summary.SuccessfulOperations, summary.RejectedOnlyOperations, summary.UnobservedOperations)
	if len(summary.MissingCaseIDs) > 0 {
		fmt.Fprintf(&out, "Missing selected cases: %s.\n\n", strings.Join(summary.MissingCaseIDs, ", "))
	}
	if len(summary.MissingShardIndexes) > 0 {
		fmt.Fprintf(&out, "Missing shard reports: %v.\n\n", summary.MissingShardIndexes)
	}
	out.WriteString("| Operation | Passed success | Passed rejection | Passed other response | Failed case observation |\n| --- | --- | --- | --- | --- |\n")
	for _, operation := range summary.Operations {
		fmt.Fprintf(&out, "| `%s %s` | %s | %s | %s | %s |\n", operation.Method, operation.Path, caseNames(operation.SuccessfulCases), caseNames(operation.RejectedCases), caseNames(operation.OtherResponseCases), caseNames(operation.FailedCases))
	}
	if len(summary.Unmatched) > 0 {
		fmt.Fprintf(&out, "\n%d observations did not match a documented HTTP operation or registered WebSocket route; see coverage.json.\n", len(summary.Unmatched))
	}
	return out.String()
}

func caseNames(values []string) string {
	if len(values) == 0 {
		return "—"
	}
	return strings.Join(values, "<br>")
}
