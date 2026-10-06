package archive

import (
	"crypto/sha256"
	"fmt"
	"strings"
)

func compressionWorkload(seed string) string {
	var data strings.Builder
	for n := 0; n < 260000; n++ {
		sum := sha256.Sum256([]byte(fmt.Sprintf("%s-%d", seed, n)))
		fmt.Fprintf(&data, "%x", sum)
	}
	return data.String()
}
