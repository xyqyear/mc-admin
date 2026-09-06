package api

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"mime"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"mc-admin/e2e/internal/evidence"
)

const maxBody = 32 << 20

type Client struct {
	BaseURL    string
	ResolveURL func() string
	HTTP       *http.Client
	Bearer     string
	CSRF       bool
	Recorder   *evidence.Recorder
}

func (c *Client) URL() string {
	if c.ResolveURL != nil {
		return c.ResolveURL()
	}
	return c.BaseURL
}

type Response struct {
	Status int
	Header http.Header
	Body   []byte
}

type StatusError struct {
	Code     int
	Expected int
	Body     string
}

func (e *StatusError) Error() string {
	return fmt.Sprintf("expected HTTP %d, got %d: %s", e.Expected, e.Code, e.Body)
}

func New(baseURL string, recorder *evidence.Recorder) *Client {
	jar, _ := cookiejar.New(nil)
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	return &Client{BaseURL: strings.TrimRight(baseURL, "/"), HTTP: &http.Client{
		Jar: jar, Transport: transport, Timeout: 90 * time.Second,
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
	}, CSRF: true, Recorder: recorder}
}

func (c *Client) Close() { c.HTTP.CloseIdleConnections() }

func (c *Client) request(ctx context.Context, method, path string, body []byte, headers http.Header) (*http.Response, error) {
	if !strings.HasPrefix(path, "/") || strings.HasPrefix(path, "//") {
		return nil, fmt.Errorf("API path must be relative: %q", path)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.URL()+path, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	for key, values := range headers {
		req.Header[key] = append([]string(nil), values...)
	}
	if c.Bearer != "" {
		req.Header.Set("Authorization", "Bearer "+c.Bearer)
	}
	if c.CSRF && method != "GET" && method != "HEAD" && method != "OPTIONS" {
		for _, cookie := range c.HTTP.Jar.Cookies(req.URL) {
			if cookie.Name == "mc_admin_csrf" {
				req.Header.Set("X-CSRF-Token", cookie.Value)
			}
		}
	}
	return c.HTTP.Do(req)
}

func bodyEvidence(body []byte, contentType string) any {
	var value any
	if len(body) <= 8192 && json.Unmarshal(body, &value) == nil {
		return value
	}
	if strings.HasPrefix(contentType, "application/x-www-form-urlencoded") {
		values, _ := url.ParseQuery(string(body))
		return values
	}
	return map[string]any{"bytes": len(body), "sha256": fmt.Sprintf("%x", sha256.Sum256(body))}
}

func (c *Client) Do(ctx context.Context, method, path string, body []byte, headers http.Header) (Response, error) {
	start := time.Now()
	response, err := c.request(ctx, method, path, body, headers)
	if err != nil {
		c.Recorder.Event("http", map[string]any{"method": method, "path": path, "error": err.Error()})
		return Response{}, err
	}
	defer response.Body.Close()
	data, err := io.ReadAll(io.LimitReader(response.Body, maxBody+1))
	if len(data) > maxBody {
		err = fmt.Errorf("response exceeds %d bytes", maxBody)
	}
	c.Recorder.Event("http", map[string]any{
		"method": method, "path": path, "status": response.StatusCode, "duration_ms": time.Since(start).Milliseconds(),
		"request": bodyEvidence(body, headers.Get("Content-Type")), "response": bodyEvidence(data, response.Header.Get("Content-Type")),
	})
	return Response{Status: response.StatusCode, Header: response.Header, Body: data}, err
}

func (c *Client) JSON(ctx context.Context, method, path string, input, output any, expected int) error {
	var body []byte
	var err error
	if input != nil {
		body, err = json.Marshal(input)
		if err != nil {
			return err
		}
	}
	response, err := c.Do(ctx, method, path, body, http.Header{"Content-Type": {"application/json"}})
	if err != nil {
		return err
	}
	if err = c.Expect(response, expected); err != nil {
		return fmt.Errorf("%s %s: %w", method, path, err)
	}
	if output != nil {
		return json.Unmarshal(response.Body, output)
	}
	return nil
}

func (c *Client) Expect(response Response, expected int) error {
	if response.Status == expected {
		return nil
	}
	message := string(response.Body)
	if !utf8.Valid(response.Body) || strings.IndexFunc(message, func(r rune) bool { return unicode.IsControl(r) && r != '\n' && r != '\r' && r != '\t' }) >= 0 {
		message = fmt.Sprintf("binary response: %d bytes, sha256 %x", len(response.Body), sha256.Sum256(response.Body))
	}
	if c.Recorder != nil {
		message = c.Recorder.Redactor.Text(message)
	}
	if len(message) > 2048 {
		message = message[:2048] + "…"
	}
	return &StatusError{Code: response.Status, Expected: expected, Body: message}
}

func (c *Client) Login(ctx context.Context, username, password string) error {
	response, err := c.Do(ctx, "POST", "/api/auth/token", []byte(url.Values{"username": {username}, "password": {password}}.Encode()), http.Header{"Content-Type": {"application/x-www-form-urlencoded"}})
	if err != nil {
		return err
	}
	if err = c.Expect(response, 200); err != nil {
		return err
	}
	u, _ := url.Parse(c.URL() + "/api/user/me")
	session, csrf := false, false
	for _, cookie := range c.HTTP.Jar.Cookies(u) {
		if cookie.Name == "mc_admin_session" {
			session = true
		}
		if cookie.Name == "mc_admin_csrf" {
			csrf = true
		}
		if c.Recorder != nil {
			c.Recorder.Redactor.Add(cookie.Value)
		}
	}
	if !session || !csrf {
		return fmt.Errorf("login did not set session and CSRF cookies")
	}
	return nil
}

func contentType(header http.Header) string {
	value, _, _ := mime.ParseMediaType(header.Get("Content-Type"))
	return value
}
