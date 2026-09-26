package suites

import (
	_ "embed"
	"encoding/json"

	"mc-admin/e2e/internal/engine"
)

//go:embed costs.json
var costData []byte

func Costs() (engine.CostProfile, error) {
	var profile engine.CostProfile
	err := json.Unmarshal(costData, &profile)
	return profile, err
}
