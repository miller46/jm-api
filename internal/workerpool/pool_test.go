package workerpool

import (
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestPoolLimitsConcurrency(t *testing.T) {
	pool := New(3)

	var (
		mu      sync.Mutex
		current int
		maxSeen int
		wg      sync.WaitGroup
	)

	tasks := 24
	wg.Add(tasks)

	for i := 0; i < tasks; i++ {
		err := pool.Submit(func() {
			defer wg.Done()

			mu.Lock()
			current++
			if current > maxSeen {
				maxSeen = current
			}
			mu.Unlock()

			time.Sleep(20 * time.Millisecond)

			mu.Lock()
			current--
			mu.Unlock()
		})
		require.NoError(t, err)
	}

	wg.Wait()
	pool.Wait()

	assert.LessOrEqual(t, maxSeen, 3)
}

func TestPoolDefaultsWhenConfiguredWithNonPositiveConcurrency(t *testing.T) {
	pool := New(0)
	assert.Equal(t, DefaultMaxConcurrency, pool.Capacity())
}

func TestPoolRejectsNilTask(t *testing.T) {
	pool := New(1)
	err := pool.Submit(nil)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "task is nil")
}
