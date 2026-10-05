package engine

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"math"
	"math/rand/v2"
	"reflect"
	"slices"
	"sort"
)

type Shard struct {
	Index            int      `json:"index"`
	Providers        []string `json:"providers"`
	EstimatedSeconds float64  `json:"estimated_seconds"`
	Cases            []string `json:"cases"`
}
type OversizedGroup struct {
	Key     string  `json:"key"`
	Seconds float64 `json:"seconds"`
	Reason  string  `json:"reason"`
}
type RunPlan struct {
	Version        int              `json:"version"`
	Profile        string           `json:"profile"`
	Revision       string           `json:"revision"`
	Image          string           `json:"image"`
	RunnerSHA256   string           `json:"runner_sha256"`
	HistorySource  json.RawMessage  `json:"history_source,omitempty"`
	Costs          CostProfile      `json:"costs"`
	Seed           uint64           `json:"seed"`
	NoReuse        bool             `json:"no_reuse"`
	Workers        int              `json:"workers"`
	MinecraftSlots int              `json:"minecraft_slots"`
	BudgetSeconds  float64          `json:"budget_seconds"`
	MaxShards      int              `json:"max_shards"`
	Catalog        []Entry          `json:"catalog"`
	Shards         []Shard          `json:"shards"`
	Oversized      []OversizedGroup `json:"oversized"`
	Digest         string           `json:"digest"`
}

func ProfileCases(catalog []Case, profile string) ([]Case, error) {
	if !slices.Contains([]string{"regression", "qualification", "smoke", "mojang", "dnspod"}, profile) {
		return nil, fmt.Errorf("unknown execution profile %q", profile)
	}
	var selected []Case
	cloud := 0
	for _, test := range catalog {
		include := false
		switch profile {
		case "regression", "qualification":
			include = slices.Contains(test.Tags, "regression") && test.Capability == ""
			if profile == "qualification" && test.Capability == "huawei" {
				include = true
				cloud++
			}
		case "dnspod":
			include = test.Capability == "dnspod"
		default:
			include = slices.Contains(test.Tags, profile) && test.Capability == ""
		}
		if include {
			selected = append(selected, test)
		}
	}
	if len(selected) == 0 || (profile == "qualification" && cloud == 0) {
		return nil, fmt.Errorf("profile %s lacks its required current cases", profile)
	}
	return selected, nil
}

func BuildRunPlan(catalog []Case, input RunPlan) (RunPlan, error) {
	p := input
	p.Version = 1
	p.Catalog = nil
	p.Shards = nil
	p.Oversized = nil
	p.Digest = ""
	if p.BudgetSeconds <= 0 || math.IsNaN(p.BudgetSeconds) || math.IsInf(p.BudgetSeconds, 0) || p.MaxShards < 1 || p.MaxShards > 64 {
		return p, fmt.Errorf("invalid automatic planning limits")
	}
	selected, err := ProfileCases(catalog, p.Profile)
	if err != nil {
		return p, err
	}
	profile, _, err := scheduling(Selection{Costs: p.Costs, Workers: p.Workers, MinecraftSlots: p.MinecraftSlots})
	if err != nil {
		return p, err
	}
	p.Costs = profile
	base, err := BuildPlan(selected, Selection{ShardIndex: 1, ShardCount: 1, Seed: p.Seed, Costs: p.Costs, Workers: p.Workers, MinecraftSlots: p.MinecraftSlots, NoReuse: p.NoReuse})
	if err != nil {
		return p, err
	}
	p.Workers = base.Scheduling.Workers
	p.MinecraftSlots = base.Scheduling.MinecraftSlots
	p.Catalog = base.Catalog
	var units []weightedUnit
	if p.Costs.ShardOverheadSeconds >= p.BudgetSeconds {
		p.Oversized = append(p.Oversized, OversizedGroup{"fixed-overhead", p.Costs.ShardOverheadSeconds, "fixed execution cleanup overhead exceeds target; extra shards cannot satisfy it"})
	}
	for _, group := range base.Groups {
		unit := weightedUnit{key: group.Key, slots: group.Cases[0].Recipe.MinecraftSlots, seconds: p.Costs.groupEstimate(group)}
		for _, test := range group.Cases {
			if test.Capability != "" {
				unit.providers = append(unit.providers, test.Capability)
			}
			unit.ids = append(unit.ids, test.ID)
		}
		if unit.slots > p.MinecraftSlots {
			return p, fmt.Errorf("group %s exceeds Minecraft slot capacity", unit.key)
		}
		if unit.seconds > p.BudgetSeconds || (p.Costs.ShardOverheadSeconds < p.BudgetSeconds && unit.seconds+p.Costs.ShardOverheadSeconds > p.BudgetSeconds) {
			p.Oversized = append(p.Oversized, OversizedGroup{unit.key, unit.seconds + p.Costs.ShardOverheadSeconds, "indivisible lifecycle group plus fixed runner overhead exceeds execution target"})
		}
		units = append(units, unit)
	}
	var bins [][]weightedUnit
	if p.Costs.ShardOverheadSeconds >= p.BudgetSeconds {
		bins = [][]weightedUnit{units}
	} else {
		bins, err = allocateUnits(units, p.Workers, p.MinecraftSlots, p.BudgetSeconds-p.Costs.ShardOverheadSeconds, p.MaxShards)
		if err != nil {
			return p, err
		}
	}
	assigned := map[string]int{}
	for _, bin := range bins {
		shard := Shard{Index: len(p.Shards) + 1, Providers: []string{}, EstimatedSeconds: p.Costs.ShardOverheadSeconds + predictUnits(bin, p.Workers, p.MinecraftSlots), Cases: []string{}}
		if shard.EstimatedSeconds > p.BudgetSeconds && len(bin) > 1 && p.Costs.ShardOverheadSeconds < p.BudgetSeconds {
			p.Oversized = append(p.Oversized, OversizedGroup{fmt.Sprintf("shard:%d", shard.Index), shard.EstimatedSeconds, "shard_limit: maximum shard count retains all indivisible lifecycle groups"})
		}
		for _, unit := range bin {
			shard.Providers = append(shard.Providers, unit.providers...)
			for _, id := range unit.ids {
				shard.Cases = append(shard.Cases, id)
				assigned[id] = shard.Index
			}
		}
		sort.Strings(shard.Providers)
		shard.Providers = slices.Compact(shard.Providers)
		sort.Strings(shard.Cases)
		p.Shards = append(p.Shards, shard)
	}
	for i := range p.Catalog {
		p.Catalog[i].Shard = assigned[p.Catalog[i].ID]
	}
	p.Digest, err = p.identity()
	return p, err
}

func (p RunPlan) identity() (string, error) {
	p.Digest = ""
	data, err := json.Marshal(p)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%x", sha256.Sum256(data)), nil
}
func (p RunPlan) Validate(catalog []Case, requiredProfile string) error {
	if p.Version != 1 || p.Profile != requiredProfile {
		return fmt.Errorf("plan profile does not satisfy requested qualification")
	}
	digest, err := p.identity()
	if err != nil || digest != p.Digest {
		return fmt.Errorf("immutable plan digest mismatch")
	}
	rebuilt, err := BuildRunPlan(catalog, p)
	if err != nil {
		return err
	}
	if !reflect.DeepEqual(p, rebuilt) {
		return fmt.Errorf("plan differs from current required catalog or assignments")
	}
	return nil
}

func (p RunPlan) Execution(catalog []Case, index int, requiredProfile string) (Plan, error) {
	if err := p.Validate(catalog, requiredProfile); err != nil {
		return Plan{}, err
	}
	if index < 1 || index > len(p.Shards) {
		return Plan{}, fmt.Errorf("shard index is outside immutable plan")
	}
	_, config, err := scheduling(Selection{Costs: p.Costs, Workers: p.Workers, MinecraftSlots: p.MinecraftSlots})
	if err != nil {
		return Plan{}, err
	}
	plan := Plan{Digest: p.Digest, Seed: p.Seed, ShardIndex: index, ShardCount: len(p.Shards), Catalog: p.Catalog, Order: []string{}, Scheduling: config}
	selected, err := ProfileCases(catalog, requiredProfile)
	if err != nil {
		return plan, err
	}
	byID := map[string]Case{}
	for _, test := range selected {
		byID[test.ID] = test
	}
	groups := map[string][]Case{}
	for _, entry := range p.Catalog {
		if entry.Shard != index {
			continue
		}
		test := byID[entry.ID]
		key := "recipe:" + test.Recipe.ID
		if test.Isolation == Fresh || p.NoReuse {
			key = "case:" + test.ID
		}
		groups[key] = append(groups[key], test)
	}
	var keys []string
	for key := range groups {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	random := rand.New(rand.NewPCG(p.Seed, p.Seed^0x9e3779b97f4a7c15))
	if p.Seed != 0 {
		random.Shuffle(len(keys), func(i, j int) { keys[i], keys[j] = keys[j], keys[i] })
	}
	for _, key := range keys {
		tests := groups[key]
		if p.Seed != 0 {
			random.Shuffle(len(tests), func(i, j int) { tests[i], tests[j] = tests[j], tests[i] })
		}
		plan.Groups = append(plan.Groups, Group{Key: key, Cases: tests})
		for _, test := range tests {
			plan.Order = append(plan.Order, test.ID)
		}
	}
	return plan, nil
}

type weightedUnit struct {
	key       string
	seconds   float64
	slots     int
	ids       []string
	providers []string
}

func predictUnits(units []weightedUnit, workers, slots int) float64 {
	pending := slices.Clone(units)
	sort.Slice(pending, func(i, j int) bool {
		if pending[i].seconds == pending[j].seconds {
			return pending[i].key < pending[j].key
		}
		return pending[i].seconds > pending[j].seconds
	})
	type activeUnit struct {
		end   float64
		slots int
	}
	var active []activeUnit
	now := 0.0
	occupied := 0
	for len(pending) > 0 || len(active) > 0 {
		for len(active) < workers {
			eligible := -1
			for i, unit := range pending {
				if occupied+unit.slots <= slots {
					eligible = i
					break
				}
			}
			if eligible < 0 {
				break
			}
			unit := pending[eligible]
			pending = append(pending[:eligible], pending[eligible+1:]...)
			active = append(active, activeUnit{now + unit.seconds, unit.slots})
			occupied += unit.slots
		}
		if len(active) == 0 {
			return math.Inf(1)
		}
		next := active[0].end
		for _, unit := range active {
			next = min(next, unit.end)
		}
		now = next
		retained := active[:0]
		for _, unit := range active {
			if unit.end <= now {
				occupied -= unit.slots
			} else {
				retained = append(retained, unit)
			}
		}
		active = retained
	}
	return now
}

func allocateUnits(units []weightedUnit, workers, slots int, budget float64, maximum int) ([][]weightedUnit, error) {
	sort.Slice(units, func(i, j int) bool {
		if units[i].seconds == units[j].seconds {
			return units[i].key < units[j].key
		}
		return units[i].seconds > units[j].seconds
	})
	var oversized, normal []weightedUnit
	total, mc := 0.0, 0.0
	for _, unit := range units {
		if unit.seconds > budget {
			oversized = append(oversized, unit)
		} else {
			normal = append(normal, unit)
			total += unit.seconds
			mc += unit.seconds * float64(unit.slots)
		}
	}
	minimum := len(oversized)
	if len(normal) > 0 {
		minimum++
	}
	if maximum < 1 {
		return nil, fmt.Errorf("maximum shard count must be positive")
	}
	if maximum < minimum {
		bins := make([][]weightedUnit, maximum)
		for _, unit := range units {
			best := 0
			for i := 1; i < len(bins); i++ {
				if predictUnits(bins[i], workers, slots) < predictUnits(bins[best], workers, slots) {
					best = i
				}
			}
			bins[best] = append(bins[best], unit)
		}
		return bins, nil
	}
	var fixed [][]weightedUnit
	for _, unit := range oversized {
		fixed = append(fixed, []weightedUnit{unit})
	}
	if len(normal) == 0 {
		return fixed, nil
	}
	limit := min(maximum-len(fixed), len(normal))
	start := min(limit, max(1, int(math.Ceil(max(total/float64(workers), mc/float64(slots))/budget))))
	for count := start; count <= limit; count++ {
		bins := make([][]weightedUnit, count)
		for _, unit := range normal {
			best := -1
			score := math.Inf(1)
			for i := range bins {
				predicted := predictUnits(append(slices.Clone(bins[i]), unit), workers, slots)
				if predicted < score || (predicted == score && best >= 0 && len(bins[i]) < len(bins[best])) {
					best = i
					score = predicted
				}
			}
			bins[best] = append(bins[best], unit)
		}
		fits := true
		for _, bin := range bins {
			if predictUnits(bin, workers, slots) > budget {
				fits = false
			}
		}
		if fits || count == limit {
			for _, bin := range bins {
				if len(bin) > 0 {
					fixed = append(fixed, bin)
				}
			}
			return fixed, nil
		}
	}
	return nil, fmt.Errorf("automatic planning produced no shards")
}
