# FATE 2.x Kuscia Adapter

A lightweight adapter that lets Kuscia schedule FATE 2.x jobs through the native FATE 2.x API (`/v2/job/*`).

## Deployment boundary

The adapter runs only on Alice. The native FATE Guest (`19381`) and Host
(`19382`) are independent containers, federating with their native party IDs
`JG0100001100000010` and `JG0100001100000000`. Bob is exclusively BFIA and
Kimi exclusively native SecretFlow. Neither is a FATE scheduler participant.
Do not register this AppImage on Bob or change Alice–Bob routes to Kuscia.
The platform request is translated into a native FATE DAG; no BFIA scheduler is used.

## What it does

- Reads the platform DAG and native party configuration from Kuscia task config.
- Translates PSI, coordinated LR and heterogeneous SecureBoost into a native FATE 2.0 DAG, including readers and data bindings.
- Calls `POST /v2/job/submit` and polls `/v2/job/query` and `/v2/job/task/query`.
- Returns success only when the native job and all local native tasks report `success`; the native scheduler coordinates peer completion.
- Cancels the native job on timeout. Defaults: 30 minutes, one computing worker per task and one data partition.
- Coordinated LR hosts the arbiter role on the native Host when no explicit arbiter is given.

## Project layout

```
.
├── cmd/adapter          # Entry point
├── pkg/
│   ├── adapter          # Main lifecycle (create/start/poll)
│   ├── client           # FATE-Flow HTTP client
│   ├── config           # Config parsing from env + task config file
│   └── models           # BFIA request/response structs
├── scripts/
│   ├── Dockerfile       # Multi-stage build
│   ├── build.sh         # Build the Docker image
│   ├── app_image.fate2.yaml   # Kuscia AppImage
│   └── fate2_job.yaml   # Sample KusciaJob
└── examples/
    └── task_config.json # Local test config
```

## Build

```bash
cd thirdparty/fate2-adapter
./scripts/build.sh
```

The image is tagged `secretflow/fate2-adapter:0.2.0-native` by default.

## Local test (without Kuscia)

If you have a FATE-Flow 2.x instance listening on `http://localhost:19381`:

```bash
go run ./cmd/adapter \
  -c examples/task_config.json \
  -a http://localhost:19381
```

## Use in Kuscia

1. Load the AppImage:

```bash
docker exec ${USER}-kuscia-autonomy-alice \
  kubectl apply -f /home/kuscia/var/images/app_image.fate2.yaml
```

2. Submit the sample job:

```bash
docker exec ${USER}-kuscia-autonomy-alice \
  kubectl apply -f /home/kuscia/var/images/fate2_job.yaml
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `FATE_FLOW_ADDRESS` | `http://127.0.0.1:9380` | FATE-Flow 2.x HTTP address |
| `TASK_CONFIG_PATH` | `/etc/kuscia/task-config.conf` | Path to Kuscia task config |

## Limitations

- Supports one native Guest and one native Host for the three canvas components listed above.
- Both native FATE sites must be reachable through OSX. Their native data tables must already exist.
- For the installed local pair, run `NewProject/scripts/configure_native_fate.py` from the workspace to configure OSX routes, startup recovery, and bounded worker pools. Existing configurations are backed up before the first change.
- Historical jobs from the old BFIA adapter are not native execution proof: `FINISHED` could be returned with failed or unstarted tasks. The platform labels their former successes `UNVERIFIED`.
