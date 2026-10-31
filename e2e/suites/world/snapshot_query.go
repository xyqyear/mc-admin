package world

import (
	"bytes"
	"compress/zlib"
	"context"
	"encoding/binary"
	"fmt"
	"slices"
	"strings"
	"time"

	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/fixtures"
)

func snapshotQueryResponsiveness(ctx context.Context, t *engine.Scope) error {
	s, err := open(ctx, t)
	if err != nil {
		return err
	}
	if err = s.seedStoppedWorld(); err != nil {
		return err
	}
	mccPath := fixtureRegion + "/c.-1.0.mcc"
	regionPath := fixtureRegion + "/r.-1.0.mca"
	external := make([]byte, 8192+4096)
	binary.BigEndian.PutUint32(external[31*4:], 2<<8|1)
	binary.BigEndian.PutUint32(external[8192:], 1)
	external[8196] = 0x82
	var compressed bytes.Buffer
	w := zlib.NewWriter(&compressed)
	_, _ = w.Write(chunkNBT(-1, 0, 50, "external source"))
	_ = w.Close()
	before := compressed.Bytes()
	if err = s.seed(regionPath, external); err != nil {
		return err
	}
	if err = s.seed(mccPath, before); err != nil {
		return err
	}
	dimension := map[string]any{"type": "dimension", "region_dir_relpath": fixtureRegion}
	full, err := s.snapshot(ctx, dimension)
	if err != nil {
		return err
	}
	if err = s.config(ctx, "snapshots", func(data map[string]any) { data["ignored_paths"] = []string{mccPath} }); err != nil {
		return err
	}
	protected, err := s.snapshot(ctx, dimension)
	if err != nil {
		return err
	}
	if err = s.config(ctx, "snapshots", func(data map[string]any) { data["ignored_paths"] = []string{} }); err != nil {
		return err
	}
	var regions [][2]int
	for x := -32; x < 32; x++ {
		regions = append(regions, [2]int{x, 0})
	}
	selection := map[string]any{"type": "regions", "region_dir_relpath": fixtureRegion, "regions": regions}
	request := s.scopeRequest(selection)
	anonymous, err := fixtures.Session(ctx, t, "")
	if err != nil {
		return err
	}
	if err = anonymous.JSON(ctx, "POST", "/api/snapshots/eligible", request, nil, 401); err != nil {
		return err
	}
	type candidate struct {
		ID      string   `json:"id"`
		Skipped []string `json:"skipped_paths"`
		Count   int      `json:"skipped_count"`
	}
	type response struct {
		Snapshots []candidate `json:"snapshots"`
	}
	queryCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	done := make(chan error, 1)
	var result response
	started := time.Now()
	go func() { done <- s.client.JSON(queryCtx, "POST", "/api/snapshots/eligible", request, &result, 200) }()
	for range 3 {
		readCtx, readCancel := context.WithTimeout(ctx, 2*time.Second)
		err = s.client.JSON(readCtx, "GET", "/api/system/health", nil, nil, 200)
		readCancel()
		if err != nil {
			cancel()
			<-done
			return fmt.Errorf("management read blocked by candidate query: %w", err)
		}
	}
	if err = <-done; err != nil {
		return err
	}
	t.Recorder.Event("snapshot_query_timing", map[string]any{"regions": len(regions), "elapsed_ms": time.Since(started).Milliseconds()})
	if len(result.Snapshots) != 2 {
		return fmt.Errorf("candidate query changed source coverage: %+v", result)
	}
	for _, row := range result.Snapshots {
		if row.ID == full && (row.Count != 0 || len(row.Skipped) != 0) {
			return fmt.Errorf("unprotected source acquired skipped data: %+v", row)
		}
		if row.ID == protected && (row.Count != 1 || len(row.Skipped) != 1 || !strings.HasSuffix(row.Skipped[0], "/"+mccPath)) {
			return fmt.Errorf("historical MCC protection was lost: %+v", row)
		}
	}
	if !slices.ContainsFunc(result.Snapshots, func(row candidate) bool { return row.ID == full }) || !slices.ContainsFunc(result.Snapshots, func(row candidate) bool { return row.ID == protected }) {
		return fmt.Errorf("candidate query returned unrelated sources")
	}
	if content, err := s.download(ctx, mccPath); err != nil || !bytes.Equal(content, before) {
		return fmt.Errorf("candidate query changed external chunk data: %v", err)
	}
	var liveCompressed bytes.Buffer
	liveWriter := zlib.NewWriter(&liveCompressed)
	_, _ = liveWriter.Write(chunkNBT(-1, 0, 80, "external data before recovery"))
	_ = liveWriter.Close()
	live := liveCompressed.Bytes()
	if err = s.seed(mccPath, live); err != nil {
		return err
	}
	selection["regions"] = [][2]int{{-1, 0}, {0, 0}}
	restored, err := s.client.RunTaskResult(ctx, "POST", "/api/snapshots/restorations", s.restoreRequest(full, selection))
	if err != nil {
		return err
	}
	if content, err := s.download(ctx, mccPath); err != nil || !bytes.Equal(content, before) {
		return fmt.Errorf("selected recovery lost external chunk bytes: %v", err)
	}
	if err = s.client.RunTask(ctx, "POST", "/api/snapshots/restorations/"+fmt.Sprint(restored["restoration_id"])+"/rollback", nil, nil); err != nil {
		return err
	}
	if content, err := s.download(ctx, mccPath); err != nil || !bytes.Equal(content, live) {
		return fmt.Errorf("rollback lost pre-recovery external chunk bytes: %v", err)
	}
	return nil
}
