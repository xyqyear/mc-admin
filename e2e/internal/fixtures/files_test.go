package fixtures

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mc-admin/e2e/internal/api"
)

func TestCheckFileRequiresPresentStringContent(t *testing.T) {
	for _, test := range []struct {
		name, body, expected, errorText string
	}{
		{"missing", `{}`, "", "omitted string content"},
		{"null", `{"content":null}`, "", "omitted string content"},
		{"numeric", `{"content":0}`, "", "cannot unmarshal number"},
		{"empty", `{"content":""}`, "", ""},
		{"unicode", `{"content":"世界\n"}`, "世界\n", ""},
		{"different", `{"content":"wrong"}`, "expected", "expected"},
	} {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path != "/api/servers/owned/files/content" || r.URL.Query().Get("path") != "/empty.txt" {
					t.Errorf("unexpected request %s", r.URL)
				}
				w.Header().Set("Content-Type", "application/json")
				_, _ = w.Write([]byte(test.body))
			}))
			defer server.Close()
			client := api.New(server.URL, nil)
			defer client.Close()
			err := CheckFile(context.Background(), client, "owned", "/empty.txt", test.expected)
			if test.errorText == "" && err != nil {
				t.Fatal(err)
			}
			if test.errorText != "" && (err == nil || !strings.Contains(err.Error(), test.errorText)) {
				t.Fatalf("expected %q, got %v", test.errorText, err)
			}
		})
	}
}
