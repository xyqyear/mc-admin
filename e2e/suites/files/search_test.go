package files

import "testing"

func TestSearchOracleChecksFileIdentityAndTotal(t *testing.T) {
	expected := []searchEntry{{"/TOP.txt", "TOP.txt"}, {"/deeper/small.txt", "small.txt"}}
	for _, test := range []struct {
		name       string
		result     searchResponse
		shouldFail bool
	}{
		{"same files reversed", searchResponse{2, []searchEntry{{"/deeper/small.txt", "small.txt"}, {"/TOP.txt", "TOP.txt"}}}, false},
		{"wrong path", searchResponse{2, []searchEntry{{"/wrong/TOP.txt", "TOP.txt"}, {"/deeper/small.txt", "small.txt"}}}, true},
		{"wrong name", searchResponse{2, []searchEntry{{"/TOP.txt", "wrong.txt"}, {"/deeper/small.txt", "small.txt"}}}, true},
		{"duplicate", searchResponse{2, []searchEntry{{"/TOP.txt", "TOP.txt"}, {"/TOP.txt", "TOP.txt"}}}, true},
		{"wrong total", searchResponse{1, []searchEntry{{"/TOP.txt", "TOP.txt"}, {"/deeper/small.txt", "small.txt"}}}, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := checkSearchResults(test.result, expected); (err != nil) != test.shouldFail {
				t.Fatalf("search error = %v, should fail = %v", err, test.shouldFail)
			}
		})
	}
	if err := checkSearchResults(searchResponse{}, nil); err != nil {
		t.Fatal(err)
	}
}
