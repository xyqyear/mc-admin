package engine

import (
	"context"
	"fmt"
	"sort"
	"time"
)

type queuedGroup struct {
	group           Group
	queued          time.Time
	resourceBlocked time.Time
	resourceWait    time.Duration
}

type completedGroup struct {
	results []Result
	slots   int
}

func Run(ctx context.Context, plan Plan, factory Factory, options Options) []Result {
	ctx, cancel := context.WithCancelCause(ctx)
	defer cancel(nil)
	options.abort = cancel
	queuedAt := time.Now()
	pending := make([]queuedGroup, len(plan.Groups))
	for index, group := range plan.Groups {
		pending[index] = queuedGroup{group: group, queued: queuedAt}
	}
	completed := make(chan completedGroup)
	var results []Result
	running, occupied := 0, 0
	cancelled := ctx.Done()
	for len(pending) > 0 || running > 0 {
		now := time.Now()
		selected := -1
		for index := range pending {
			item := &pending[index]
			slots := item.group.Cases[0].Recipe.MinecraftSlots
			blocked := slots <= options.MinecraftSlots && slots+occupied > options.MinecraftSlots && ctx.Err() == nil
			if blocked && item.resourceBlocked.IsZero() {
				item.resourceBlocked = now
			} else if !blocked && !item.resourceBlocked.IsZero() {
				item.resourceWait += now.Sub(item.resourceBlocked)
				item.resourceBlocked = time.Time{}
			}
			if !blocked && selected == -1 {
				selected = index
			}
		}
		if running < max(options.Workers, 1) && selected >= 0 {
			item := pending[selected]
			pending = append(pending[:selected], pending[selected+1:]...)
			groupOptions := options
			groupOptions.queueSeconds = now.Sub(item.queued).Seconds()
			groupOptions.resourceWaitSeconds = item.resourceWait.Seconds()
			if ctx.Err() != nil {
				results = append(results, runGroup(ctx, item.group, factory, groupOptions)...)
				continue
			}
			slots := item.group.Cases[0].Recipe.MinecraftSlots
			if slots > options.MinecraftSlots {
				for index, test := range item.group.Cases {
					result := Result{ID: test.ID, Suite: test.Suite, Started: now.UTC(), Status: "failed"}
					if index == 0 {
						result.Timings.SchedulerQueueSeconds = groupOptions.queueSeconds
						result.Timings.SchedulerResourceWaitSeconds = groupOptions.resourceWaitSeconds
					}
					result.issue("reservation", fmt.Errorf("recipe requires %d Minecraft slots with budget %d", slots, options.MinecraftSlots), options.Redactor)
					results = append(results, result)
				}
				continue
			}
			occupied += slots
			running++
			go func() {
				completed <- completedGroup{results: runGroup(ctx, item.group, factory, groupOptions), slots: slots}
			}()
			continue
		}
		select {
		case group := <-completed:
			results = append(results, group.results...)
			if !hasTeardownFailure(group.results) {
				occupied -= group.slots
			}
			running--
		case <-cancelled:
			cancelled = nil
		}
	}
	sort.Slice(results, func(i, j int) bool { return results[i].ID < results[j].ID })
	return results
}

func hasTeardownFailure(results []Result) bool {
	for _, result := range results {
		for _, issue := range result.Issues {
			if issue.Phase == "teardown" {
				return true
			}
		}
	}
	return false
}
