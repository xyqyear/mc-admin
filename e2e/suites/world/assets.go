package world

import (
	"bytes"
	"compress/gzip"
	"compress/zlib"
	"context"
	"encoding/binary"
	"fmt"
	"math"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"mc-admin/e2e/internal/fixtures"
)

const fixtureRegion = "world/dimensions/e2e/testing/region"
const teamID = "11111111-1111-4111-8111-111111111111"
const playerID = "22222222-2222-4222-8222-222222222222"

// Binary fixtures implement the public Minecraft NBT/Anvil formats independently of the application.
type nbt bytes.Buffer

func (b *nbt) raw(data []byte)  { (*bytes.Buffer)(b).Write(data) }
func (b *nbt) number(value any) { _ = binary.Write((*bytes.Buffer)(b), binary.BigEndian, value) }
func (b *nbt) name(kind byte, name string) {
	b.raw([]byte{kind})
	b.number(uint16(len(name)))
	b.raw([]byte(name))
}
func (b *nbt) text(name, value string) {
	b.name(8, name)
	b.number(uint16(len(value)))
	b.raw([]byte(value))
}
func (b *nbt) integer(name string, value int32) { b.name(3, name); b.number(value) }
func (b *nbt) long(name string, value int64)    { b.name(4, name); b.number(value) }
func (b *nbt) data() []byte                     { return (*bytes.Buffer)(b).Bytes() }

func playerNBT(dimension string) []byte {
	var b nbt
	b.name(10, "")
	b.integer("DataVersion", 4671)
	b.text("Dimension", dimension)
	b.name(9, "Pos")
	b.raw([]byte{6})
	b.number(int32(3))
	for _, value := range []float64{24.5, 65, -8.25} {
		b.number(math.Float64bits(value))
	}
	b.raw([]byte{0})
	var out bytes.Buffer
	w := gzip.NewWriter(&out)
	_, _ = w.Write(b.data())
	_ = w.Close()
	return out.Bytes()
}

func chunkNBT(x, z int32, inhabited int64, marker string) []byte {
	var b nbt
	b.name(10, "")
	b.integer("DataVersion", 4671)
	b.integer("xPos", x)
	b.integer("zPos", z)
	b.long("InhabitedTime", inhabited)
	b.text("Status", "minecraft:full")
	b.text("e2e_marker", marker)
	b.name(9, "sections")
	b.raw([]byte{10})
	b.number(int32(0))
	b.raw([]byte{0})
	return b.data()
}

func regionData(markers [2]string) []byte {
	result := make([]byte, 8192)
	for x, marker := range markers {
		var compressed bytes.Buffer
		w := zlib.NewWriter(&compressed)
		_, _ = w.Write(chunkNBT(int32(x), 0, 0, marker))
		_ = w.Close()
		payload := compressed.Bytes()
		sectors := (len(payload) + 5 + 4095) / 4096
		offset := len(result) / 4096
		binary.BigEndian.PutUint32(result[x*4:], uint32(offset<<8|sectors))
		binary.BigEndian.PutUint32(result[4096+x*4:], 1700000000)
		block := make([]byte, sectors*4096)
		binary.BigEndian.PutUint32(block, uint32(len(payload)+1))
		block[4] = 2
		copy(block[5:], payload)
		result = append(result, block...)
	}
	return result
}

func chunkPayload(region []byte, x int) ([]byte, error) {
	if len(region) < 8192 {
		return nil, fmt.Errorf("truncated Anvil header")
	}
	loc := binary.BigEndian.Uint32(region[x*4:])
	offset := int(loc>>8) * 4096
	if offset == 0 {
		return nil, nil
	}
	if offset+5 > len(region) {
		return nil, fmt.Errorf("Anvil offset outside file")
	}
	size := int(binary.BigEndian.Uint32(region[offset:]))
	if size < 1 || offset+4+size > len(region) {
		return nil, fmt.Errorf("Anvil chunk outside file")
	}
	return region[offset+4 : offset+4+size], nil
}

func (s *scenario) seed(relative string, data []byte) error {
	if filepath.IsAbs(relative) || strings.Contains(relative, "..") {
		return fmt.Errorf("unsafe fixture path %q", relative)
	}
	file := filepath.Join(s.t.Env.Dir, "servers", s.id, "data", filepath.FromSlash(relative))
	if err := os.MkdirAll(filepath.Dir(file), 0755); err != nil {
		return err
	}
	if err := os.WriteFile(file, data, 0644); err != nil {
		return err
	}
	s.t.Recorder.Event("fixture_file", map[string]any{"path": relative, "bytes": len(data)})
	return nil
}

func (s *scenario) download(ctx context.Context, relative string) ([]byte, error) {
	response, err := s.client.Do(ctx, "GET", s.base+"/files/download?path="+url.QueryEscape("/"+relative), nil, nil)
	if err != nil {
		return nil, err
	}
	if err = s.client.Expect(response, 200); err != nil {
		return nil, err
	}
	return response.Body, nil
}

func (s *scenario) seedRegion(markers [2]string) error {
	return s.seed(fixtureRegion+"/r.0.0.mca", regionData(markers))
}

func (s *scenario) claims() error {
	if err := s.seed("world/ftbchunks/"+teamID+".snbt", []byte(`{chunks: {"e2e:testing": [{x: 0, z: 0, force_loaded: 1b}]}}`)); err != nil {
		return err
	}
	return s.seed("world/ftbteams/party/"+teamID+".snbt", []byte(`{type: "party", properties: {"ftbteams:display_name": "E2E builders"}}`))
}

func (s *scenario) checkChunk(ctx context.Context, x int, expected []byte) error {
	return s.checkChunkAt(ctx, fixtureRegion+"/r.0.0.mca", x, expected)
}

func (s *scenario) checkChunkAt(ctx context.Context, relative string, x int, expected []byte) error {
	data, err := s.download(ctx, relative)
	if err != nil {
		return err
	}
	actual, err := chunkPayload(data, x)
	if err != nil {
		return err
	}
	if !bytes.Equal(actual, expected) {
		return fmt.Errorf("%s chunk %d content differs (actual=%d bytes expected=%d)", relative, x, len(actual), len(expected))
	}
	return nil
}

func (s *scenario) createMarker(ctx context.Context, relative, content string) error {
	return fixtures.CreateFile(ctx, s.client, s.id, "/"+relative, content)
}
