// Run from the restored dtx-manager module with -mod=vendor; credentials stay on Linux.
package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/md5"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"math/big"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	sdkcrypto "github.com/xuperchain/xuper-sdk-go/crypto"
)

type credentials struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type response struct {
	Code string          `json:"code"`
	Data json.RawMessage `json:"data"`
}

type identity struct {
	key    *ecdsa.PrivateKey
	public string
}

func authorize(req *http.Request, message string, who *identity, offset int64, corrupt bool) error {
	stamp := time.Now().Unix() + offset
	digest := sha256.Sum256([]byte(message + strconv.FormatInt(stamp, 10)))
	r, s, err := ecdsa.Sign(rand.Reader, who.key, digest[:])
	if err != nil {
		return errors.New("signing failed")
	}
	signature := make([]byte, 64)
	r.FillBytes(signature[:32])
	s.FillBytes(signature[32:])
	if corrupt {
		signature[0] ^= 1
	}
	req.Header.Set("X-User-Pubkey", who.public)
	req.Header.Set("Authorization", fmt.Sprintf("auth-v1/%d/%s", stamp, hex.EncodeToString(signature)))
	return nil
}

var client = &http.Client{
	Timeout:       20 * time.Second,
	CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}

func readCredentials(path string) (credentials, error) {
	var c credentials
	info, err := os.Stat(path)
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 {
		return c, errors.New("credentials must be a server-local private file (0600)")
	}
	data, err := os.ReadFile(path)
	if err == nil {
		err = json.Unmarshal(data, &c)
	}
	if err != nil || c.Username == "" || c.Password == "" {
		return c, errors.New("invalid credentials file")
	}
	return c, nil
}

func wirePassword(password string) string {
	digest := md5.Sum([]byte(password))
	return hex.EncodeToString(digest[:])
}

func request(base, method, path string, query url.Values, body interface{}, who *identity, offset int64, corrupt bool) (response, error) {
	var result response
	var payload []byte
	var err error
	if body != nil {
		payload, err = json.Marshal(body)
	}
	if err != nil {
		return result, err
	}
	endpoint := strings.TrimRight(base, "/") + "/dtx/v1/" + path
	if len(query) > 0 {
		endpoint += "?" + query.Encode()
	}
	req, err := http.NewRequest(method, endpoint, bytes.NewReader(payload))
	if err != nil {
		return result, errors.New("invalid endpoint")
	}
	if method == "POST" {
		req.Header.Set("Content-Type", "application/json")
	}
	if who != nil {
		message := string(payload)
		if method == "GET" {
			parts := make([]string, 0, len(query))
			for k := range query {
				parts = append(parts, k+"="+query.Get(k))
			}
			sort.Strings(parts)
			message = strings.Join(parts, "")
		}
		if err = authorize(req, message, who, offset, corrupt); err != nil {
			return result, err
		}
	}
	resp, err := client.Do(req)
	if err != nil {
		return result, errors.New("request failed")
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(io.LimitReader(resp.Body, 2<<20))
	if err != nil || json.Unmarshal(data, &result) != nil || result.Code == "" {
		return result, errors.New("non-API response")
	}
	return result, nil
}

func upload(base, name, content string, who *identity) (string, error) {
	var body bytes.Buffer
	w := multipart.NewWriter(&body)
	if err := w.WriteField("fileName", name); err != nil {
		return "", err
	}
	part, err := w.CreateFormFile("file", name)
	if err != nil {
		return "", err
	}
	if _, err = io.WriteString(part, content); err != nil {
		return "", err
	}
	if err = w.Close(); err != nil {
		return "", err
	}
	req, err := http.NewRequest("POST", strings.TrimRight(base, "/")+"/dtx/v1/data/fileupload", &body)
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", w.FormDataContentType())
	if err = authorize(req, "fileName="+name, who, 0, false); err != nil {
		return "", err
	}
	resp, err := client.Do(req)
	if err != nil {
		return "", errors.New("upload request failed")
	}
	defer resp.Body.Close()
	var result struct {
		Code string `json:"code"`
		Data struct {
			Path string `json:"filePath"`
		} `json:"data"`
	}
	if json.NewDecoder(io.LimitReader(resp.Body, 2<<20)).Decode(&result) != nil || result.Code != "0" || result.Data.Path == "" {
		return "", fmt.Errorf("upload failed (API code %s)", result.Code)
	}
	return result.Data.Path, nil
}

func publicWorkflow(base, credentialsPath string) (map[string]interface{}, error) {
	c, err := readCredentials(credentialsPath)
	if err != nil {
		return nil, err
	}
	admin, err := login(base, c)
	if err != nil {
		return nil, err
	}
	post := func(path string, body interface{}) (response, error) {
		r, e := request(base, "POST", path, nil, body, admin, 0, false)
		if e != nil || r.Code != "0" {
			return r, fmt.Errorf("public workflow %s failed (API code %s)", path, r.Code)
		}
		return r, nil
	}
	namespace := "mgr-" + strconv.FormatInt(time.Now().Unix(), 10)
	if _, err = post("data/ns/add", map[string]interface{}{"name": namespace, "replica": 1, "description": "Synthetic public recovery acceptance"}); err != nil {
		return nil, err
	}
	csv := "id,x\n1,10\n2,20\n3,30\n4,40\n"
	file, err := upload(base, "public.csv", csv, admin)
	if err != nil {
		return nil, err
	}
	meta, err := upload(base, "public.meta", "id,int,Public identifier\nx,float,Public feature\n", admin)
	if err != nil {
		return nil, err
	}
	r, err := post("data/create", map[string]interface{}{
		"name": "public-four-rows", "description": "Synthetic public recovery acceptance", "namespace": namespace,
		"filePath": file, "metaPath": meta, "fileVersion": "v1", "storageType": 1, "expireTime": time.Now().Add(24 * time.Hour).Unix(),
	})
	if err != nil {
		return nil, err
	}
	var created struct {
		ID         uint64 `json:"id"`
		ResourceID string `json:"resourceID"`
	}
	if json.Unmarshal(r.Data, &created) != nil || created.ID == 0 || created.ResourceID == "" {
		return nil, errors.New("public workflow invalid create result")
	}
	query := url.Values{"id": {strconv.FormatUint(created.ID, 10)}}
	var detail struct {
		Status int    `json:"status"`
		TxID   string `json:"tx_id"`
	}
	for i := 0; i < 60; i++ {
		r, err = request(base, "GET", "data/detail", query, nil, admin, 0, false)
		if err != nil || r.Code != "0" || json.Unmarshal(r.Data, &detail) != nil {
			return nil, errors.New("public workflow detail failed")
		}
		if detail.Status == 2 {
			break
		}
		if detail.Status == 4 || detail.Status == 5 || i == 59 {
			return nil, fmt.Errorf("public workflow storage failed (status %d)", detail.Status)
		}
		time.Sleep(time.Second)
	}
	if _, err = post("data/publish", map[string]uint64{"id": created.ID}); err != nil {
		return nil, err
	}
	r, err = request(base, "GET", "data/detail", query, nil, admin, 0, false)
	if err != nil || r.Code != "0" || json.Unmarshal(r.Data, &detail) != nil || detail.Status != 3 || detail.TxID == "" {
		return nil, errors.New("public workflow publish not confirmed")
	}
	r, err = request(base, "GET", "data/ns/resource/detail", url.Values{"resourceID": {created.ResourceID}}, nil, admin, 0, false)
	var catalog struct {
		FileID string `json:"fileID"`
		Rows   int    `json:"totalNumber"`
	}
	if err != nil || r.Code != "0" || json.Unmarshal(r.Data, &catalog) != nil || catalog.FileID != created.ResourceID || catalog.Rows != 4 {
		return nil, errors.New("public workflow on-chain catalog mismatch")
	}
	downloadQuery := "id=" + strconv.FormatUint(created.ID, 10) + "&type=data"
	req, _ := http.NewRequest("GET", strings.TrimRight(base, "/")+"/dtx/v1/data/download?"+downloadQuery, nil)
	if err = authorize(req, "id="+strconv.FormatUint(created.ID, 10)+"type=data", admin, 0, false); err != nil {
		return nil, err
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, errors.New("public workflow download failed")
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil || resp.StatusCode != 200 || !bytes.Equal(data, []byte(csv)) {
		return nil, errors.New("public workflow download content mismatch")
	}
	digest := sha256.Sum256(data)
	return map[string]interface{}{"pass": true, "namespace": namespace, "database_id": created.ID,
		"resource_id": created.ResourceID, "transaction_id": detail.TxID, "rows": 4,
		"storage": "manager-local", "download_sha256": hex.EncodeToString(digest[:]), "cross_org_authorization_checked": false}, nil
}

func login(base string, c credentials) (*identity, error) {
	wire := wirePassword(c.Password)
	r, err := request(base, "POST", "user/login", nil, map[string]string{"username": c.Username, "password": wire}, nil, 0, false)
	if err != nil || r.Code != "0" {
		return nil, errors.New("login failed")
	}
	var data struct {
		PrivateKey string `json:"privateKey"`
	}
	if json.Unmarshal(r.Data, &data) != nil {
		return nil, errors.New("invalid login response")
	}
	ciphertext, err := base64.StdEncoding.DecodeString(data.PrivateKey)
	if err != nil {
		return nil, errors.New("invalid encrypted login response")
	}
	plain, err := sdkcrypto.GetCryptoClient().DecryptByAESKey(string(ciphertext), wire)
	if err != nil {
		return nil, errors.New("login key decryption failed")
	}
	var key struct{ Curvname, X, Y, D string }
	if json.Unmarshal([]byte(plain), &key) != nil || key.Curvname != "P-256" {
		return nil, errors.New("invalid login key")
	}
	x, xok := new(big.Int).SetString(key.X, 10)
	y, yok := new(big.Int).SetString(key.Y, 10)
	d, dok := new(big.Int).SetString(key.D, 10)
	curve := elliptic.P256()
	if !xok || !yok || !dok || !curve.IsOnCurve(x, y) || d.Sign() <= 0 || d.Cmp(curve.Params().N) >= 0 {
		return nil, errors.New("invalid login key")
	}
	public, _ := json.Marshal(map[string]string{"Curvname": "P-256", "X": key.X, "Y": key.Y})
	return &identity{key: &ecdsa.PrivateKey{PublicKey: ecdsa.PublicKey{Curve: curve, X: x, Y: y}, D: d}, public: string(public)}, nil
}

func check(base, credentialsPath, probePath string) (map[string]interface{}, error) {
	adminCredentials, err := readCredentials(credentialsPath)
	if err != nil {
		return nil, err
	}
	admin, err := login(base, adminCredentials)
	if err != nil {
		return nil, err
	}
	checks := 1
	expect := func(label, method, path string, query url.Values, body interface{}, who *identity, offset int64, corrupt bool, code string) (response, error) {
		r, e := request(base, method, path, query, body, who, offset, corrupt)
		if e != nil || r.Code != code {
			return r, fmt.Errorf("%s failed (expected API code %s)", label, code)
		}
		checks++
		return r, nil
	}
	wrong := map[string]string{"username": adminCredentials.Username, "password": wirePassword(adminCredentials.Password + "-invalid")}
	if _, err = expect("wrong password", "POST", "user/login", nil, wrong, nil, 0, false, "ParamsErr"); err != nil {
		return nil, err
	}
	query := url.Values{"pageNo": {"1"}, "pageSize": {"20"}}
	totals := map[string]int{}
	for _, path := range []string{"data/list", "model/list", "task/list"} {
		if _, err = expect("anonymous "+path, "GET", path, query, nil, nil, 0, false, "SignErr"); err != nil {
			return nil, err
		}
		r, e := expect("admin "+path, "GET", path, query, nil, admin, 0, false, "0")
		if e != nil {
			return nil, e
		}
		var data struct {
			Total int               `json:"total"`
			List  []json.RawMessage `json:"list"`
		}
		if json.Unmarshal(r.Data, &data) != nil || data.List == nil {
			return nil, errors.New("invalid list response")
		}
		totals[path] = data.Total
	}
	for _, path := range []string{"data/download", "task/result/download", "algo/download"} {
		if _, err = expect("anonymous download", "GET", path, nil, nil, nil, 0, false, "SignErr"); err != nil {
			return nil, err
		}
	}
	missing := map[string]string{"username": "ppci-permission-boundary-missing-user"}
	if _, err = expect("anonymous password reset", "POST", "user/clearpwd", nil, missing, nil, 0, false, "SignErr"); err != nil {
		return nil, err
	}
	if _, err = expect("tampered signature", "GET", "data/list", query, nil, admin, 0, true, "SignErr"); err != nil {
		return nil, err
	}
	if _, err = expect("expired signature", "GET", "data/list", query, nil, admin, -301, false, "SignErr"); err != nil {
		return nil, err
	}
	if _, err = expect("future signature", "GET", "data/list", query, nil, admin, 60, false, "SignErr"); err != nil {
		return nil, err
	}
	if _, err = expect("admin user info", "GET", "user/info", nil, nil, admin, 0, false, "0"); err != nil {
		return nil, err
	}
	outside := map[string]interface{}{
		"name": "ppci-path-boundary", "description": "path boundary check", "namespace": "boundary",
		"filePath": "/nonexistent/ppci-outside-upload.csv", "metaPath": "/nonexistent/ppci-outside-upload.meta", "storageType": 1,
	}
	if _, err = expect("outside upload create", "POST", "data/create", nil, outside, admin, 0, false, "ParamsErr"); err != nil {
		return nil, err
	}
	outside["id"] = 1
	outside["fileVersion"] = "boundary"
	if _, err = expect("outside upload update", "POST", "data/update", nil, outside, admin, 0, false, "ParamsErr"); err != nil {
		return nil, err
	}
	if probePath != "" {
		c, e := readCredentials(probePath)
		if e != nil {
			return nil, e
		}
		probe, e := login(base, c)
		if e != nil {
			body := map[string]string{"username": c.Username, "password": wirePassword(c.Password)}
			if _, err = expect("probe registration", "POST", "user/register", nil, body, nil, 0, false, "0"); err != nil {
				return nil, err
			}
			probe, e = login(base, c)
			if e != nil {
				return nil, e
			}
		}
		checks++
		for _, path := range []string{"data/list", "model/list", "task/list"} {
			if _, err = expect("low privilege "+path, "GET", path, query, nil, probe, 0, false, "NoAuthority"); err != nil {
				return nil, err
			}
		}
		if _, err = expect("low privilege password reset", "POST", "user/clearpwd", nil, missing, probe, 0, false, "NoAuthority"); err != nil {
			return nil, err
		}
		if _, err = expect("probe user info", "GET", "user/info", nil, nil, probe, 0, false, "0"); err != nil {
			return nil, err
		}
	}
	return map[string]interface{}{"pass": true, "checks": checks, "list_totals": totals, "low_privilege_checked": probePath != ""}, nil
}

// chainTaskCheck never creates a probe account or writes business records.
func chainTaskCheck(base, credentialsPath, probePath, taskID, expectedExecutors string) (map[string]interface{}, error) {
	c, err := readCredentials(credentialsPath)
	if err != nil {
		return nil, err
	}
	admin, err := login(base, c)
	if err != nil {
		return nil, err
	}
	call := func(path string, q url.Values, who *identity, corrupt bool, code string) (response, error) {
		r, err := request(base, "GET", path, q, nil, who, 0, corrupt)
		if err != nil || r.Code != code {
			return r, fmt.Errorf("%s: expected %s, got %s", path, code, r.Code)
		}
		return r, nil
	}
	totals := map[string]int{}
	for _, path := range []string{"data/list", "model/list", "task/list"} {
		r, err := call(path, url.Values{"pageNo": {"1"}, "pageSize": {"20"}}, admin, false, "0")
		var data struct {
			Total int               `json:"total"`
			List  []json.RawMessage `json:"list"`
		}
		if err != nil || json.Unmarshal(r.Data, &data) != nil || data.List == nil {
			return nil, fmt.Errorf("%s: invalid management list", path)
		}
		totals[path] = data.Total
	}
	result := map[string]interface{}{"pass": true, "list_totals": totals}
	if taskID == "" {
		return result, nil
	}
	lowCredentials, err := readCredentials(probePath)
	if err != nil {
		return nil, err
	}
	low, err := login(base, lowCredentials)
	if err != nil {
		return nil, err
	}
	const path = "task/chain-detail"
	q := func(id string) url.Values { return url.Values{"chainTaskId": {id}} }
	for _, test := range []struct {
		id      string
		who     *identity
		corrupt bool
		code    string
	}{
		{taskID, nil, false, "SignErr"},
		{taskID, admin, true, "SignErr"},
		{taskID, low, false, "NoAuthority"},
		{"invalid", admin, false, "ParamsErr"},
		{"00000000-0000-0000-0000-000000000000", admin, false, "TaskNotExisted"},
	} {
		r, err := call(path, q(test.id), test.who, test.corrupt, test.code)
		payload := string(bytes.TrimSpace(r.Data))
		if err != nil || (payload != "" && payload != "null" && payload != "{}") {
			return nil, fmt.Errorf("chain query rejection check failed (expected %s): %v", test.code, err)
		}
	}
	r, err := call(path, q(taskID), admin, false, "0")
	if err != nil {
		return nil, err
	}
	var summary struct {
		TaskID    string `json:"taskId"`
		Status    string `json:"status"`
		EndTime   int64  `json:"endTime"`
		Executors []struct {
			Name    string `json:"name"`
			ModelID string `json:"modelId"`
		} `json:"executors"`
	}
	var fields map[string]json.RawMessage
	if json.Unmarshal(r.Data, &summary) != nil || json.Unmarshal(r.Data, &fields) != nil ||
		summary.TaskID != taskID || summary.Status != "Finished" || summary.EndTime <= 0 || len(summary.Executors) != 2 {
		return nil, errors.New("chain query did not return the expected completed two-executor task")
	}
	for key := range fields {
		switch key {
		case "taskId", "name", "status", "publishTime", "startTime", "endTime", "executors":
		default:
			return nil, errors.New("chain summary exposed an unexpected field")
		}
	}
	names := []string{summary.Executors[0].Name, summary.Executors[1].Name}
	sort.Strings(names)
	want := strings.Split(expectedExecutors, ",")
	for i := range want {
		want[i] = strings.TrimSpace(want[i])
	}
	sort.Strings(want)
	if len(want) != 2 || want[0] == "" || want[0] == want[1] || names[0] != want[0] || names[1] != want[1] {
		return nil, errors.New("chain query did not resolve the two expected executor names")
	}
	result["task_id"] = summary.TaskID
	result["status"] = summary.Status
	result["executors"] = names
	models := map[string]string{}
	for _, executor := range summary.Executors {
		if executor.ModelID != "" {
			models[executor.Name] = executor.ModelID
		}
	}
	result["model_ids"] = models
	result["rejection_checks"] = 5
	return result, nil
}

func main() {
	base := flag.String("base-url", "http://127.0.0.1:8084", "local manager URL")
	credentialsPath := flag.String("credentials", "/srv/ppci/dtx-manager/private/credentials.json", "private server-local admin credentials")
	probe := flag.String("probe-credentials", "", "private server-local probe credentials; creates that low privilege account if absent")
	public := flag.Bool("public-workflow", false, "create and publish a new synthetic four-row CSV and verify signed download")
	chainTask := flag.String("chain-task-id", "", "read-only verification of a finished Alice chain task")
	chainBaseline := flag.Bool("chain-baseline", false, "read-only manager list totals before a chain task UI release")
	executors := flag.String("expected-executors", "executor1,executor2", "comma-separated registered executor names for chain task verification")
	flag.Parse()
	if *chainBaseline || *chainTask != "" {
		if *public || (*chainBaseline && *chainTask != "") {
			fmt.Fprintln(os.Stderr, "choose one read-only chain verification mode")
			os.Exit(2)
		}
		result, err := chainTaskCheck(*base, *credentialsPath, *probe, *chainTask, *executors)
		if err != nil {
			fmt.Fprintln(os.Stderr, "chain task check:", err)
			os.Exit(1)
		}
		json.NewEncoder(os.Stdout).Encode(result)
		return
	}
	result, err := check(*base, *credentialsPath, *probe)
	if err != nil {
		fmt.Fprintln(os.Stderr, "manager check:", err)
		os.Exit(1)
	}
	if *public {
		workflow, e := publicWorkflow(*base, *credentialsPath)
		if e != nil {
			fmt.Fprintln(os.Stderr, "manager public workflow:", e)
			os.Exit(1)
		}
		result["public_workflow"] = workflow
	}
	data, _ := json.Marshal(result)
	fmt.Println(string(data))
}
