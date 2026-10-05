package engine

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"math"
	"sort"
)

type CostProfile struct {
	Groups               map[string]GroupCost `json:"groups,omitempty"`
	ShardOverheadSeconds float64              `json:"shard_overhead_seconds,omitempty"`
	Version              int                  `json:"version"`
	Sources              []string             `json:"sources"`
	Measurement          string               `json:"measurement"`
	DefaultSeconds       float64              `json:"default_seconds"`
	Recipes              map[string]float64   `json:"recipes"`
	Cases                map[string]float64   `json:"cases"`
}

type GroupCost struct {
	Seconds float64  `json:"seconds"`
	Members []string `json:"members"`
}

type Scheduling struct {
	Algorithm      string `json:"algorithm"`
	CostSHA256     string `json:"cost_sha256"`
	Workers        int    `json:"workers"`
	MinecraftSlots int    `json:"minecraft_slots"`
}

func (p CostProfile) Validate() error { return p.validate() }

func (p CostProfile) validate() error {
	valid := func(value float64) bool { return value > 0 && !math.IsNaN(value) && !math.IsInf(value, 0) }
	if p.Version != 1 || !valid(p.DefaultSeconds) {
		return fmt.Errorf("cost profile requires version 1 and a positive finite default")
	}
	if p.ShardOverheadSeconds < 0 || math.IsNaN(p.ShardOverheadSeconds) || math.IsInf(p.ShardOverheadSeconds, 0) {
		return fmt.Errorf("invalid fixed shard lifecycle overhead")
	}
	for _, costs := range []map[string]float64{p.Recipes, p.Cases} {
		for key, value := range costs {
			if key == "" || !valid(value) {
				return fmt.Errorf("invalid scheduling cost for %q", key)
			}
		}
	}
	for key, group := range p.Groups {
		if key == "" || !valid(group.Seconds) || len(group.Members) == 0 {
			return fmt.Errorf("invalid historical group lifecycle cost")
		}
		members := map[string]bool{}
		for _, id := range group.Members {
			if id == "" || members[id] {
				return fmt.Errorf("invalid historical group membership")
			}
			members[id] = true
		}
	}
	return nil
}

func (p CostProfile) groupEstimate(group Group) float64 {
	historical, exists := p.Groups[group.Key]
	known, added := 0.0, 0.0
	members := map[string]bool{}
	for _, id := range historical.Members {
		members[id] = true
	}
	for _, test := range group.Cases {
		if !exists || members[test.ID] {
			known += p.estimate(test)
		} else {
			added += p.estimate(test)
		}
	}
	return max(known, historical.Seconds) + added
}

func (p CostProfile) estimate(test Case) float64 {
	if seconds := p.Cases[test.ID]; seconds > 0 {
		return seconds
	}
	if seconds := p.Recipes[test.Recipe.ID]; seconds > 0 {
		return seconds
	}
	return p.DefaultSeconds
}

func scheduling(selection Selection) (CostProfile, Scheduling, error) {
	profile := selection.Costs
	if profile.Version == 0 {
		profile = CostProfile{Version: 1, DefaultSeconds: 30}
	}
	if err := profile.validate(); err != nil {
		return profile, Scheduling{}, err
	}
	workers, slots := selection.Workers, selection.MinecraftSlots
	if workers == 0 {
		workers = 2
	}
	if slots == 0 {
		slots = 1
	}
	if workers < 1 || slots < 1 {
		return profile, Scheduling{}, fmt.Errorf("scheduling resource budgets must be positive")
	}
	encoded, err := json.Marshal(profile)
	if err != nil {
		return profile, Scheduling{}, err
	}
	return profile, Scheduling{Algorithm: "resource-weighted-v1", CostSHA256: fmt.Sprintf("%x", sha256.Sum256(encoded)), Workers: workers, MinecraftSlots: slots}, nil
}

func assignGroups(groups map[string][]Case, profile CostProfile, config Scheduling, count int) map[string]int {
	type weightedGroup struct {
		key   string
		work  float64
		slots int
	}
	var weighted []weightedGroup
	for key, tests := range groups {
		group := weightedGroup{key: key, slots: tests[0].Recipe.MinecraftSlots}
		for _, test := range tests {
			group.work += profile.estimate(test)
		}
		weighted = append(weighted, group)
	}
	sort.Slice(weighted, func(i, j int) bool {
		a, b := weighted[i], weighted[j]
		if (a.slots > 0) != (b.slots > 0) {
			return a.slots > 0
		}
		if a.work != b.work {
			return a.work > b.work
		}
		return a.key < b.key
	})
	type load struct{ work, minecraft float64 }
	loads := make([]load, count)
	assignments := make(map[string]int, len(weighted))
	for _, group := range weighted {
		best := 0
		var bestScore, bestMinecraft, bestWork float64
		for shard, current := range loads {
			work := current.work + group.work
			minecraft := current.minecraft + group.work*float64(group.slots)
			score := max(work/float64(config.Workers), minecraft/float64(config.MinecraftSlots))
			if shard == 0 || score < bestScore || score == bestScore && (minecraft < bestMinecraft || minecraft == bestMinecraft && work < bestWork) {
				best, bestScore, bestMinecraft, bestWork = shard, score, minecraft, work
			}
		}
		loads[best] = load{work: bestWork, minecraft: bestMinecraft}
		assignments[group.key] = best + 1
	}
	return assignments
}
