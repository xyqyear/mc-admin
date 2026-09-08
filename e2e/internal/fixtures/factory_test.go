package fixtures

import (
	"context"
	"errors"
	"runtime"
	"sync"
	"testing"
	"time"
)

func TestWeightedReservationsDoNotDeadlock(t *testing.T) {
	factory := NewFactory(Options{MinecraftSlots: 2}, nil, nil)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	var workers sync.WaitGroup
	for range 4 {
		workers.Go(func() {
			for range 100 {
				release, err := factory.acquireSlots(ctx, 2)
				if err != nil {
					t.Error(err)
					return
				}
				runtime.Gosched()
				release()
			}
		})
	}
	workers.Wait()
	if len(factory.slots) != 0 {
		t.Fatal("Minecraft reservations leaked")
	}
}

func TestCancelledReservationReturnsPartialSlots(t *testing.T) {
	factory := NewFactory(Options{MinecraftSlots: 2}, nil, nil)
	factory.slots <- struct{}{}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { _, err := factory.acquireSlots(ctx, 2); done <- err }()
	deadline := time.After(time.Second)
	for len(factory.slots) != 2 {
		select {
		case <-deadline:
			cancel()
			t.Fatal("reservation did not start")
		default:
			runtime.Gosched()
		}
	}
	cancel()
	if err := <-done; !errors.Is(err, context.Canceled) {
		t.Fatalf("expected cancellation, got %v", err)
	}
	if len(factory.slots) != 1 || len(factory.slotGate) != 0 {
		t.Fatal("cancelled reservation retained resources")
	}
	<-factory.slots
	if _, err := factory.acquireSlots(context.Background(), 3); err == nil {
		t.Fatal("oversized reservation accepted")
	}
}
