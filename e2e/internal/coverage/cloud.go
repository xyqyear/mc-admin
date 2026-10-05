package coverage

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

type cloudScope struct {
	Version     int    `json:"version"`
	Provider    string `json:"provider"`
	Environment string `json:"environment"`
	RunID       string `json:"run_id"`
	Domain      string `json:"domain"`
	Scope       string `json:"scope"`
	Helper      string `json:"helper"`
	Armed       bool   `json:"armed"`
	Cleaned     bool   `json:"cleaned"`
}

func (scope cloudScope) binding() cloudScope {
	scope.Armed = false
	scope.Cleaned = false
	return scope
}
func cloudReceipt(directory, caseID string) (cloudScope, error) {
	file, err := os.Open(filepath.Join(directory, "cases", caseID+".jsonl"))
	if err != nil {
		return cloudScope{}, err
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 4096), 2<<20)
	var initial cloudScope
	started, closed := false, false
	for scanner.Scan() {
		var event struct {
			Kind string          `json:"kind"`
			Data json.RawMessage `json:"data"`
		}
		if err = json.Unmarshal(scanner.Bytes(), &event); err != nil {
			return initial, err
		}
		switch event.Kind {
		case "external_dns_scope":
			if started {
				return initial, fmt.Errorf("duplicate initial cloud scope receipt")
			}
			if err = json.Unmarshal(event.Data, &initial); err != nil {
				return initial, err
			}
			started = true
		case "external_dns_cleanup":
			var cleanup struct {
				Manifest cloudScope `json:"manifest"`
			}
			if err = json.Unmarshal(event.Data, &cleanup); err != nil {
				return initial, err
			}
			if !started || closed || initial.binding() != cleanup.Manifest.binding() {
				return initial, fmt.Errorf("cloud cleanup trace differs from initial authorized scope")
			}
			closed = true
		}
	}
	if err = scanner.Err(); err != nil {
		return initial, err
	}
	if !started || !closed {
		return initial, fmt.Errorf("cloud case lacks initial scope or cleanup trace")
	}
	return initial, nil
}
