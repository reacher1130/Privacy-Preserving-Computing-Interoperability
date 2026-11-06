# BFIA 端到端全流程打通实现计划

> **目标：** 从 SecretPad 页面切换 BFIA 协议 → 建立连接 → 添加数据 → 拖拉拽算法 → 运行 → 查看结果，实现 Alice↔Bob 端到端全流程。

**架构：** Kuscia 容器同时启动 BFIA(8084) 和原生(8083) 两套协议服务。SecretPad 通过 `port`(8083) 走 gRPC 管理数据源，通过 `httpPort`(8084) 走 HTTP 提交/查询 BFIA 作业。修复 `BfiaJobConverter` 数据引用、`BfiaFlowServiceImpl` 作业持久化与状态同步。

**技术栈：** Java 17 + Spring Boot 3 + JPA + H2/MySQL

---

## 关键发现

1. **Kuscia 已支持 BFIA 全套接口**：`/v1/interconn/schedule/job/create|stop|start|status_all`，无需改 Kuscia
2. **协议不可热切换的是 DomainRoute 层面**，单个容器同时运行两套协议
3. **核心缺陷 3 个**：
   - `BfiaJobConverter.hostDataRef()/guestDataRef()` 返回空 Map → 算法插件找不到数据
   - `BfiaFlowServiceImpl.startGraph()` 未持久化作业记录 → 状态查询永远返回空
   - 无作业状态轮询 → 前端 DAG 节点状态无法刷新

## 文件结构

### 需要修改的文件

| 文件 | 责任 |
|------|------|
| `BfiaDatasetDO.java` | 扩展字段：namespace, fileName, fieldNames, hasLabel, rowCount |
| `BfiaDatasetVO.java` | 对应扩展 VO 字段 |
| `V3__bfia_dataset_and_flow.sql` | 增加 ALTER TABLE 添加新列 |
| `BfiaJobConverter.java` | 实现 hostDataRef/guestDataRef，修复多任务覆盖 |
| `BfiaFlowServiceImpl.java` | startGraph 持久化 ProjectJobDO/ProjectTaskDO |
| `BfiaFlowController.java` | 新增 job status 查询接口 |
| `BfiaInterconnClient.java` | 新增 queryJobStatus 方法 |

### 需要新建的文件

| 文件 | 责任 |
|------|------|
| `BfiaJobStatusSyncService.java` | 定时轮询 BFIA 作业状态，更新数据库 |
| `V4__bfia_dataset_extend.sql` | Flyway 迁移：扩展 bfia_dataset 表 |

---

## Task 1: 扩展 BfiaDatasetDO 数据模型

**目的：** 让数据集实体存储 BFIA 协议必需的物理文件名、命名空间、求交主键等字段。

**Files:**
- Modify: `secretpad/secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaDatasetDO.java`
- Create: `secretpad/secretpad-persistence/src/main/resources/db/bfia/V4__bfia_dataset_extend.sql`

### 步骤

- [ ] **Step 1: 创建 Flyway 迁移脚本**

```sql
-- V4__bfia_dataset_extend.sql
ALTER TABLE bfia_dataset ADD COLUMN namespace VARCHAR(64) DEFAULT 'data';
ALTER TABLE bfia_dataset ADD COLUMN file_name VARCHAR(256);
ALTER TABLE bfia_dataset ADD COLUMN field_names VARCHAR(256);
ALTER TABLE bfia_dataset ADD COLUMN has_label BOOLEAN DEFAULT FALSE;
ALTER TABLE bfia_dataset ADD COLUMN row_count BIGINT DEFAULT 0;
```

- [ ] **Step 2: 扩展 BfiaDatasetDO 实体**

```java
@Column(name = "namespace", length = 64)
private String namespace;

@Column(name = "file_name", length = 256)
private String fileName;

@Column(name = "field_names", length = 256)
private String fieldNames;

@Column(name = "has_label")
private Boolean hasLabel;

@Column(name = "row_count")
private Long rowCount;
```

- [ ] **Step 3: 扩展 BfiaDatasetVO**

在 `BfiaDatasetVO.java` 中添加对应字段。

---

## Task 2: 修复 BfiaJobConverter 数据引用

**目的：** 让 `hostDataRef()/guestDataRef()` 从图节点配置中提取数据集信息，组装成 BFIA 期望的 `{name, namespace, field_names}` 结构。

**Files:**
- Modify: `secretpad/secretpad-service/src/main/java/org/secretflow/secretpad/service/graph/converter/BfiaJobConverter.java`

### 数据流

前端画布配置节点时，将 host/guest 的 `datasetId` 写入 `nodeDef.attrs`。`BfiaJobConverter` 从 `GraphNodeInfo.nodeDef` 中提取 `datasetId`，查 `BfiaDatasetRepository` 获取完整信息。

### 步骤

- [ ] **Step 1: 注入 BfiaDatasetRepository**

```java
@Component
@RequiredArgsConstructor
public class BfiaJobConverter {
    private final ObjectProvider<BfiaDatasetRepository> datasetRepositoryProvider;
    // ...
}
```

- [ ] **Step 2: 实现 hostDataRef/guestDataRef**

从 `node.nodeDef.attrs` 中提取 `host_dataset_id` / `guest_dataset_id`，查库后组装：

```java
private Map<String, Object> hostDataRef(GraphNodeInfo node, String compName) {
    String datasetId = extractAttr(node, "host_dataset_id");
    if (datasetId == null) {
        // fallback: 使用 node.inputs
        if (!CollectionUtils.isEmpty(node.getInputs())) {
            datasetId = node.getInputs().get(0);
        }
    }
    return buildDataRef(datasetId, compName);
}

private Map<String, Object> buildDataRef(String datasetId, String compName) {
    Map<String, Object> ref = new LinkedHashMap<>();
    if (datasetId == null) return ref;
    
    BfiaDatasetRepository repo = datasetRepositoryProvider.getIfAvailable();
    if (repo == null) return ref;
    
    BfiaDatasetDO ds = repo.findById(datasetId).orElse(null);
    if (ds == null) return ref;
    
    ref.put("name", ds.getFileName() != null ? ds.getFileName() : ds.getName());
    ref.put("namespace", ds.getNamespace() != null ? ds.getNamespace() : "data");
    
    // PSI 需要求交主键
    if (ds.getFieldNames() != null && !ds.getFieldNames().isEmpty()) {
        ref.put("field_names", ds.getFieldNames());
    }
    // SS-LR/XGB 需要 has_label
    if (ds.getHasLabel() != null) {
        ref.put("has_label", ds.getHasLabel());
    }
    return ref;
}
```

- [ ] **Step 3: 修复多任务 task_params 覆盖问题**

将 `taskParamsHost.put("0", ...)` 改为 merge：

```java
// 修改前：taskParamsHost.put("0", indexed(compName, hostParams));
// 修改后：
Map<String, Object> host0 = (Map<String, Object>) taskParamsHost.computeIfAbsent("0", k -> new LinkedHashMap<>());
host0.putAll(indexed(compName, hostParams));
```

- [ ] **Step 4: 修复 dag.components[].input 为空数组**

```java
// 从 node.getInputs() 构造 input
List<Map<String, Object>> inputs = new ArrayList<>();
if (!CollectionUtils.isEmpty(node.getInputs())) {
    for (String inputKey : node.getInputs()) {
        Map<String, Object> io = new LinkedHashMap<>();
        io.put("type", "dataset");
        io.put("key", inputKey);
        inputs.add(io);
    }
}
comp.put("input", inputs);
```

---

## Task 3: 持久化 BFIA 作业记录

**目的：** `startGraph()` 提交作业后持久化 `ProjectJobDO` 和 `ProjectTaskDO`，让状态查询有数据可读。

**Files:**
- Modify: `secretpad/secretpad-service/src/main/java/org/secretflow/secretpad/service/impl/bfia/BfiaFlowServiceImpl.java`

### 步骤

- [ ] **Step 1: 注入 JobRepository 和 TaskRepository**

```java
private final ObjectProvider<JobRepository> jobRepositoryProvider;
private final ObjectProvider<TaskRepository> taskRepositoryProvider;
```

- [ ] **Step 2: 在 startGraph 中持久化作业记录**

提交成功后，将 `ProjectJob` 转为 `ProjectJobDO` 保存：

```java
// 在 verifyResponse(responseBody) 之后添加
persistJobRecords(job, initiatorId);
```

```java
private void persistJobRecords(ProjectJob job, String initiatorId) {
    JobRepository jobRepo = jobRepositoryProvider.getIfAvailable();
    TaskRepository taskRepo = taskRepositoryProvider.getIfAvailable();
    if (jobRepo == null || taskRepo == null) return;
    
    // 保存 ProjectJobDO
    ProjectJobDO jobDO = ProjectJobDO.builder()
        .jobId(job.getJobId())
        .graphId(job.getGraphId())
        .projectId(job.getProjectId())
        .status("RUNNING")
        .build();
    jobRepo.save(jobDO);
    
    // 保存每个 ProjectTaskDO
    for (ProjectJob.JobTask task : job.getTasks()) {
        ProjectTaskDO taskDO = ProjectTaskDO.builder()
            .taskId(UUID.randomUUID().toString().replaceAll("-", ""))
            .jobId(job.getJobId())
            .graphNodeId(task.getNode().getGraphNodeId())
            .status("STAGING")
            .build();
        taskRepo.save(taskDO);
    }
}
```

---

## Task 4: 实现 BFIA 作业状态轮询

**目的：** 定时查询 Kuscia 8084 端口的 `job/status_all`，更新数据库中的作业/任务状态。

**Files:**
- Create: `secretpad/secretpad-service/src/main/java/org/secretflow/secretpad/service/impl/bfia/BfiaJobStatusSyncService.java`
- Modify: `secretpad/secretpad-service/src/main/java/org/secretflow/secretpad/service/bfia/BfiaInterconnClient.java`

### 步骤

- [ ] **Step 1: 在 BfiaInterconnClient 添加 queryJobStatus 方法**

```java
public Map<String, Object> queryJobStatus(String initiatorId, String jobId) {
    String url = resolveJobStatusUrl(initiatorId);
    Map<String, Object> body = new HashMap<>();
    body.put("job_id", jobId);
    String resp = RestTemplateUtil.sendPostJson(url, body, new HashMap<>(), String.class);
    return JsonUtils.toJavaMap(resp);
}

private String resolveJobStatusUrl(String initiatorId) {
    // 复用 resolveJobCreateUrl 逻辑，路径改为 /v1/interconn/schedule/job/status_all
    KusciaGrpcConfig target = findNode(initiatorId);
    return "http://" + target.getHost() + ":" + target.getHttpPort() + "/v1/interconn/schedule/job/status_all";
}
```

- [ ] **Step 2: 创建 BfiaJobStatusSyncService**

```java
@Slf4j
@Service
@RequiredArgsConstructor
@ConditionalOnBean(BfiaInterconnClient.class)
public class BfiaJobStatusSyncService {
    private final ObjectProvider<JobRepository> jobRepoProvider;
    private final ObjectProvider<TaskRepository> taskRepoProvider;
    private final BfiaInterconnClient bfiaInterconnClient;
    
    @Scheduled(fixedDelay = 5000)
    public void syncBfiaJobStatus() {
        JobRepository jobRepo = jobRepoProvider.getIfAvailable();
        if (jobRepo == null) return;
        
        // 查询所有 RUNNING 状态的作业
        List<ProjectJobDO> runningJobs = jobRepo.findByStatus("RUNNING");
        for (ProjectJobDO job : runningJobs) {
            try {
                Map<String, Object> resp = bfiaInterconnClient.queryJobStatus(
                    job.getInitiatorId(), job.getJobId());
                updateJobStatus(job, resp);
            } catch (Exception e) {
                log.warn("Failed to sync BFIA job status: jobId={}", job.getJobId(), e);
            }
        }
    }
    
    private void updateJobStatus(ProjectJobDO job, Map<String, Object> resp) {
        Map<String, Object> data = (Map<String, Object>) resp.get("data");
        if (data == null) return;
        
        String jobStatus = (String) data.get("jobStatus");
        Map<String, String> taskStatus = (Map<String, String>) data.get("status");
        
        // 更新任务状态
        TaskRepository taskRepo = taskRepoProvider.getIfAvailable();
        if (taskRepo != null && taskStatus != null) {
            for (Map.Entry<String, String> e : taskStatus.entrySet()) {
                List<ProjectTaskDO> tasks = taskRepo.findByJobIdAndGraphNodeId(
                    job.getJobId(), e.getKey());
                for (ProjectTaskDO t : tasks) {
                    t.setStatus(mapBfiaStatus(e.getValue()));
                    taskRepo.save(t);
                }
            }
        }
        
        // 更新作业状态
        if (jobStatus != null) {
            job.setStatus(mapBfiaStatus(jobStatus));
            jobRepoProvider.getIfAvailable().save(job);
        }
    }
    
    private String mapBfiaStatus(String bfiaStatus) {
        return switch (bfiaStatus.toUpperCase()) {
            case "PENDING" -> "STAGING";
            case "RUNNING" -> "RUNNING";
            case "SUCCESS" -> "SUCCEED";
            case "FAILED" -> "FAILED";
            default -> "STAGING";
        };
    }
}
```

- [ ] **Step 3: 在启动类添加 @EnableScheduling**

确保 SecretPad 启动类已有 `@EnableScheduling`，若没有则添加。

---

## Task 5: 结果同步

**目的：** 作业成功后通过 KusciaAPI gRPC 查询 DomainData，写入 project_result 表。

### 步骤

- [ ] **Step 1: 在 BfiaJobStatusSyncService 中，当任务状态变为 SUCCESS 时触发结果同步**

复用 `JobManager.syncResult()` 的逻辑，通过 KusciaAPI gRPC `Domaindata.QueryDomainData` 查询产出数据。BFIA 作业的输出 DomainData ID 格式为 `{jobId}-{taskName}-result`。

```java
// 在 updateJobStatus 中，当 taskStatus 变为 SUCCESS 时
if ("SUCCEED".equals(mappedStatus)) {
    syncTaskResult(job, graphNodeId);
}
```

---

## Task 6: 端到端测试验证

### 步骤

- [ ] **Step 1: 重新编译 SecretPad**

```bash
cd NewProject/secretpad
mvn clean package -DskipTests -pl secretpad-web -am
```

- [ ] **Step 2: 重建 SecretPad Docker 镜像**

- [ ] **Step 3: 在 Alice 端 SecretPad 页面操作**
  1. 切换到 BFIA 协议
  2. 添加数据集（alice.csv，namespace=data，field_names=id1）
  3. 创建项目
  4. 拖拽 ecdh-psi 组件
  5. 配置 host 数据集
  6. 启动作业
  7. 查看状态刷新
  8. 查看结果

- [ ] **Step 4: 在 Bob 端重复操作**
  1. 添加数据集（bob.csv，namespace=data，field_names=id2）
  2. 接受项目邀请
  3. 配置 guest 数据集

- [ ] **Step 5: 验证 6 个算法全部跑通**
  - ecdh-psi
  - ss-lr
  - ss-xgb
  - ss-pearson
  - ss-vif
  - ss-compare

---

## 风险与注意事项

1. **前端数据集绑定**：前端在画布配置节点时需要将 `datasetId` 写入 `nodeDef.attrs` 的 `host_dataset_id`/`guest_dataset_id`。如果前端尚未实现，需要同步修改前端组件配置面板。

2. **跨节点场景**：当前计划主要面向单 SecretPad 管理 alice+bob 的场景。若 alice 和 bob 各有独立 SecretPad，需要确保 `BfiaInterconnClient` 跨节点传播正常。

3. **H2 vs MySQL**：开发环境用 H2，生产用 MySQL。Flyway 脚本需兼容两者。

4. **状态同步性能**：5秒轮询频率对大量作业可能有压力，可根据实际情况调整。
