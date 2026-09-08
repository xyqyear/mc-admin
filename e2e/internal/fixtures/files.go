package fixtures

import (
	"context"
	"fmt"
	"net/url"
	"path"

	"mc-admin/e2e/internal/api"
)

func CreateFile(ctx context.Context, client *api.Client, serverID, file, content string) error {
	if err := client.JSON(ctx, "POST", "/api/servers/"+serverID+"/files/create", map[string]string{"name": path.Base(file), "path": path.Dir(file), "type": "file"}, nil, 200); err != nil {
		return err
	}
	return WriteFile(ctx, client, serverID, file, content)
}

func WriteFile(ctx context.Context, client *api.Client, serverID, file, content string) error {
	return client.JSON(ctx, "POST", "/api/servers/"+serverID+"/files/content?path="+url.QueryEscape(file), map[string]string{"content": content}, nil, 200)
}

func CheckFile(ctx context.Context, client *api.Client, serverID, file, expected string) error {
	var response struct {
		Content string `json:"content"`
	}
	if err := client.JSON(ctx, "GET", "/api/servers/"+serverID+"/files/content?path="+url.QueryEscape(file), nil, &response, 200); err != nil {
		return err
	}
	if response.Content != expected {
		return fmt.Errorf("%s content=%q, expected %q", file, response.Content, expected)
	}
	return nil
}
