package platform

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCleanupCannotOpenAnActiveRun(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "run")
	journal, err := NewJournal(dir, "e2e-test-run", Docker{Socket: "/var/run/docker.sock"}, "app:test")
	if err != nil {
		t.Fatal(err)
	}
	if opened, err := OpenJournal(dir); err == nil {
		opened.Close()
		t.Fatal("cleanup opened an active run")
	}
	if err = journal.Close(); err != nil {
		t.Fatal(err)
	}
	opened, err := OpenJournal(dir)
	if err != nil {
		t.Fatal(err)
	}
	opened.Close()
}

func TestManifestRejectsTraversalAndDirectoryMismatch(t *testing.T) {
	for _, mode := range []string{"directory", "environment", "project"} {
		t.Run(mode, func(t *testing.T) {
			dir := filepath.Join(t.TempDir(), "run")
			journal, err := NewJournal(dir, "e2e-test-run", Docker{}, "app:test")
			if err != nil {
				t.Fatal(err)
			}
			if err = journal.AddEnvironment("abcdef123456"); err != nil {
				t.Fatal(err)
			}
			switch mode {
			case "directory":
				journal.Manifest.Directory = filepath.Dir(dir)
			case "environment":
				journal.Manifest.Environments[0].ID = "../../outside"
			case "project":
				journal.Manifest.Environments[0].Projects = []string{"unrelated-project"}
			}
			if mode == "directory" {
				journal.Manifest.Directory = dir
				if err = journal.save(); err != nil {
					t.Fatal(err)
				}
				data, _ := os.ReadFile(filepath.Join(dir, "manifest.json"))
				other := filepath.Join(t.TempDir(), "copied")
				if err = os.Mkdir(other, 0700); err != nil {
					t.Fatal(err)
				}
				if err = os.WriteFile(filepath.Join(other, "manifest.json"), data, 0600); err != nil {
					t.Fatal(err)
				}
				journal.Close()
				dir = other
			} else {
				if err = journal.save(); err != nil {
					t.Fatal(err)
				}
				journal.Close()
			}
			if opened, err := OpenJournal(dir); err == nil {
				opened.Close()
				t.Fatal("unsafe manifest accepted")
			}
		})
	}
}

func TestFileLeaseCannotBeClaimedTwice(t *testing.T) {
	path := filepath.Join(t.TempDir(), "port.lock")
	first, err := TryLock(path)
	if err != nil {
		t.Fatal(err)
	}
	if second, err := TryLock(path); err == nil {
		second.Close()
		t.Fatal("double lease accepted")
	}
	first.Close()
	second, err := TryLock(path)
	if err != nil {
		t.Fatal(err)
	}
	second.Close()
}
