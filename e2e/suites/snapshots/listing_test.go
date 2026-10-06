package snapshots

import "testing"

func TestSnapshotListingOracleRequiresExactIdentities(t *testing.T) {
	for _, test := range []struct {
		name       string
		actual     []string
		shouldFail bool
	}{
		{"same identities reversed", []string{"server", "paths"}, false},
		{"wrong identity", []string{"global", "paths"}, true},
		{"duplicate identity", []string{"paths", "paths"}, true},
		{"missing identity", []string{"paths"}, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := checkSnapshotIDs(test.actual, []string{"paths", "server"}); (err != nil) != test.shouldFail {
				t.Fatalf("listing error = %v, should fail = %v", err, test.shouldFail)
			}
		})
	}
}
