package workerpool

import (
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestPoolLimitsConcurrency(t *testing.T) {
	pool := New(3)

	var current int64
	var maxSeen int64
	var wg sync.WaitGroup

	tasks := 24
	wg.Add(tasks)

	for i := 0; i < tasks; i++ {
		err := pool.Submit(func() {
			defer wg.Done()

			now := atomic.AddInt64(&current, 1)
			for {
				seen := atomic.LoadInt64(&maxSeen)
				if now <= seen || atomic.CompareAndSwapInt64(&maxSeen, seen, now) {
					break
				}
			}

			time.Sleep(20 * time.Millisecond)
			atomic.AddInt64(&current, -1)
		})
		require.NoError(t, err)
	}

	wg.Wait()
	pool.Wait()

	assert.LessOrEqual(t, maxSeen, int64(3))
}

func TestPoolDefaultsWhenConfiguredWithNonPositiveConcurrency(t *testing.T) {
	pool := New(0)
	assert.Equal(t, 10, pool.Capacity())
}

func TestPoolRejectsNilTask(t *testing.T) {
	pool := New(1)
	err := pool.Submit(nil)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "task is nil")
}
