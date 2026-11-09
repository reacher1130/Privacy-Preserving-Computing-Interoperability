package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/secretflow/kuscia/thirdparty/fate2-adapter/pkg/adapter"
	"github.com/secretflow/kuscia/thirdparty/fate2-adapter/pkg/config"
)

var (
	cfgPath   string
	cluster   string
	version   = "0.1.0"
	gitCommit = "unknown"
)

func main() {
	rootCmd := &cobra.Command{
		Use:   "fate2-adapter",
		Short: "Kuscia adapter for FATE 2.x BFIA scheduler",
		Long: `fate2-adapter reads a Kuscia task config containing a BFIA job request,
submits it to FATE-Flow 2.x via /schedule/job/create_all, starts the job,
and polls /schedule/job/status_all until completion.`,
		Version: fmt.Sprintf("%s (git: %s)", version, gitCommit),
		RunE:    run,
	}

	rootCmd.Flags().StringVarP(&cfgPath, "conf", "c", "", "task config path (env: TASK_CONFIG_PATH)")
	rootCmd.Flags().StringVarP(&cluster, "address", "a", "", "FATE-Flow HTTP address (env: FATE_FLOW_ADDRESS)")

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintf(os.Stderr, "[fate2-adapter] error: %v\n", err)
		os.Exit(1)
	}
}

func run(cmd *cobra.Command, args []string) error {
	if cfgPath != "" {
		os.Setenv(config.EnvTaskConfigPath, cfgPath)
	}
	if cluster != "" {
		os.Setenv(config.EnvClusterAddress, cluster)
	}

	conf, err := config.Load()
	if err != nil {
		return fmt.Errorf("load config: %w", err)
	}

	fmt.Printf("[fate2-adapter] loaded config, cluster=%s\n", conf.ClusterAddress)

	ctx := adapter.SetupSignalContext()
	adapt := adapter.New(conf)
	if err := adapt.Run(ctx); err != nil {
		return err
	}

	fmt.Printf("[fate2-adapter] finished successfully, job_id=%s\n", adapt.JobID())
	return nil
}
