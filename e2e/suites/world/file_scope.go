package world

import (
	"context"
	"fmt"
	"net/http"
	"net/url"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/fixtures"
)

const scopeMarker = "/" + fixtureRegion + "/e2e-scope.txt"

func (s *scenario) prepareScopedUpload(ctx context.Context) (string, error) {
	if err := fixtures.CreateFile(ctx, s.client, s.id, scopeMarker, "world scope original"); err != nil {
		return "", err
	}
	var session struct {
		ID string `json:"session_id"`
	}
	files := []map[string]any{
		{"path": "e2e-scope.txt", "name": "e2e-scope.txt", "type": "file", "size": 11},
		{"path": "new-scope.txt", "name": "new-scope.txt", "type": "file", "size": 11},
	}
	if err := s.client.JSON(ctx, "POST", s.base+"/files/upload/check?path=/"+fixtureRegion, map[string]any{"files": files}, &session, 200); err != nil {
		return "", err
	}
	err := s.client.JSON(ctx, "POST", s.base+"/files/upload/policy?session_id="+session.ID, map[string]string{"mode": "always_overwrite"}, nil, 200)
	return session.ID, err
}

func (s *scenario) checkScopedFiles(ctx context.Context, uploadSession, fileSnapshot string) error {
	for _, request := range []struct {
		method, path string
		body         any
	}{
		{"POST", "/content?path=" + url.QueryEscape(scopeMarker), map[string]string{"content": "must not overwrite"}},
		{"POST", "/rename", map[string]string{"old_path": scopeMarker, "new_name": "renamed.txt"}},
		{"DELETE", "?path=" + url.QueryEscape(scopeMarker), nil},
		{"POST", "/create", map[string]string{"path": "/" + fixtureRegion, "name": "created.txt", "type": "file"}},
	} {
		if err := s.client.JSON(ctx, request.method, s.base+"/files"+request.path, request.body, nil, 423); err != nil {
			return fmt.Errorf("overlapping file mutation must conflict with world restore: %w", err)
		}
	}
	body, contentType, err := api.MultipartFiles([]api.FilePart{
		{Filename: "e2e-scope.txt", Content: []byte("must reject")},
		{Filename: "new-scope.txt", Content: []byte("must reject")},
	})
	if err != nil {
		return err
	}
	response, err := s.client.Do(ctx, "POST", s.base+"/files/upload/multiple?path=/"+fixtureRegion+"&session_id="+uploadSession, body, http.Header{"Content-Type": {contentType}})
	if err != nil {
		return err
	}
	if err = s.client.Expect(response, 423); err != nil {
		return err
	}
	if err = fixtures.CheckFile(ctx, s.client, s.id, scopeMarker, "world scope original"); err != nil {
		return err
	}
	if err = s.client.JSON(ctx, "GET", s.base+"/files/content?path=/"+fixtureRegion+"/new-scope.txt", nil, nil, 404); err != nil {
		return err
	}
	if err = fixtures.WriteFile(ctx, s.client, s.id, "/e2e-online.txt", "unrelated ordinary file remains writable"); err != nil {
		return err
	}
	if _, err = s.client.RunTaskResult(ctx, "POST", "/api/snapshots/restorations", map[string]any{"scope": map[string]any{"kind": "paths", "server_id": s.id, "paths": []string{"e2e-online.txt"}}, "source_snapshot_id": fileSnapshot}); err != nil {
		return fmt.Errorf("unrelated ordinary file restore was blocked by world maintenance: %w", err)
	}
	return fixtures.CheckFile(ctx, s.client, s.id, "/e2e-online.txt", "before online restore")
}
