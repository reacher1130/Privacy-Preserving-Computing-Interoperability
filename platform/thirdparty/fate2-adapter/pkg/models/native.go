package models

import (
	"fmt"
	"strings"
)

type object = map[string]interface{}

func nested(v interface{}, keys ...string) interface{} {
	for _, key := range keys {
		m, ok := v.(map[string]interface{})
		if !ok {
			return nil
		}
		v = m[key]
	}
	return v
}

// NativeSchema translates the three canvas components to FATE's native DAG.
// The native Flow executes local providers and federates through OSX, without Bob.
func (r *CreateJobRequest) NativeSchema() (object, error) {
	if len(r.Config.Role.Guest) != 1 || len(r.Config.Role.Host) != 1 {
		return nil, fmt.Errorf("native canvas requires one guest and one host")
	}
	guest, host := r.Config.Role.Guest[0], r.Config.Role.Host[0]
	for _, id := range []string{guest, host} {
		if id == "alice" || id == "bob" || id == "kimi" {
			return nil, fmt.Errorf("use native FATE party IDs")
		}
	}
	party := func(role, id string) object { return object{"role": role, "party_id": []string{id}} }
	dataParties := []object{party("guest", guest), party("host", host)}
	parties := append([]object{}, dataParties...)
	hasLR := false
	components := map[string]DagComponentSpec{}
	for _, c := range r.Dag.Components {
		components[c.Name] = c
		if c.ComponentName == "coordinated_lr" {
			hasLR = true
		}
	}
	if hasLR {
		arbiter := host
		if len(r.Config.Role.Arbiter) > 0 {
			arbiter = r.Config.Role.Arbiter[0]
		}
		// Coordinated LR requires an arbiter; it is a role on the native Host,
		// not a third platform node. Explicit native arbiter IDs remain supported.
		parties = append(parties, party("arbiter", arbiter))
	}
	tasks := object{}
	partyTasks := object{}
	for _, c := range r.Dag.Components {
		if c.ComponentName != "psi" && c.ComponentName != "coordinated_lr" && c.ComponentName != "hetero_secureboost" {
			return nil, fmt.Errorf("unsupported native canvas component %s", c.ComponentName)
		}
		params := object{}
		for k, v := range c.Parameter {
			if !strings.HasPrefix(k, "__") && v != nil {
				params[k] = v
			}
		}
		if common, ok := nested(r.Config.TaskParams, "common", c.Name).(map[string]interface{}); ok {
			for k, v := range common {
				if v != nil {
					params[k] = v
				}
			}
		}
		node := object{"component_ref": c.ComponentName, "parameters": params, "parties": dataParties, "stage": "train"}
		inputKey := "train_data"
		if c.ComponentName == "psi" {
			inputKey = "input_data"
			node["stage"] = "default"
		}
		if c.ComponentName == "coordinated_lr" {
			node["parties"] = parties
		}
		var producer, artifact string
		if len(c.Input) == 0 {
			if c.ComponentName != "psi" {
				return nil, fmt.Errorf("%s requires upstream data", c.Name)
			}
			producer = "reader_" + c.Name
			artifact = "output_data"
			tasks[producer] = object{"component_ref": "reader", "parties": dataParties, "stage": "default"}
			for role, id := range map[string]string{"guest": guest, "host": host} {
				ref, _ := nested(r.Config.TaskParams, role, "0", c.Name, "dataset_id").(string)
				if ref == "" {
					key := "__guestDatasetRef"
					if role == "host" {
						key = "__hostDatasetRef"
					}
					ref, _ = c.Parameter[key].(string)
				}
				split := strings.SplitN(ref, "#", 2)
				if len(split) != 2 {
					return nil, fmt.Errorf("%s %s requires namespace#table dataset binding", c.Name, role)
				}
				key := role + "_" + id
				item, ok := partyTasks[key].(object)
				if !ok {
					item = object{"parties": []object{party(role, id)}, "tasks": object{}}
					partyTasks[key] = item
				}
				item["tasks"].(object)[producer] = object{"parameters": object{"namespace": split[0], "name": split[1]}}
			}
		} else {
			if len(c.Input) != 1 {
				return nil, fmt.Errorf("%s requires one data input", c.Name)
			}
			producer = strings.SplitN(c.Input[0].Key, ".", 2)[0]
			upstream, ok := components[producer]
			if !ok {
				return nil, fmt.Errorf("unknown upstream %s", producer)
			}
			artifact = "train_output_data"
			if upstream.ComponentName == "psi" {
				artifact = "output_data"
			}
		}
		node["dependent_tasks"] = []string{producer}
		node["inputs"] = object{"data": object{inputKey: object{"task_output_artifact": object{"producer_task": producer, "output_artifact_key": artifact}}}}
		tasks[c.Name] = node
	}
	if len(tasks) == 0 {
		return nil, fmt.Errorf("native DAG is empty")
	}
	return object{"schema_version": "2.0.0", "kind": "fate", "dag": object{"stage": "train", "parties": parties, "tasks": tasks, "party_tasks": partyTasks, "conf": object{"scheduler_party_id": guest, "initiator_party_id": guest, "cores": 2, "computing_partitions": 1, "task": object{"engine_run": object{"cores": 1}}}}}, nil
}
