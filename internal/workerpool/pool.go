package workerpool

import (
	"fmt"
	"sync"
)

const defaultMaxConcurrency = 10

// Pool runs submitted tasks with a bounded concurrency.
type Pool struct {
	sem chan struct{}
	wg  sync.WaitGroup
}

func New(maxConcurrency int) *Pool {
	if maxConcurrency <= 0 {
		maxConcurrency = defaultMaxConcurrency
	}
	return &Pool{sem: make(chan struct{}, maxConcurrency)}
}

func (p *Pool) Submit(task func()) error {
	if task == nil {
		return fmt.Errorf("task is nil")
	}

	p.sem <- struct{}{}
	p.wg.Add(1)
	go func() {
		defer p.wg.Done()
		defer func() { <-p.sem }()
		task()
	}()

	return nil
}

func (p *Pool) Wait() {
	p.wg.Wait()
}

func (p *Pool) Capacity() int {
	return cap(p.sem)
}

func (p *Pool) Active() int {
	return len(p.sem)
}
