package api

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestPermanentPollErrorDoesNotRetry(t *testing.T) {
	calls := 0
	failure := errors.New("resource disappeared")
	err := Wait(context.Background(), time.Millisecond, "task", func(context.Context) (bool, error) { calls++; return false, Permanent(failure) })
	if !errors.Is(err, failure) || calls != 1 {
		t.Fatalf("permanent error retried: %v (%d calls)", err, calls)
	}
}

func TestSessionCSRFAndEndpointRefresh(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/auth/token" {
			http.SetCookie(w, &http.Cookie{Name: "mc_admin_session", Value: "session-value", Path: "/api", HttpOnly: true})
			http.SetCookie(w, &http.Cookie{Name: "mc_admin_csrf", Value: "csrf-value", Path: "/"})
			fmt.Fprint(w, `{"user":{}}`)
			return
		}
		cookie, err := r.Cookie("mc_admin_session")
		if err != nil || cookie.Value != "session-value" {
			w.WriteHeader(401)
			return
		}
		if r.Method == "POST" && r.Header.Get("X-CSRF-Token") != "csrf-value" {
			w.WriteHeader(403)
			return
		}
		fmt.Fprint(w, `{}`)
	})
	first := httptest.NewServer(handler)
	second := httptest.NewServer(handler)
	defer second.Close()
	endpoint := first.URL
	client := New(endpoint, nil)
	defer client.Close()
	client.ResolveURL = func() string { return endpoint }
	ctx := context.Background()
	if err := client.Login(ctx, "owner", "password"); err != nil {
		t.Fatal(err)
	}
	if err := client.JSON(ctx, "POST", "/api/write", nil, nil, 200); err != nil {
		t.Fatal(err)
	}
	client.CSRF = false
	if err := client.JSON(ctx, "POST", "/api/write", nil, nil, 403); err != nil {
		t.Fatal(err)
	}
	first.Close()
	endpoint = second.URL
	client.CSRF = true
	if err := client.JSON(ctx, "POST", "/api/write", nil, nil, 200); err != nil {
		t.Fatalf("session did not survive endpoint refresh: %v", err)
	}
}

func TestSSERequiresTerminalAndSupportsMultilineFrames(t *testing.T) {
	accept := func(event map[string]any) (bool, error) { return event["event_type"] == "complete", nil }
	event, err := ReadSSE(strings.NewReader(": heartbeat\n\ndata: {\ndata: \"event_type\":\"complete\"}\n\n"), accept)
	if err != nil || event["event_type"] != "complete" {
		t.Fatalf("multiline frame: %v, %v", event, err)
	}
	for _, body := range []string{"data: {\"event_type\":\"progress\"}\n\n", "data: bad\n\n", "data: {\"event_type\":\"complete\"}"} {
		if _, err := ReadSSE(strings.NewReader(body), accept); err == nil {
			t.Fatalf("accepted incomplete/malformed SSE %q", body)
		}
	}
}

func TestRequestDeadlineCancelsBodyRead(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		w.(http.Flusher).Flush()
		<-r.Context().Done()
	}))
	defer server.Close()
	client := New(server.URL, nil)
	defer client.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	if _, err := client.Do(ctx, "GET", "/slow", nil, nil); err == nil {
		t.Fatal("body read ignored context deadline")
	}
}

func TestSSEUsesOperationDeadlineAndSharedSession(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/auth/token" {
			http.SetCookie(w, &http.Cookie{Name: "mc_admin_session", Value: "session", Path: "/"})
			http.SetCookie(w, &http.Cookie{Name: "mc_admin_csrf", Value: "csrf", Path: "/"})
			fmt.Fprint(w, `{}`)
			return
		}
		if cookie, err := r.Cookie("mc_admin_session"); err != nil || cookie.Value != "session" || r.Header.Get("X-CSRF-Token") != "csrf" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		w.(http.Flusher).Flush()
		if r.URL.Path == "/cancel" {
			<-r.Context().Done()
			return
		}
		time.Sleep(30 * time.Millisecond)
		fmt.Fprint(w, "data: {\"event_type\":\"complete\"}\n\n")
	}))
	defer server.Close()
	client := New(server.URL, nil)
	defer client.Close()
	if err := client.Login(context.Background(), "owner", "password"); err != nil {
		t.Fatal(err)
	}
	client.HTTP.Timeout = time.Millisecond
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if _, err := client.SSE(ctx, "POST", "/stream", nil, "complete"); err != nil {
		t.Fatalf("valid long stream failed: %v", err)
	}
	if client.HTTP.Timeout != time.Millisecond {
		t.Fatal("stream changed ordinary request timeout")
	}
	short, stop := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer stop()
	if _, err := client.SSE(short, "POST", "/cancel", nil, "complete"); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("stream did not honor operation deadline: %v", err)
	}
}

func TestSSETerminalVariantsAndObserverFailure(t *testing.T) {
	for _, field := range []string{"event_type", "type", "stage"} {
		t.Run(field, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.Header().Set("Content-Type", "text/event-stream")
				fmt.Fprintf(w, "data: {\"%s\":\"progress\"}\n\ndata: {\"%s\":\"complete\"}\n\n", field, field)
			}))
			defer server.Close()
			client := New(server.URL, nil)
			defer client.Close()
			observed := 0
			if _, err := client.SSEEvents(context.Background(), "GET", "/stream", nil, "complete", func(map[string]any) error { observed++; return nil }); err != nil || observed != 2 {
				t.Fatalf("terminal/observer: %v, events %d", err, observed)
			}
			failure := errors.New("invalid progress payload")
			if _, err := client.SSEEvents(context.Background(), "GET", "/stream", nil, "complete", func(map[string]any) error { return failure }); !errors.Is(err, failure) {
				t.Fatalf("observer error not propagated: %v", err)
			}
		})
	}
}

func TestBinaryStatusErrorDoesNotPrintRawContent(t *testing.T) {
	client := New("http://unused.invalid", nil)
	defer client.Close()
	err := client.Expect(Response{Status: 200, Body: []byte{'P', 'N', 'G', 0, 255}}, 404)
	if err == nil || !strings.Contains(err.Error(), "sha256") || strings.ContainsRune(err.Error(), '\x00') {
		t.Fatalf("binary body is not bounded evidence: %v", err)
	}
}
