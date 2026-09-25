package world

import (
	"bytes"
	"context"
	"fmt"
	"mime/multipart"
	"net/http"
	"net/url"

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
	var body bytes.Buffer
	form := multipart.NewWriter(&body)
	for _, name := range []string{"e2e-scope.txt", "new-scope.txt"} {
		part, err := form.CreateFormFile("files", name)
		if err != nil {
			return err
		}
		if _, err = part.Write([]byte("must reject")); err != nil {
			return err
		}
	}
	if err := form.Close(); err != nil {
		return err
	}
	response, err := s.client.Do(ctx, "POST", s.base+"/files/upload/multiple?path=/"+fixtureRegion+"&session_id="+uploadSession, body.Bytes(), http.Header{"Content-Type": {form.FormDataContentType()}})
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
	if _, err = s.client.SSE(ctx, "POST", "/api/snapshots/restore", map[string]any{
		"server_id": s.id, "paths": []string{"/e2e-online.txt"}, "snapshot_id": fileSnapshot,
	}, "complete"); err != nil {
		return fmt.Errorf("unrelated ordinary file restore was blocked by world maintenance: %w", err)
	}
	return fixtures.CheckFile(ctx, s.client, s.id, "/e2e-online.txt", "before online restore")
}
