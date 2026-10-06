package archive

import "testing"

func TestCompressionWorkloadKeepsExistingSizeAndSeeds(t *testing.T) {
	for _, test := range []struct{ seed, first, last string }{
		{"e2e-archive", "37fd839236a97eddd02b08099883f4eea4a6217343f7fcfbad81f122b180171e", "6ef8e50e2af9a97c3ee01691f16de852da5ade8da8e3ccc315fea1dee5de2190"},
		{"task-permissions", "24a4da94576339b729ff71bbda4f064632fb120122b8c0f1da9432c7e0660351", "ac6497b4e795c529c1e4c82070d5065e23b1c755edbd4c5cafb93fb531daaacb"},
	} {
		data := compressionWorkload(test.seed)
		if len(data) != 16640000 || data[:64] != test.first || data[len(data)-64:] != test.last {
			t.Fatalf("%s workload size or seed changed", test.seed)
		}
	}
}
