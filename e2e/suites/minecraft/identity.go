package minecraft

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"path/filepath"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/fixtures"
	"mc-admin/e2e/internal/platform"
)

func serverIdentityAdoption(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	journal := environment.Get[*platform.Journal](t.Env, "journal")
	options := environment.Get[fixtures.Options](t.Env, "options")
	ports, err := platform.LeasePorts(ctx, journal.Docker, options.PortDirectory, 2)
	if err != nil {
		return err
	}
	t.Cleanup(func(context.Context) error { return ports.Close() })
	id := "Legacy.Server_" + t.Env.ID
	if err = journal.Track(t.Env.ID, "mc-"+id, "e2e-"+t.Env.ID); err != nil {
		return err
	}
	project := filepath.Join(t.Env.Dir, "servers", id)
	if err = os.MkdirAll(filepath.Join(project, "data"), 0755); err != nil {
		return err
	}
	compose := fixtures.Compose(t.Env, id, fmt.Sprint(ports.Ports[0]), fmt.Sprint(ports.Ports[1]))
	if err = os.WriteFile(filepath.Join(project, "compose.yaml"), []byte(compose), 0600); err != nil {
		return err
	}
	if err = os.WriteFile(filepath.Join(project, "data", "marker.txt"), []byte("original orphan data"), 0600); err != nil {
		return err
	}
	base := "/api/servers/" + url.PathEscape(id)
	write := func(status int, content string) error {
		return client.JSON(ctx, "POST", base+"/files/content?path=/marker.txt", map[string]string{"content": content}, nil, status)
	}
	type syncResult struct {
		Applied bool `json:"applied"`
		Adopted []struct {
			ID string `json:"server_id"`
		} `json:"adopted"`
		Removed []struct {
			ID string `json:"server_id"`
		} `json:"removed"`
		Preview []struct {
			ID     string `json:"server_id"`
			Action string `json:"action"`
		} `json:"preview"`
		Errors []any `json:"errors"`
	}
	adopt := func() error {
		var result syncResult
		if err := client.JSON(ctx, "POST", "/api/servers/sync", map[string]bool{}, &result, 200); err != nil {
			return err
		}
		if !result.Applied || len(result.Errors) != 0 || len(result.Adopted) != 1 || result.Adopted[0].ID != id {
			return fmt.Errorf("explicit adoption did not register the expected server: %+v", result)
		}
		return nil
	}
	if err = t.Step("an orphan directory and a dry run never authorize writes", func() error {
		if err := write(404, "must not overwrite orphan"); err != nil {
			return err
		}
		var preview syncResult
		if err := client.JSON(ctx, "POST", "/api/servers/sync", map[string]bool{"dry_run": true}, &preview, 200); err != nil {
			return err
		}
		if preview.Applied || len(preview.Errors) != 0 || len(preview.Preview) != 1 || preview.Preview[0].ID != id || preview.Preview[0].Action != "adopt" {
			return fmt.Errorf("unexpected adoption preview: %+v", preview)
		}
		if err := write(404, "must not overwrite after preview"); err != nil {
			return err
		}
		if err := adopt(); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, client, id, "/marker.txt", "original orphan data")
	}); err != nil {
		return err
	}
	if err = t.Step("a missing active directory cannot be silently recreated or an inactive one reused", func() error {
		saved := filepath.Join(t.Env.Dir, "servers", ".saved-"+id)
		if err := os.Rename(project, saved); err != nil {
			return err
		}
		if err := write(404, "missing write"); err != nil {
			return err
		}
		if err := client.JSON(ctx, "POST", base, map[string]string{"yaml_content": compose}, nil, 409); err != nil {
			return err
		}
		var result syncResult
		if err := client.JSON(ctx, "POST", "/api/servers/sync", map[string]bool{}, &result, 200); err != nil {
			return err
		}
		if len(result.Errors) != 0 || len(result.Removed) != 1 || result.Removed[0].ID != id {
			return fmt.Errorf("missing directory was not explicitly deactivated: %+v", result)
		}
		if err := os.Rename(saved, project); err != nil {
			return err
		}
		if err := write(409, "inactive write"); err != nil {
			return err
		}
		if err := adopt(); err != nil {
			return err
		}
		if err := fixtures.CheckFile(ctx, client, id, "/marker.txt", "original orphan data"); err != nil {
			return err
		}
		return write(200, "explicitly adopted new instance")
	}); err != nil {
		return err
	}
	return t.Step("legacy public names and explicit registration survive process restart", func() error {
		if err := fixtures.BackendOf(t.Env).Restart(ctx); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, client, id, "/marker.txt", "explicitly adopted new instance")
	})
}

func serverIdentityPaths(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	id := fixtures.ServerOf(t.Env).ID
	project := filepath.Join(t.Env.Dir, "servers", id)
	base := "/api/servers/" + id + "/files"
	if err = fixtures.CreateFile(ctx, client, id, "/marker.txt", "protected server data"); err != nil {
		return err
	}
	if err = t.Step("traversal names cannot read or write outside the named project", func() error {
		for _, name := range []string{"%2e%2e", "%2e"} {
			if err := client.JSON(ctx, "GET", "/api/servers/"+name+"/files", nil, nil, 400); err != nil {
				return err
			}
			if err := client.JSON(ctx, "POST", "/api/servers/"+name+"/files/content?path=/marker.txt", map[string]string{"content": "traversal overwrite"}, nil, 400); err != nil {
				return err
			}
		}
		return fixtures.CheckFile(ctx, client, id, "/marker.txt", "protected server data")
	}); err != nil {
		return err
	}
	if err = t.Step("a project symlink alias cannot expose or mutate its target", func() error {
		saved := filepath.Join(t.Env.Dir, "servers", ".saved-project")
		if err := os.Rename(project, saved); err != nil {
			return err
		}
		if err := os.Symlink(saved, project); err != nil {
			return err
		}
		if err := client.JSON(ctx, "GET", base+"/content?path=/marker.txt", nil, nil, 409); err != nil {
			return err
		}
		if err := client.JSON(ctx, "POST", base+"/content?path=/marker.txt", map[string]string{"content": "alias overwrite"}, nil, 409); err != nil {
			return err
		}
		if err := os.Remove(project); err != nil {
			return err
		}
		if err := os.Rename(saved, project); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, client, id, "/marker.txt", "protected server data")
	}); err != nil {
		return err
	}
	return t.Step("data-root symlinks cannot turn the project boundary into the filesystem root", func() error {
		data := filepath.Join(project, "data")
		saved := filepath.Join(project, "saved-data")
		if err := os.Rename(data, saved); err != nil {
			return err
		}
		if err := os.Symlink("/", data); err != nil {
			return err
		}
		if err := client.JSON(ctx, "GET", base+"/content?path="+url.QueryEscape(filepath.Join(saved, "marker.txt")), nil, nil, 409); err != nil {
			return err
		}
		if err := client.JSON(ctx, "POST", base+"/content?path="+url.QueryEscape(filepath.Join(saved, "marker.txt")), map[string]string{"content": "data-root overwrite"}, nil, 409); err != nil {
			return err
		}
		if err := os.Remove(data); err != nil {
			return err
		}
		if err := os.Rename(saved, data); err != nil {
			return err
		}
		return fixtures.CheckFile(ctx, client, id, "/marker.txt", "protected server data")
	})
}
