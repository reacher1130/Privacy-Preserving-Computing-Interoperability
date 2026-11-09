package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/secretflow/kuscia/thirdparty/fate2-adapter/pkg/models"
)

// FateFlowClient talks to FATE-Flow 2.x BFIA scheduler APIs.
type FateFlowClient struct {
	BaseURL    string
	HTTPClient *http.Client
}

// NewFateFlowClient creates a client for the given FATE-Flow address.
func NewFateFlowClient(address string) *FateFlowClient {
	if address == "" {
		address = "http://127.0.0.1:9380"
	}
	address = strings.TrimRight(address, "/")
	if !strings.HasSuffix(address, "/v1/interconn") {
		address += "/v1/interconn"
	}
	return &FateFlowClient{
		BaseURL: address,
		HTTPClient: &http.Client{
			Timeout: 60 * time.Second,
		},
	}
}

// CreateJobAll calls POST /schedule/job/create_all.
func (c *FateFlowClient) CreateJobAll(ctx context.Context, req *models.CreateJobRequest) (*models.CreateJobResponse, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("marshal create job request: %w", err)
	}

	u, err := url.JoinPath(c.BaseURL, "/schedule/job/create_all")
	if err != nil {
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("create_all http do: %w", err)
	}
	defer resp.Body.Close()

	return decode[models.CreateJobResponse](resp)
}

// StartJob calls POST /schedule/job/start.
func (c *FateFlowClient) StartJob(ctx context.Context, jobID string) error {
	body, err := json.Marshal(map[string]string{"job_id": jobID})
	if err != nil {
		return err
	}

	u, err := url.JoinPath(c.BaseURL, "/schedule/job/start")
	if err != nil {
		return err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	if err != nil {
		return err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("start job http do: %w", err)
	}
	defer resp.Body.Close()

	_, err = decode[models.CreateJobResponse](resp)
	return err
}

// StopJobAll calls POST /schedule/job/stop_all.
func (c *FateFlowClient) StopJobAll(ctx context.Context, jobID string) error {
	body, err := json.Marshal(map[string]string{"job_id": jobID})
	if err != nil {
		return err
	}

	u, err := url.JoinPath(c.BaseURL, "/schedule/job/stop_all")
	if err != nil {
		return err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	if err != nil {
		return err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("stop job http do: %w", err)
	}
	defer resp.Body.Close()

	_, err = decode[models.CreateJobResponse](resp)
	return err
}

// GetJobStatus calls GET /schedule/job/status_all.
func (c *FateFlowClient) GetJobStatus(ctx context.Context, jobID string) (string, error) {
	u, err := url.JoinPath(c.BaseURL, "/schedule/job/status_all")
	if err != nil {
		return "", err
	}

	// FATE 2.2's API.Input.json parses the GET JSON body, not query parameters.
	body, err := json.Marshal(map[string]string{"job_id": jobID})
	if err != nil {
		return "", err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, u, bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return "", fmt.Errorf("status_all http do: %w", err)
	}
	defer resp.Body.Close()

	parsed, err := decode[models.JobStatusResponse](resp)
	if err != nil {
		return "", err
	}

	if parsed.Data == nil {
		return "", fmt.Errorf("status response data is nil")
	}

	status := parsed.Data.JobStatus
	if status == "" {
		return "", fmt.Errorf("job_id %s not found in status response", jobID)
	}
	if status == "FINISHED" || status == "SUCCESS" {
		if len(parsed.Data.Tasks) == 0 {
			return "FAILED", nil
		}
		for _, taskState := range parsed.Data.Tasks {
			if taskState != "SUCCESS" {
				return "FAILED", nil
			}
		}
	}
	return status, nil
}

func decode[T any](resp *http.Response) (*T, error) {
	data, err := io.ReadAll(io.LimitReader(resp.Body, 2<<20))
	if err != nil {
		return nil, fmt.Errorf("read response body: %w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("fate flow HTTP status %d", resp.StatusCode)
	}
	var envelope struct {
		Code    *int   `json:"code"`
		Msg     string `json:"msg"`
		Message string `json:"message"`
	}
	if err := json.Unmarshal(data, &envelope); err != nil || envelope.Code == nil {
		return nil, fmt.Errorf("fate flow response is missing a valid BFIA code")
	}

	var out T
	if err := json.Unmarshal(data, &out); err != nil {
		return nil, fmt.Errorf("unmarshal response: %w, body: %s", err, string(data))
	}

	// Try to access Code generically through the concrete type.
	switch v := any(out).(type) {
	case models.CreateJobResponse:
		if v.Code != 0 {
			message := v.Msg
			if message == "" {
				message = v.Message
			}
			if message == "" {
				message = envelope.Msg
			}
			if message == "" {
				message = envelope.Message
			}
			return &out, fmt.Errorf("fate flow returned code %d, msg: %s", v.Code, message)
		}
	case models.JobStatusResponse:
		if v.Code != 0 {
			message := v.Msg
			if message == "" {
				message = v.Message
			}
			if message == "" {
				message = envelope.Msg
			}
			if message == "" {
				message = envelope.Message
			}
			return &out, fmt.Errorf("fate flow returned code %d, msg: %s", v.Code, message)
		}
	}

	return &out, nil
}
