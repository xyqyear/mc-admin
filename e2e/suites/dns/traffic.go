package dns

import (
	"bufio"
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"strings"
	"time"

	"mc-admin/e2e/internal/api"
	"mc-admin/e2e/internal/engine"
	"mc-admin/e2e/internal/environment"
	"mc-admin/e2e/internal/fixtures"
)

func minecraftStatus(ctx context.Context, address, hostname string, port int) (string, error) {
	probe, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	conn, err := (&net.Dialer{}).DialContext(probe, "tcp", address)
	if err != nil {
		return "", err
	}
	defer conn.Close()
	deadline, _ := probe.Deadline()
	if err = conn.SetDeadline(deadline); err != nil {
		return "", err
	}
	stop := context.AfterFunc(probe, func() { conn.Close() })
	defer stop()
	var packet bytes.Buffer
	writeVarInt := func(value uint32) {
		for value >= 128 {
			packet.WriteByte(byte(value&127) | 128)
			value >>= 7
		}
		packet.WriteByte(byte(value))
	}
	writeVarInt(0)
	writeVarInt(0xffffffff)
	writeVarInt(uint32(len(hostname)))
	packet.WriteString(hostname)
	packet.WriteByte(byte(port >> 8))
	packet.WriteByte(byte(port))
	writeVarInt(1)
	var header [5]byte
	n := binary.PutUvarint(header[:], uint64(packet.Len()))
	if _, err = io.Copy(conn, io.MultiReader(bytes.NewReader(header[:n]), &packet, bytes.NewReader([]byte{1, 0}))); err != nil {
		return "", err
	}
	reader := bufio.NewReader(conn)
	size, err := binary.ReadUvarint(reader)
	if err != nil {
		return "", err
	}
	if size == 0 || size > 1<<20 {
		return "", fmt.Errorf("invalid Minecraft status frame size %d", size)
	}
	body := make([]byte, int(size))
	if _, err = io.ReadFull(reader, body); err != nil {
		return "", err
	}
	payload := bytes.NewReader(body)
	id, err := binary.ReadUvarint(payload)
	if err != nil || id != 0 {
		return "", fmt.Errorf("invalid Minecraft status packet")
	}
	length, err := binary.ReadUvarint(payload)
	if err != nil || length != uint64(payload.Len()) {
		return "", fmt.Errorf("invalid Minecraft status JSON length")
	}
	data, err := io.ReadAll(payload)
	if err != nil {
		return "", err
	}
	var response struct {
		Description json.RawMessage `json:"description"`
		Version     json.RawMessage `json:"version"`
	}
	if err = json.Unmarshal(data, &response); err != nil {
		return "", err
	}
	if len(response.Description) == 0 || len(response.Version) == 0 {
		return "", fmt.Errorf("incomplete Minecraft status response")
	}
	return string(response.Description), nil
}

func startTrafficServer(ctx context.Context, t *engine.Scope, client *api.Client) (string, error) {
	server := fixtures.ServerOf(t.Env)
	motd := "mc-admin-dns-" + t.Env.ID
	compose := strings.Replace(server.Compose, "      EULA: 'true'", "      EULA: 'true'\n      MOTD: '"+motd+"'", 1)
	var task struct {
		ID string `json:"task_id"`
	}
	if err := client.JSON(ctx, "POST", "/api/servers/"+server.ID+"/compose", map[string]string{"yaml_content": compose}, &task, 200); err != nil {
		return "", err
	}
	if _, err := client.Task(ctx, task.ID); err != nil {
		return "", err
	}
	server.Compose = compose
	if err := fixtures.Operation(ctx, client, server.ID, "up"); err != nil {
		return "", err
	}
	if err := fixtures.WaitStatus(ctx, client, server.ID, "healthy"); err != nil {
		return "", err
	}
	server.Running = true
	return motd, nil
}

func assertTraffic(ctx context.Context, t *engine.Scope, address, hostname, motd string, port int) error {
	response, err := minecraftStatus(ctx, address, hostname, port)
	if err != nil {
		return fmt.Errorf("Minecraft route %s: %w", hostname, err)
	}
	if !strings.Contains(response, motd) {
		return fmt.Errorf("route %s reached the wrong Minecraft server: %s", hostname, response)
	}
	t.Recorder.Event("minecraft_route", map[string]any{"hostname": hostname, "address": address, "motd": response})
	return nil
}

func routerTraffic(ctx context.Context, t *engine.Scope) error {
	client, err := fixtures.Session(ctx, t, "owner")
	if err != nil {
		return err
	}
	if err = startRouter(ctx, t); err != nil {
		return err
	}
	motd, err := startTrafficServer(ctx, t, client)
	if err != nil {
		return err
	}
	port := environment.Get[[]int](t.Env, "ports")[4]
	host := fixtures.ServerOf(t.Env).ID + ".primary.mc.e2e.invalid"
	configuration := map[string]any{"enabled": true, "dns": map[string]any{"type": "huawei", "domain": "e2e.invalid", "ak": "synthetic-ak", "sk": "synthetic-sk", "region": "e2e-invalid-region"}, "managed_sub_domain": "mc", "mc_router_base_url": routerEndpoint(t), "addresses": []any{map[string]any{"type": "manual", "name": "primary", "record_type": "A", "value": "127.0.0.1", "port": port}}}
	if err = client.JSON(ctx, "PUT", "/api/config/modules/dns", map[string]any{"config_data": configuration}, nil, 200); err != nil {
		return err
	}
	return t.Step("unavailable cloud does not prevent real Minecraft routing and drift repair", func() error {
		if err := safeFailedUpdate(ctx, client); err != nil {
			return err
		}
		address := fmt.Sprintf("127.0.0.1:%d", port)
		if err := assertTraffic(ctx, t, address, host, motd, port); err != nil {
			return err
		}
		if response, err := minecraftStatus(ctx, address, "unknown.mc.e2e.invalid", port); err == nil {
			return fmt.Errorf("unknown hostname was routed: %s", response)
		}
		if _, err := routerRequest(ctx, t, "POST", "/routes", map[string]string{"serverAddress": host, "backend": "localhost:1"}); err != nil {
			return err
		}
		if err := safeFailedUpdate(ctx, client); err != nil {
			return err
		}
		return assertTraffic(ctx, t, address, host, motd, port)
	})
}
