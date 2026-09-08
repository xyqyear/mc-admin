package engine

import (
	"encoding/xml"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"mc-admin/e2e/internal/evidence"
)

type Report struct {
	RunID            string    `json:"run_id"`
	Image            string    `json:"image"`
	MinecraftImage   string    `json:"minecraft_image"`
	MinecraftVersion string    `json:"minecraft_version"`
	NoReuse          bool      `json:"no_reuse"`
	Started          time.Time `json:"started"`
	Plan             Plan      `json:"plan"`
	Results          []Result  `json:"results"`
	Errors           []string  `json:"errors,omitempty"`
}

func (r Report) Failed() bool {
	if len(r.Errors) > 0 {
		return true
	}
	for _, result := range r.Results {
		if result.Status != "passed" {
			return true
		}
	}
	return len(r.Results) != len(r.Plan.Order)
}

type junitSuite struct {
	XMLName  xml.Name    `xml:"testsuite"`
	Name     string      `xml:"name,attr"`
	Tests    int         `xml:"tests,attr"`
	Failures int         `xml:"failures,attr"`
	Cases    []junitCase `xml:"testcase"`
}
type junitCase struct {
	Name    string        `xml:"name,attr"`
	Class   string        `xml:"classname,attr"`
	Time    string        `xml:"time,attr"`
	Failure *junitFailure `xml:"failure,omitempty"`
}
type junitFailure struct {
	Message string `xml:"message,attr"`
	Text    string `xml:",chardata"`
}

func (r Report) Write(dir string) error {
	if err := evidence.WriteJSON(filepath.Join(dir, "results.json"), r); err != nil {
		return err
	}
	suite := junitSuite{Name: "mc-admin-e2e"}
	for _, result := range r.Results {
		test := junitCase{Name: result.ID, Class: result.Suite, Time: fmt.Sprintf("%.3f", result.Seconds)}
		if result.Status != "passed" {
			var issues []string
			for _, issue := range result.Issues {
				issues = append(issues, issue.Phase+": "+issue.Message)
			}
			test.Failure = &junitFailure{Message: result.Status, Text: strings.Join(issues, "\n")}
			suite.Failures++
		}
		suite.Cases = append(suite.Cases, test)
	}
	for _, err := range r.Errors {
		suite.Cases = append(suite.Cases, junitCase{Name: "run.infrastructure", Class: "runner", Time: "0", Failure: &junitFailure{Message: err, Text: err}})
		suite.Failures++
	}
	suite.Tests = len(suite.Cases)
	data, err := xml.MarshalIndent(suite, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(dir, "junit.xml"), append([]byte(xml.Header), data...), 0600)
}
