package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestBrowserCommandPassesPrivateFixtureAndPreservesFailure(t *testing.T) {
	path := filepath.Join(t.TempDir(), "private.json")
	if err := os.WriteFile(path, []byte("{}"), 0600); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := runBrowserCommand(ctx, []string{"sh", "-c", `test "$MC_ADMIN_BROWSER_FIXTURE" = "$1"`, "sh", path}, path); err != nil {
		t.Fatal(err)
	}
	if err := runBrowserCommand(ctx, []string{"sh", "-c", "exit 7"}, path); err == nil {
		t.Fatal("child failure was acknowledged as success")
	}
}

func TestBrowserCommandDrainsDescendantsAfterParentExit(t *testing.T) {
	childFile := filepath.Join(t.TempDir(), "child.pid")
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err := runBrowserCommand(ctx, []string{"sh", "-c", `sleep 60 & echo "$!" > "$1"; exit 0`, "sh", childFile}, "fixture"); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(childFile)
	if err != nil {
		t.Fatal(err)
	}
	pid, err := strconv.Atoi(strings.TrimSpace(string(raw)))
	if err != nil {
		t.Fatal(err)
	}
	identity, err := readCommandIdentity(pid)
	if err == nil && identity.state != "Z" && identity.state != "X" {
		t.Fatalf("owned child still running: %+v", identity)
	}
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		t.Fatal(err)
	}
}

func TestBrowserCommandCancellationTerminatesOwnedGroup(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	started := time.Now()
	err := runBrowserCommand(ctx, []string{"sh", "-c", "sleep 60 & wait"}, "fixture")
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("missing cancellation outcome: %v", err)
	}
	if time.Since(started) > 2*time.Second {
		t.Fatal("cancelled subprocess cleanup was not bounded")
	}
}
