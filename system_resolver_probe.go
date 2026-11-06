package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"runtime"
	"sort"
	"strings"
	"time"
)

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--version" {
		json.NewEncoder(os.Stdout).Encode(map[string]string{"go_version": runtime.Version(), "resolver": "net.DefaultResolver; CGO_ENABLED=0"})
		return
	}
	if len(os.Args) != 3 {
		os.Exit(2)
	}
	name, kind := os.Args[1], os.Args[2]
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	var answers []string
	var err error
	switch kind {
	case "A":
		var addresses []net.IP
		addresses, err = net.DefaultResolver.LookupIP(ctx, "ip4", name)
		for _, address := range addresses {
			answers = append(answers, address.String())
		}
	case "SRV":
		var records []*net.SRV
		_, records, err = net.DefaultResolver.LookupSRV(ctx, "minecraft", "tcp", strings.TrimPrefix(name, "_minecraft._tcp."))
		for _, record := range records {
			answers = append(answers, fmt.Sprintf("%d %d %d %s", record.Priority, record.Weight, record.Port, record.Target))
		}
	default:
		os.Exit(2)
	}
	sort.Strings(answers)
	result := map[string]any{"answers": answers}
	if err != nil {
		var dnsError *net.DNSError
		if errors.As(err, &dnsError) {
			result["error_type"] = "DNSError"
			result["not_found"] = dnsError.IsNotFound
			result["timed_out"] = dnsError.IsTimeout
			result["temporary"] = dnsError.IsTemporary
			result["dns_server"] = dnsError.Server
		} else {
			result["error_type"] = fmt.Sprintf("%T", err)
		}
	}
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		os.Exit(2)
	}
}
