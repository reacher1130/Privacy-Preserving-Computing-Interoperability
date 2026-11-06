package models

import (
	"os"
	"strings"
)

// CreateJobRequest matches FATE 2.x /schedule/job/create_all request body.
type CreateJobRequest struct {
	JobID    string    `json:"job_id"`
	FlowID   string    `json:"flow_id"`
	OldJobID string    `json:"old_job_id"`
	Dag      DagSpec   `json:"dag"`
	Config   DagConfig `json:"config"`
	// ClusterAddress is the FATE-Flow HTTP endpoint. It is injected by SecretPad
	// per FateCluster so that one AppImage can serve multiple FATE backends.
	ClusterAddress string `json:"fate_flow_address,omitempty"`
}

// DagSpec is the BFIA DAG definition.
type DagSpec struct {
	Version string `json:"version"`
	// FATE 2.x BFIA schema uses an ordered list, not the legacy name->component map.
	Components []DagComponentSpec `json:"components"`
}

// DagComponentSpec describes one node in the BFIA DAG.
type DagComponentSpec struct {
	Name          string                 `json:"name"`
	ComponentName string                 `json:"componentName"`
	Provider      string                 `json:"provider"`
	Version       string                 `json:"version"`
	Role          string                 `json:"role,omitempty"`
	Input         []DataSpec             `json:"input,omitempty"`
	Output        []DataSpec             `json:"output,omitempty"`
	Parameter     map[string]interface{} `json:"parameter,omitempty"`
}

// DataSpec is the BFIA artifact reference expected by FATE-Flow 2.x.
type DataSpec struct {
	Key  string `json:"key"`
	Type string `json:"type"`
}

// DagConfig contains party/role configuration and common job parameters.
type DagConfig struct {
	Initiator InitiatorConfig `json:"initiator"`
	Role      RoleConfig      `json:"role"`
	// FATE's BFIA schema allows common plus per-role job parameters.  Keep the
	// object open so the adapter does not silently drop guest/host/arbiter
	// fields while unmarshalling and forwarding a SecretPad request.
	JobParams  map[string]interface{} `json:"job_params"`
	TaskParams map[string]interface{} `json:"task_params,omitempty"`
	Version    string                 `json:"version"`
}

// InitiatorConfig identifies the initiator party.
type InitiatorConfig struct {
	Role    string `json:"role"`
	NodeID  string `json:"node_id"`
	PartyID string `json:"party_id"`
}

// RoleConfig lists node_ids per role.
type RoleConfig struct {
	Guest   []string `json:"guest,omitempty"`
	Host    []string `json:"host,omitempty"`
	Arbiter []string `json:"arbiter,omitempty"`
}

// CreateJobResponse is the response from /schedule/job/create_all.
type CreateJobResponse struct {
	Code    int                    `json:"code"`
	Msg     string                 `json:"msg,omitempty"`
	Message string                 `json:"message,omitempty"`
	Data    map[string]interface{} `json:"data,omitempty"`
}

// JobStatusResponse is the response from /schedule/job/status_all.
type JobStatusResponse struct {
	Code    int            `json:"code"`
	Msg     string         `json:"msg,omitempty"`
	Message string         `json:"message,omitempty"`
	Data    *JobStatusData `json:"data,omitempty"`
}

type JobStatusData struct {
	JobStatus string            `json:"job_status"`
	Tasks     map[string]string `json:"status"`
}

// KusciaTaskConfig is the expected shape of task_input_config passed by Kuscia.
type KusciaTaskConfig struct {
	TaskID          string            `json:"task_id"`
	TaskInputConfig *CreateJobRequest `json:"task_input_config"`
	// ClusterAddress may be injected by the AppImage env if not present.
	ClusterAddress string `json:"cluster_address,omitempty"`
}

// NormalizePartyIDs translates SecretPad/Kuscia domain ids to the FATE party
// ids used by the configured FATE Flow pair.  SecretPad deliberately keeps
// the user-facing ids (alice/bob) in its graph and Kuscia task parties; FATE
// BFIA, however, routes federated calls by its own stable party ids.
//
// The defaults match the local two-node deployment.  Production deployments
// can override them with FATE_GUEST_PARTY_ID and FATE_HOST_PARTY_ID.
func (r *CreateJobRequest) NormalizePartyIDs() {
	if r == nil {
		return
	}
	guestID := envOrDefault("FATE_GUEST_PARTY_ID", "JG0100001100000010")
	hostID := envOrDefault("FATE_HOST_PARTY_ID", "JG0100001100000000")
	mapID := func(id string) string {
		switch strings.ToLower(strings.TrimSpace(id)) {
		case "alice", "guest":
			return guestID
		case "bob", "host":
			return hostID
		default:
			return id
		}
	}
	for i, id := range r.Config.Role.Guest {
		r.Config.Role.Guest[i] = mapID(id)
	}
	for i, id := range r.Config.Role.Host {
		r.Config.Role.Host[i] = mapID(id)
	}
	for i, id := range r.Config.Role.Arbiter {
		r.Config.Role.Arbiter[i] = mapID(id)
	}
	r.Config.Initiator.NodeID = mapID(r.Config.Initiator.NodeID)
	if strings.TrimSpace(r.Config.Initiator.PartyID) == "" || r.Config.Initiator.PartyID == "10000" || r.Config.Initiator.PartyID == "9999" {
		if strings.EqualFold(r.Config.Initiator.Role, "host") {
			r.Config.Initiator.PartyID = hostID
		} else {
			r.Config.Initiator.PartyID = guestID
		}
	}
}

func envOrDefault(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}
