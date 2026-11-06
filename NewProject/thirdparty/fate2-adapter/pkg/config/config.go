package config

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/secretflow/kuscia/thirdparty/fate2-adapter/pkg/models"
)

const (
	// EnvClusterAddress is the FATE-Flow HTTP address, e.g. http://fate-flow:9380.
	EnvClusterAddress = "FATE_FLOW_ADDRESS"
	// EnvTaskConfigPath is the path to the Kuscia task config file.
	EnvTaskConfigPath = "TASK_CONFIG_PATH"
	// DefaultTaskConfigPath matches Kuscia's default mount path.
	DefaultTaskConfigPath = "/etc/kuscia/task-config.conf"
)

// Config holds runtime configuration for the adapter.
type Config struct {
	ClusterAddress string
	TaskConfig     models.KusciaTaskConfig
}

// Load reads configuration from environment variables and the task config file.
func Load() (*Config, error) {
	clusterAddress := os.Getenv(EnvClusterAddress)
	if clusterAddress == "" {
		clusterAddress = "http://127.0.0.1:9380"
	}

	taskConfigPath := os.Getenv(EnvTaskConfigPath)
	if taskConfigPath == "" {
		taskConfigPath = DefaultTaskConfigPath
	}

	raw, err := os.ReadFile(taskConfigPath)
	if err != nil {
		return nil, fmt.Errorf("read task config %s: %w", taskConfigPath, err)
	}

	var taskConfig models.KusciaTaskConfig

	// Kuscia mounts task config as a JSON object with string fields.
	// The most common format is:
	//   {"task_id": "...", "task_input_config": "<json-string>"}
	var wrapped map[string]string
	if err := json.Unmarshal(raw, &wrapped); err == nil {
		taskConfig.TaskID = wrapped["task_id"]
		if taskConfig.ClusterAddress == "" {
			taskConfig.ClusterAddress = wrapped["cluster_address"]
		}
		if input, ok := wrapped["task_input_config"]; ok && input != "" {
			if err := json.Unmarshal([]byte(input), &taskConfig.TaskInputConfig); err != nil {
				return nil, fmt.Errorf("unmarshal task_input_config string: %w", err)
			}
		}
	} else {
		// Fallback: try to unmarshal directly as KusciaTaskConfig.
		if err := json.Unmarshal(raw, &taskConfig); err != nil {
			return nil, fmt.Errorf("unmarshal task config: %w", err)
		}
	}

	if taskConfig.TaskInputConfig == nil {
		// Last resort: the raw file itself might be the BFIA job request.
		var req models.CreateJobRequest
		if err := json.Unmarshal(raw, &req); err == nil {
			taskConfig.TaskInputConfig = &req
		} else {
			return nil, fmt.Errorf("task_input_config is missing and raw config is not a BFIA job request")
		}
	}

	// Priority:
	// 1. task_input_config.fate_flow_address (injected per FateCluster by SecretPad)
	// 2. env FATE_FLOW_ADDRESS (AppImage default)
	// 3. fallback default
	if taskConfig.TaskInputConfig != nil && taskConfig.TaskInputConfig.ClusterAddress != "" {
		clusterAddress = taskConfig.TaskInputConfig.ClusterAddress
	}

	return &Config{
		ClusterAddress: clusterAddress,
		TaskConfig:     taskConfig,
	}, nil
}
