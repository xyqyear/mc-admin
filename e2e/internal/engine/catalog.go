package engine

import (
	"context"
	"fmt"
	"math/rand/v2"
	"regexp"
	"sort"
	"time"

	"mc-admin/e2e/internal/environment"
)

type Isolation string

const (
	Fresh        Isolation = "fresh"
	CleanReuse   Isolation = "clean-reuse"
	ObserveReuse Isolation = "observe-reuse"
)

type Case struct {
	ID        string
	Suite     string
	Tags      []string
	Recipe    *environment.Recipe
	Isolation Isolation
	Timeout   time.Duration
	Run       func(context.Context, *Scope) error
}

type Selection struct {
	Suite          string
	Match          string
	Tag            string
	ShardIndex     int
	ShardCount     int
	Seed           uint64
	Costs          CostProfile
	Workers        int
	MinecraftSlots int
}

type Entry struct {
	ID               string    `json:"id"`
	Suite            string    `json:"suite"`
	Tags             []string  `json:"tags"`
	Recipe           string    `json:"recipe"`
	Isolation        Isolation `json:"isolation"`
	Timeout          string    `json:"timeout"`
	Shard            int       `json:"shard"`
	EstimatedSeconds float64   `json:"estimated_seconds"`
	MinecraftSlots   int       `json:"minecraft_slots"`
}

type Group struct {
	Key   string
	Cases []Case
}
type Plan struct {
	Seed       uint64     `json:"seed"`
	ShardIndex int        `json:"shard_index"`
	ShardCount int        `json:"shard_count"`
	Catalog    []Entry    `json:"catalog"`
	Order      []string   `json:"order"`
	Groups     []Group    `json:"-"`
	Scheduling Scheduling `json:"scheduling"`
}

func BuildPlan(catalog []Case, selection Selection) (Plan, error) {
	plan := Plan{Seed: selection.Seed, ShardIndex: selection.ShardIndex, ShardCount: selection.ShardCount, Order: []string{}}
	if selection.ShardCount < 1 || selection.ShardIndex < 1 || selection.ShardIndex > selection.ShardCount {
		return plan, fmt.Errorf("shard must be INDEX/COUNT, with 1 <= INDEX <= COUNT")
	}
	profile, config, err := scheduling(selection)
	if err != nil {
		return plan, err
	}
	plan.Scheduling = config
	matcher, err := regexp.Compile(selection.Match)
	if err != nil {
		return plan, err
	}
	ids := map[string]bool{}
	recipes := map[string]*environment.Recipe{}
	groups := map[string][]Case{}
	valid := regexp.MustCompile(`^[a-z][a-z0-9_.-]+$`)
	catalog = append([]Case(nil), catalog...)
	sort.Slice(catalog, func(i, j int) bool { return catalog[i].ID < catalog[j].ID })
	for _, test := range catalog {
		if !valid.MatchString(test.ID) || test.Suite == "" || test.Run == nil || test.Timeout <= 0 {
			return plan, fmt.Errorf("invalid case %q", test.ID)
		}
		if ids[test.ID] {
			return plan, fmt.Errorf("duplicate case %s", test.ID)
		}
		ids[test.ID] = true
		if test.Isolation != Fresh && test.Isolation != CleanReuse && test.Isolation != ObserveReuse {
			return plan, fmt.Errorf("case %s requires an explicit isolation policy", test.ID)
		}
		providers, err := test.Recipe.Ordered()
		if err != nil {
			return plan, fmt.Errorf("case %s: %w", test.ID, err)
		}
		if prior := recipes[test.Recipe.ID]; prior != nil && prior != test.Recipe {
			return plan, fmt.Errorf("recipe ID %s refers to different definitions", test.Recipe.ID)
		}
		recipes[test.Recipe.ID] = test.Recipe
		if test.Isolation != Fresh {
			for _, p := range providers {
				if p.Verify == nil {
					return plan, fmt.Errorf("case %s reuses unverifiable provider %s", test.ID, p.ID)
				}
			}
		}
		if selection.Suite != "" && selection.Suite != test.Suite {
			continue
		}
		if !matcher.MatchString(test.ID) {
			continue
		}
		if selection.Tag != "" {
			found := false
			for _, tag := range test.Tags {
				if tag == selection.Tag {
					found = true
				}
			}
			if !found {
				continue
			}
		}
		key := "recipe:" + test.Recipe.ID
		if test.Isolation == Fresh {
			key = "case:" + test.ID
		}
		groups[key] = append(groups[key], test)
		plan.Catalog = append(plan.Catalog, Entry{ID: test.ID, Suite: test.Suite, Tags: test.Tags, Recipe: test.Recipe.ID, Isolation: test.Isolation, Timeout: test.Timeout.String(), EstimatedSeconds: profile.estimate(test), MinecraftSlots: test.Recipe.MinecraftSlots})
	}
	if len(plan.Catalog) == 0 {
		return plan, fmt.Errorf("selection matched no cases")
	}
	assignments := assignGroups(groups, profile, config, selection.ShardCount)
	for index := range plan.Catalog {
		entry := &plan.Catalog[index]
		key := "recipe:" + entry.Recipe
		if entry.Isolation == Fresh {
			key = "case:" + entry.ID
		}
		entry.Shard = assignments[key]
	}
	var keys []string
	for key := range groups {
		if assignments[key] == selection.ShardIndex {
			keys = append(keys, key)
		}
	}
	sort.Strings(keys)
	random := rand.New(rand.NewPCG(selection.Seed, selection.Seed^0x9e3779b97f4a7c15))
	if selection.Seed != 0 {
		random.Shuffle(len(keys), func(i, j int) { keys[i], keys[j] = keys[j], keys[i] })
	}
	for _, key := range keys {
		tests := groups[key]
		if selection.Seed != 0 {
			random.Shuffle(len(tests), func(i, j int) { tests[i], tests[j] = tests[j], tests[i] })
		}
		plan.Groups = append(plan.Groups, Group{Key: key, Cases: tests})
		for _, test := range tests {
			plan.Order = append(plan.Order, test.ID)
		}
	}
	return plan, nil
}
