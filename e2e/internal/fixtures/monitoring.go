package fixtures

import (
	"context"
	"fmt"
	"math"
	"time"

	"mc-admin/e2e/internal/api"
)

type Sample[T any] struct {
	Value     *T         `json:"value"`
	Quality   string     `json:"quality"`
	SampledAt *time.Time `json:"sampled_at"`
	Error     *string    `json:"error"`
}

func (s Sample[T]) Ready() bool { return s.Quality == "ready" && s.Value != nil && s.SampledAt != nil }

type MemoryUsage struct {
	Used  int64 `json:"used"`
	Total int64 `json:"total"`
}

type DiskUsage struct {
	Used      int64 `json:"used"`
	Total     int64 `json:"total"`
	Available int64 `json:"available"`
}

type ByteCounters struct {
	Read  int64 `json:"read"`
	Write int64 `json:"write"`
}

type Maintenance struct {
	Active      bool    `json:"active"`
	Kind        *string `json:"kind"`
	Description *string `json:"description"`
	TaskID      *string `json:"task_id"`
}

type ServerSamples struct {
	Generation  int64                `json:"generation"`
	Incarnation *string              `json:"incarnation"`
	Status      Sample[string]       `json:"status"`
	CPU         Sample[float64]      `json:"cpu_percent"`
	Memory      Sample[int64]        `json:"memory_bytes"`
	DiskIO      Sample[ByteCounters] `json:"disk_io"`
	NetworkIO   Sample[ByteCounters] `json:"network_io"`
	Disk        Sample[DiskUsage]    `json:"disk"`
	Maintenance Maintenance          `json:"maintenance"`
}

type MonitoringSnapshot struct {
	System struct {
		CPU    Sample[float64]     `json:"cpu_percent"`
		Memory Sample[MemoryUsage] `json:"memory"`
		Load   Sample[[]float64]   `json:"load"`
		Disk   Sample[DiskUsage]   `json:"disk"`
	} `json:"system"`
	Servers map[string]ServerSamples `json:"servers"`
}

func Monitoring(ctx context.Context, client *api.Client) (MonitoringSnapshot, error) {
	var snapshot MonitoringSnapshot
	err := client.JSON(ctx, "GET", "/api/monitoring", nil, &snapshot, 200)
	return snapshot, err
}

func ServerMonitoring(ctx context.Context, client *api.Client, id string) (ServerSamples, error) {
	snapshot, err := Monitoring(ctx, client)
	if err != nil {
		return ServerSamples{}, err
	}
	value, ok := snapshot.Servers[id]
	if !ok {
		return ServerSamples{}, fmt.Errorf("monitoring omitted registered server %s", id)
	}
	return value, nil
}

func ServerMaintenance(ctx context.Context, client *api.Client, id string) (Maintenance, error) {
	server, err := ServerMonitoring(ctx, client, id)
	return server.Maintenance, err
}

func WaitServerMetrics(ctx context.Context, client *api.Client, id string) (ServerSamples, error) {
	var sample ServerSamples
	err := api.Wait(ctx, 100*time.Millisecond, "running server metrics", func(ctx context.Context) (bool, error) {
		var err error
		sample, err = ServerMonitoring(ctx, client, id)
		if err != nil {
			return false, api.Permanent(err)
		}
		if !sample.CPU.Ready() || !sample.Memory.Ready() || !sample.DiskIO.Ready() || !sample.NetworkIO.Ready() || !sample.Disk.Ready() {
			return false, nil
		}
		if math.IsNaN(*sample.CPU.Value) || math.IsInf(*sample.CPU.Value, 0) || *sample.CPU.Value < 0 || *sample.Memory.Value <= 0 {
			return false, api.Permanent(fmt.Errorf("invalid running CPU/memory sample"))
		}
		for _, value := range []int64{sample.DiskIO.Value.Read, sample.DiskIO.Value.Write, sample.NetworkIO.Value.Read, sample.NetworkIO.Value.Write, sample.Disk.Value.Used, sample.Disk.Value.Available} {
			if value < 0 {
				return false, api.Permanent(fmt.Errorf("negative byte counter"))
			}
		}
		if sample.Disk.Value.Total <= 0 || sample.Disk.Value.Available > sample.Disk.Value.Total {
			return false, api.Permanent(fmt.Errorf("invalid filesystem capacity"))
		}
		return true, nil
	})
	return sample, err
}
