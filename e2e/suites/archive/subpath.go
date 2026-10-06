package archive

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"path/filepath"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func subpathCompression(ctx context.Context, t *engine.Scope) error {
	c, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	for _, file := range []struct{ path, content string }{
		{"/plugins/plugin.jar", "selected plugin bytes\n"},
		{"/config.yml", "unselected configuration\n"},
		{"/test.txt", "first file bytes\n"},
	} {
		if err = fixtures.CreateFile(ctx, c, id, file.path, file.content); err != nil {
			return err
		}
	}
	backend := fixtures.BackendOf(t.Env)
	const inspectArchive = `import base64,json,subprocess,sys
archive,member=sys.argv[1:]
listing=subprocess.check_output(['7z','l','-slt',archive],text=True).split('----------\n',1)[1]
paths=[line.removeprefix('Path = ') for line in listing.splitlines() if line.startswith('Path = ')]
content=subprocess.check_output(['7z','x','-so',archive,member])
print(json.dumps({'members':paths,'content':base64.b64encode(content).decode()}))`
	compress := func(selected, member string, expected []string, content string) (string, []byte, error) {
		var accepted struct {
			ID string `json:"task_id"`
		}
		if err := c.JSON(ctx, "POST", "/api/archive/compress", map[string]string{"server_id": id, "path": selected}, &accepted, 200); err != nil {
			return "", nil, err
		}
		task, err := c.Task(ctx, accepted.ID)
		if err != nil {
			return "", nil, err
		}
		filename, ok := task.Result["filename"].(string)
		if !ok || filename == "" {
			return "", nil, fmt.Errorf("selected compression has no output filename")
		}
		response, err := c.Do(ctx, "GET", "/api/archive/download?path="+url.QueryEscape("/"+filename), nil, nil)
		if err != nil {
			return "", nil, err
		}
		if err = c.Expect(response, 200); err != nil {
			return "", nil, err
		}
		if size, ok := task.Result["size"].(float64); !ok || size != float64(len(response.Body)) || size <= 0 {
			return "", nil, fmt.Errorf("selected archive size differs from downloaded bytes")
		}
		output, err := backend.Docker.Run(ctx, "exec", backend.Name, "python", "-c", inspectArchive, filepath.Join("/data/archives", filename), member)
		if err != nil {
			return "", nil, err
		}
		var archive struct {
			Members []string `json:"members"`
			Content []byte   `json:"content"`
		}
		if err = json.Unmarshal([]byte(output), &archive); err != nil {
			return "", nil, err
		}
		if len(archive.Members) != len(expected) {
			return "", nil, fmt.Errorf("selected archive members %v differ from %v", archive.Members, expected)
		}
		for i, name := range expected {
			if archive.Members[i] != name {
				return "", nil, fmt.Errorf("selected archive members %v differ from %v", archive.Members, expected)
			}
		}
		if string(archive.Content) != content {
			return "", nil, fmt.Errorf("selected archive member %s has incorrect bytes", member)
		}
		return filename, response.Body, nil
	}
	if err = t.Step("directory compression includes only the selected subtree and its original bytes", func() error {
		_, _, err := compress("/plugins", "plugins/plugin.jar", []string{"plugins", "plugins/plugin.jar"}, "selected plugin bytes\n")
		return err
	}); err != nil {
		return err
	}
	return t.Step("single-file tasks retain independent output paths and both generations of bytes", func() error {
		first, firstBytes, err := compress("/test.txt", "test.txt", []string{"test.txt"}, "first file bytes\n")
		if err != nil {
			return err
		}
		if err = c.JSON(ctx, "POST", "/api/servers/"+id+"/files/content?path=/test.txt", map[string]string{"content": "second file bytes\n"}, nil, 200); err != nil {
			return err
		}
		second, _, err := compress("/test.txt", "test.txt", []string{"test.txt"}, "second file bytes\n")
		if err != nil {
			return err
		}
		if first == second {
			return fmt.Errorf("separate single-file tasks reused an output path")
		}
		response, err := c.Do(ctx, "GET", "/api/archive/download?path="+url.QueryEscape("/"+first), nil, nil)
		if err != nil {
			return err
		}
		if err = c.Expect(response, 200); err != nil {
			return err
		}
		if !bytes.Equal(response.Body, firstBytes) {
			return fmt.Errorf("later compression changed the first single-file archive")
		}
		return fixtures.CheckFile(ctx, c, id, "/config.yml", "unselected configuration\n")
	})
}
