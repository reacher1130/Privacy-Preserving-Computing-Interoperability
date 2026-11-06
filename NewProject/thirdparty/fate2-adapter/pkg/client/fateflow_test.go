package client

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

func TestFate22StatusContract(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/interconn/schedule/job/status_all" || r.Method != "GET" {
			t.Errorf("unexpected endpoint %s %s", r.Method, r.URL.Path)
		}
		var body map[string]string
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body["job_id"] != "job-1" {
			t.Errorf("expected job_id in JSON body, got %v", body)
		}
		fmt.Fprint(w, `{"code":0,"data":{"job_status":"SUCCESS","status":{"psi":"SUCCESS"}}}`)
	}))
	defer server.Close()
	for _, address := range []string{server.URL, server.URL + "/v1/interconn"} {
		status, err := NewFateFlowClient(address).GetJobStatus(context.Background(), "job-1")
		if err != nil || status != "SUCCESS" {
			t.Fatalf("status=%s err=%v", status, err)
		}
	}
}

func TestRejectsFalseSuccess(t *testing.T) {
	for _, tc := range []struct {
		code int
		body string
	}{
		{404, `{"code":0}`}, {200, `{}`}, {200, `{"code":101,"msg":"failed"}`},
		{200, `{"code":0,"data":{}}`}, {200, `{"code":0,"data":null}`},
	} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(tc.code)
			fmt.Fprint(w, tc.body)
		}))
		_, err := NewFateFlowClient(server.URL).GetJobStatus(context.Background(), "job-1")
		server.Close()
		if err == nil {
			t.Fatalf("false success for %s", tc.body)
		}
	}
}

// Read-only check against the real FATE image; absence is not a successful job.
func TestLiveFate22Connectivity(t *testing.T) {
	address := os.Getenv("FATE_FLOW_TEST_ADDRESS")
	if address == "" {
		t.Skip("real FATE endpoint not configured")
	}
	_, err := NewFateFlowClient(address).GetJobStatus(context.Background(), "codex-readiness-no-such-job")
	if err == nil || !strings.Contains(err.Error(), "not found in status response") {
		t.Fatalf("expected real BFIA unknown-job response, got %v", err)
	}
}

func TestFinishedWithUnexecutedTasksIsFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, `{"code":0,"data":{"job_status":"FINISHED","status":{"psi":"READY"}}}`)
	}))
	defer server.Close()
	state, err := NewFateFlowClient(server.URL).GetJobStatus(context.Background(), "job")
	if err != nil || state != "FAILED" {
		t.Fatalf("%s %v", state, err)
	}
}
func TestNativeSuccessRequiresSuccessfulTasks(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "task/query") {
			fmt.Fprint(w, `{"code":0,"data":[{"status":"failed"}]}`)
		} else {
			fmt.Fprint(w, `{"code":0,"data":[{"status":"success"}]}`)
		}
	}))
	defer server.Close()
	state, err := NewFateFlowClient(server.URL).NativeStatus(context.Background(), "job")
	if err != nil || state != "FAILED" {
		t.Fatalf("%s %v", state, err)
	}
}
