package platform

import (
	"context"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type PortLease struct {
	Ports []int
	locks []*Lock
}

func (p *PortLease) Close() error {
	for _, lock := range p.locks {
		if err := lock.Close(); err != nil {
			return err
		}
	}
	p.locks = nil
	return nil
}

func LeasePorts(ctx context.Context, docker Docker, dir string, count int) (*PortLease, error) {
	if err := os.MkdirAll(dir, 0700); err != nil {
		return nil, err
	}
	output, err := docker.Run(ctx, "ps", "-a", "--format", "{{.Ports}}")
	if err != nil {
		return nil, err
	}
	lease := &PortLease{}
	start := 0
	for _, b := range ID() {
		start += int(b)
	}
	for i := 0; i < 20000 && len(lease.Ports) < count; i++ {
		if err := ctx.Err(); err != nil {
			lease.Close()
			return nil, err
		}
		port := 20000 + (start+i)%20000
		if strings.Contains(output, ":"+strconv.Itoa(port)+"->") {
			continue
		}
		lock, err := TryLock(filepath.Join(dir, strconv.Itoa(port)+".lock"))
		if err != nil {
			continue
		}
		listener, err := net.Listen("tcp4", fmt.Sprintf("0.0.0.0:%d", port))
		if err != nil {
			lock.Close()
			continue
		}
		listener.Close()
		lease.Ports = append(lease.Ports, port)
		lease.locks = append(lease.locks, lock)
	}
	if len(lease.Ports) != count {
		lease.Close()
		return nil, fmt.Errorf("cannot lease %d host ports", count)
	}
	return lease, nil
}
