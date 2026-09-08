package coverage

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"mc-admin/e2e/internal/engine"
)

func schemaOperations(data []byte) ([]*Operation, error) {
	var schema struct {
		Paths   map[string]map[string]json.RawMessage `json:"paths"`
		Servers []struct {
			URL string `json:"url"`
		} `json:"servers"`
	}
	if err := json.Unmarshal(data, &schema); err != nil {
		return nil, err
	}
	var operations []*Operation
	prefix := ""
	if len(schema.Servers) > 0 {
		server, err := url.Parse(schema.Servers[0].URL)
		if err != nil {
			return nil, fmt.Errorf("invalid OpenAPI server URL: %w", err)
		}
		prefix = strings.TrimRight(server.Path, "/")
	}
	for path, methods := range schema.Paths {
		if !strings.HasPrefix(path, "/") {
			return nil, fmt.Errorf("invalid schema path %q", path)
		}
		for method, body := range methods {
			if !strings.Contains(" get put post delete options head patch trace ", " "+method+" ") {
				continue
			}
			var detail struct {
				ID string `json:"operationId"`
			}
			if err := json.Unmarshal(body, &detail); err != nil {
				return nil, err
			}
			operations = append(operations, newOperation(strings.ToUpper(method), prefix+path, detail.ID))
		}
	}
	for _, path := range []string{"/api/auth/code", "/api/events", "/api/servers/{server_id}/console"} {
		operations = append(operations, newOperation("WS", path, ""))
	}
	return operations, nil
}

func newOperation(method, path, id string) *Operation {
	return &Operation{Method: method, Path: path, OperationID: id, SuccessfulCases: []string{}, RejectedCases: []string{}, OtherResponseCases: []string{}, FailedCases: []string{}, StatusCounts: map[string]int{}}
}

type matcher struct {
	operations []*Operation
	segments   map[string]*regexp.Regexp
}

var pathParameter = regexp.MustCompile(`\{[^{}]+\}`)

func newMatcher(operations []*Operation) *matcher {
	sort.Slice(operations, func(i, j int) bool {
		a, b := operations[i], operations[j]
		ac, bc := strings.Count(a.Path, "{"), strings.Count(b.Path, "{")
		if ac != bc {
			return ac < bc
		}
		as, bs := strings.Split(a.Path, "/"), strings.Split(b.Path, "/")
		for segment := 0; segment < len(as) && segment < len(bs); segment++ {
			ap, bp := strings.HasPrefix(as[segment], "{"), strings.HasPrefix(bs[segment], "{")
			if ap != bp {
				return !ap
			}
		}
		if len(a.Path) != len(b.Path) {
			return len(a.Path) > len(b.Path)
		}
		if a.Path != b.Path {
			return a.Path < b.Path
		}
		return a.Method < b.Method
	})
	segments := map[string]*regexp.Regexp{}
	for _, operation := range operations {
		for _, segment := range strings.Split(operation.Path, "/") {
			indexes := pathParameter.FindAllStringIndex(segment, -1)
			if len(indexes) == 0 {
				continue
			}
			pattern, offset := "^", 0
			for _, index := range indexes {
				pattern += regexp.QuoteMeta(segment[offset:index[0]]) + "[^/]+"
				offset = index[1]
			}
			segments[segment] = regexp.MustCompile(pattern + regexp.QuoteMeta(segment[offset:]) + "$")
		}
	}
	return &matcher{operations: operations, segments: segments}
}

func (m *matcher) match(method, path string) *Operation {
	actual := strings.Split(path, "/")
	for _, operation := range m.operations {
		if method != operation.Method {
			continue
		}
		pattern := strings.Split(operation.Path, "/")
		matches := true
		for index, segment := range pattern {
			if index >= len(actual) {
				matches = false
				break
			}
			if expression, ok := m.segments[segment]; ok {
				if strings.HasSuffix(segment, ":path}") && index == len(pattern)-1 {
					return operation
				}
				if !expression.MatchString(actual[index]) {
					matches = false
					break
				}
			} else if segment != actual[index] {
				matches = false
				break
			}
		}
		if matches && len(pattern) == len(actual) {
			return operation
		}
	}
	return nil
}

func readTrace(file string, result engine.Result, m *matcher, summary *Summary) error {
	f, err := os.Open(file)
	if errors.Is(err, os.ErrNotExist) && result.Status != "passed" {
		summary.MissingTraceCaseIDs = append(summary.MissingTraceCaseIDs, result.ID)
		return nil
	}
	if err != nil {
		return fmt.Errorf("case %s trace: %w", result.ID, err)
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 4096), 2<<20)
	for line := 1; scanner.Scan(); line++ {
		var event struct {
			Kind string          `json:"kind"`
			Data json.RawMessage `json:"data"`
		}
		if err = json.Unmarshal(scanner.Bytes(), &event); err != nil {
			return fmt.Errorf("%s:%d: %w", file, line, err)
		}
		if event.Kind != "http" && event.Kind != "sse_open" && event.Kind != "websocket_open" {
			continue
		}
		var observation struct {
			Method string `json:"method"`
			Path   string `json:"path"`
			Status int    `json:"status"`
		}
		if err = json.Unmarshal(event.Data, &observation); err != nil {
			return fmt.Errorf("%s:%d: %w", file, line, err)
		}
		method := strings.ToUpper(observation.Method)
		if event.Kind == "websocket_open" {
			method = "WS"
		}
		parsed, err := url.ParseRequestURI(observation.Path)
		if err != nil {
			return fmt.Errorf("%s:%d: invalid recorded API path: %w", file, line, err)
		}
		path := parsed.EscapedPath()
		operation := m.match(method, path)
		if operation == nil {
			summary.Unmatched = append(summary.Unmatched, Unmatched{Method: method, Path: path, CaseID: result.ID, Status: observation.Status})
			continue
		}
		operation.StatusCounts[strconv.Itoa(observation.Status)]++
		if result.Status != "passed" {
			addCase(&operation.FailedCases, result.ID)
			continue
		}
		if (method == "WS" && observation.Status == 101) || (method != "WS" && observation.Status >= 200 && observation.Status < 300) {
			addCase(&operation.SuccessfulCases, result.ID)
		} else if observation.Status >= 400 && observation.Status < 500 {
			addCase(&operation.RejectedCases, result.ID)
		} else {
			addCase(&operation.OtherResponseCases, result.ID)
		}
	}
	if err = scanner.Err(); err != nil {
		return fmt.Errorf("%s: %w", file, err)
	}
	return nil
}
