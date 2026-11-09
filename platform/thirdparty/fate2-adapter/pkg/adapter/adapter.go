package adapter

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/secretflow/kuscia/thirdparty/fate2-adapter/pkg/client"
	"github.com/secretflow/kuscia/thirdparty/fate2-adapter/pkg/config"
)

// Adapter submits a native FATE 2.x job and waits for verified completion.
type Adapter struct {
	conf   *config.Config
	client *client.FateFlowClient
	jobID  string
}

// New creates a new adapter from loaded configuration.
func New(conf *config.Config) *Adapter {
	return &Adapter{
		conf:   conf,
		client: client.NewFateFlowClient(conf.ClusterAddress),
	}
}

// Run executes the full adapter lifecycle.
func (a *Adapter) Run(ctx context.Context) error {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Minute)
	defer cancel()
	req := a.conf.TaskConfig.TaskInputConfig
	if req == nil {
		return fmt.Errorf("task_input_config is nil")
	}
	schema, err := req.NativeSchema()
	if err != nil {
		return err
	}
	fmt.Printf("[fate2-adapter] local job %s uses independent native FATE at %s\n", req.JobID, a.conf.ClusterAddress)
	id, err := a.client.SubmitNative(ctx, schema)
	if err != nil {
		return fmt.Errorf("native FATE submit failed: %w", err)
	}
	a.jobID = id
	fmt.Printf("[fate2-adapter] native_job_id=%s\n", id)

	// 3. Poll status until terminal state.
	return a.waitForCompletion(ctx)
}

// JobID returns the FATE job id.
func (a *Adapter) JobID() string {
	return a.jobID
}

func (a *Adapter) waitForCompletion(ctx context.Context) error {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	queryErrors := 0
	// Also do an immediate first check.
	for {
		status, err := a.client.NativeStatus(ctx, a.jobID)
		if err != nil {
			fmt.Printf("[fate2-adapter] query status error: %v\n", err)
			queryErrors++
			if queryErrors >= 10 {
				return fmt.Errorf("native status verification failed repeatedly: %w", err)
			}
		} else {
			queryErrors = 0
			fmt.Printf("[fate2-adapter] job %s status: %s\n", a.jobID, status)
			if isTerminal(status) {
				_ = WriteResult("/tmp/fate2-adapter-result.json", TaskResult{
					JobID:  a.jobID,
					Status: status,
				})
				if isSuccess(status) {
					fmt.Printf("[fate2-adapter] job %s succeeded\n", a.jobID)
					return nil
				}
				return fmt.Errorf("job %s terminated with status %s", a.jobID, status)
			}
		}

		select {
		case <-ctx.Done():
			// Graceful stop: try to stop the remote job.
			_ = a.client.StopNative(context.Background(), a.jobID)
			return ctx.Err()
		case <-ticker.C:
			continue
		}
	}
}

// SetupSignalContext returns a context that is canceled on SIGTERM/SIGINT.
func SetupSignalContext() context.Context {
	ctx, cancel := context.WithCancel(context.Background())
	c := make(chan os.Signal, 1)
	signal.Notify(c, syscall.SIGTERM, syscall.SIGINT)
	go func() {
		<-c
		cancel()
	}()
	return ctx
}

func isTerminal(status string) bool {
	switch status {
	case "SUCCESS", "FINISHED", "FAILED", "CANCELED", "TIMEOUT", "REJECTED":
		return true
	}
	return false
}

func isSuccess(status string) bool {
	return status == "SUCCESS"
}

// TaskResult is written to a well-known path so that Kuscia can pick it up if needed.
type TaskResult struct {
	JobID  string `json:"job_id"`
	Status string `json:"status"`
}

// WriteResult writes a result file for debugging or optional consumption.
func WriteResult(path string, result TaskResult) error {
	f, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("create result file: %w", err)
	}
	defer f.Close()

	enc := json.NewEncoder(f)
	enc.SetIndent("", "  ")
	return enc.Encode(result)
}
