package models

import (
	"encoding/json"
	"testing"
)

func TestNativeDagSeparatesRuntimeFromFateParties(t *testing.T) {
	r := CreateJobRequest{Config: DagConfig{Role: RoleConfig{Guest: []string{"native-guest"}, Host: []string{"native-host"}}}, Dag: DagSpec{Components: []DagComponentSpec{{Name: "psi", ComponentName: "psi", Parameter: map[string]interface{}{"__guestDatasetRef": "experiment#guest", "__hostDatasetRef": "experiment#host"}}, {Name: "lr", ComponentName: "coordinated_lr", Input: []DataSpec{{Key: "psi.data"}}}}}}
	schema, err := r.NativeSchema()
	if err != nil {
		t.Fatal(err)
	}
	dag := schema["dag"].(object)
	tasks := dag["tasks"].(object)
	if len(tasks) != 3 {
		t.Fatal(tasks)
	}
	if len(dag["parties"].([]object)) != 3 {
		t.Fatal("LR requires native arbiter role")
	}
	if tasks["psi"].(object)["component_ref"] != "psi" {
		t.Fatal(tasks)
	}
	b, _ := json.Marshal(schema)
	t.Log(string(b))
	r.Config.Role.Host = []string{"bob"}
	if _, err = r.NativeSchema(); err == nil {
		t.Fatal("Bob must not be a native FATE party")
	}
}
