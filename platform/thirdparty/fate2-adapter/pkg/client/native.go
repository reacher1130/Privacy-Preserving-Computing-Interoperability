package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
)

func (c *FateFlowClient) nativeRequest(ctx context.Context, method, path string, body interface{}) (map[string]interface{}, error) {
	base := strings.TrimSuffix(c.BaseURL, "/v1/interconn")
	var buffer bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&buffer).Encode(body); err != nil {
			return nil, err
		}
	}
	req, err := http.NewRequestWithContext(ctx, method, base+"/v2/"+path, &buffer)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	response, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return nil, fmt.Errorf("native FATE HTTP %d", response.StatusCode)
	}
	var result map[string]interface{}
	if err = json.NewDecoder(response.Body).Decode(&result); err != nil {
		return nil, err
	}
	code, ok := result["code"].(float64)
	if !ok || code != 0 {
		return nil, fmt.Errorf("native FATE returned %v: %v", result["code"], result["message"])
	}
	return result, nil
}
func (c *FateFlowClient) SubmitNative(ctx context.Context, schema map[string]interface{}) (string, error) {
	r, err := c.nativeRequest(ctx, "POST", "job/submit", map[string]interface{}{"dag_schema": schema})
	if err != nil {
		return "", err
	}
	id, _ := r["job_id"].(string)
	if id == "" {
		return "", fmt.Errorf("native FATE submit omitted job_id")
	}
	return id, nil
}
func (c *FateFlowClient) StopNative(ctx context.Context, id string) error {
	_, err := c.nativeRequest(ctx, "POST", "job/stop", map[string]string{"job_id": id})
	return err
}
func (c *FateFlowClient) NativeStatus(ctx context.Context, id string) (string, error) {
	r, err := c.nativeRequest(ctx, "GET", "job/query?job_id="+url.QueryEscape(id), nil)
	if err != nil {
		return "", err
	}
	rows, ok := r["data"].([]interface{})
	if !ok || len(rows) == 0 {
		return "", fmt.Errorf("native job not found")
	}
	pending := "SUCCESS"
	for _, row := range rows {
		job, ok := row.(map[string]interface{})
		if !ok {
			return "", fmt.Errorf("invalid native job row")
		}
		state, _ := job["status"].(string)
		state = strings.ToUpper(state)
		switch state {
		case "SUCCESS":
		case "FAILED", "CANCELED", "TIMEOUT", "REJECTED":
			return state, nil
		case "WAITING", "READY", "PENDING", "RUNNING":
			pending = "RUNNING"
		default:
			return "FAILED", fmt.Errorf("unverified native job terminal status %q", state)
		}
	}
	if pending != "SUCCESS" {
		return pending, nil
	}
	r, err = c.nativeRequest(ctx, "GET", "job/task/query?job_id="+url.QueryEscape(id), nil)
	if err != nil {
		return "", err
	}
	tasks, ok := r["data"].([]interface{})
	if !ok || len(tasks) == 0 {
		return "", fmt.Errorf("successful native job has no task evidence")
	}
	for _, row := range tasks {
		task, ok := row.(map[string]interface{})
		if !ok {
			return "", fmt.Errorf("invalid native task")
		}
		if strings.ToUpper(fmt.Sprint(task["status"])) != "SUCCESS" {
			return "FAILED", nil
		}
	}
	return "SUCCESS", nil
}
