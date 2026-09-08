package evidence

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
	"sync"
	"time"
)

type Redactor struct {
	mu      sync.RWMutex
	secrets []string
}

func (r *Redactor) Add(values ...string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	for _, value := range values {
		if value != "" {
			r.secrets = append(r.secrets, value)
		}
	}
	sort.Slice(r.secrets, func(i, j int) bool { return len(r.secrets[i]) > len(r.secrets[j]) })
}

func (r *Redactor) Text(value string) string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	for _, secret := range r.secrets {
		value = strings.ReplaceAll(value, secret, "[REDACTED]")
	}
	return value
}

func sensitive(key string) bool {
	key = strings.ToLower(key)
	for _, part := range []string{"password", "secret", "token", "cookie", "authorization", "csrf", "ticket", "api_key", "access_key", "private_key"} {
		if strings.Contains(key, part) {
			return true
		}
	}
	return key == "key" || key == "code" || key == "sk" || key == "ak"
}

func (r *Redactor) scrub(value any) any {
	switch v := value.(type) {
	case map[string]any:
		out := make(map[string]any, len(v))
		for key, item := range v {
			if sensitive(key) {
				out[key] = "[REDACTED]"
			} else {
				out[key] = r.scrub(item)
			}
		}
		return out
	case []any:
		for i := range v {
			v[i] = r.scrub(v[i])
		}
		return v
	case string:
		return r.Text(v)
	default:
		return value
	}
}

type Recorder struct {
	mu       sync.Mutex
	file     *os.File
	err      error
	Redactor *Redactor
}

func Open(path string, redactor *Redactor) (*Recorder, error) {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return nil, err
	}
	return &Recorder{file: f, Redactor: redactor}, nil
}

func (r *Recorder) Event(kind string, fields any) {
	if r == nil {
		return
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	data, err := json.Marshal(fields)
	var value any
	if err == nil {
		err = json.Unmarshal(data, &value)
	}
	if err == nil {
		data, err = json.Marshal(map[string]any{"time": time.Now().UTC(), "kind": kind, "data": r.Redactor.scrub(value)})
	}
	if err == nil {
		_, err = fmt.Fprintln(r.file, string(data))
	}
	if err != nil && r.err == nil {
		r.err = err
	}
}

func (r *Recorder) Close() error {
	if r == nil {
		return nil
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	err := r.file.Close()
	if r.err != nil {
		return r.err
	}
	return err
}

func WriteJSON(path string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	if err = os.WriteFile(path+".tmp", append(data, '\n'), 0600); err != nil {
		return err
	}
	return os.Rename(path+".tmp", path)
}
