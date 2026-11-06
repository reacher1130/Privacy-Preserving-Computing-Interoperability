# BFIA 协议数据完全隔离实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 BFIA 协议的节点、流程图、任务、结果数据从隐语原生的共用表中完全独立出来，实现两套协议数据的物理隔离。

**Architecture:** 为 BFIA 新建 4 张独立表（bfia_node / bfia_graph / bfia_job / bfia_result），每张表配套独立的 Entity、Repository、Service、Controller。BFIA 前端所有 API 调用走 `/api/v1bfia/*` 路径，不再触碰标准 `/api/v1alpha1/*` 路径。项目（bfia_project）和数据集（bfia_dataset）已独立，无需改动。

**Tech Stack:** Java 17 + Spring Boot + JPA/Hibernate + H2/SQLite + React + UmiJS

---

## 文件结构

### 新建文件（后端 persistence 层）
- `secretpad-persistence/.../entity/bfia/BfiaNodeDO.java` — BFIA 节点实体
- `secretpad-persistence/.../entity/bfia/BfiaGraphDO.java` — BFIA 流程图实体
- `secretpad-persistence/.../entity/bfia/BfiaGraphNodeDO.java` — BFIA 图节点实体
- `secretpad-persistence/.../entity/bfia/BfiaJobDO.java` — BFIA 任务实体
- `secretpad-persistence/.../entity/bfia/BfiaResultDO.java` — BFIA 结果实体
- `secretpad-persistence/.../repository/bfia/BfiaNodeRepository.java`
- `secretpad-persistence/.../repository/bfia/BfiaGraphRepository.java`
- `secretpad-persistence/.../repository/bfia/BfiaJobRepository.java`
- `secretpad-persistence/.../repository/bfia/BfiaResultRepository.java`

### 新建文件（后端 service 层）
- `secretpad-service/.../service/bfia/BfiaNodeService.java` + `impl/bfia/BfiaNodeServiceImpl.java`
- `secretpad-service/.../service/bfia/BfiaGraphService.java` + `impl/bfia/BfiaGraphServiceImpl.java`
- `secretpad-service/.../service/bfia/BfiaResultService.java` + `impl/bfia/BfiaResultServiceImpl.java`

### 修改文件（后端 controller 层）
- `secretpad-web/.../controller/bfia/BfiaNodeController.java` — 改为查 BfiaNodeRepository
- `secretpad-web/.../controller/bfia/BfiaFlowController.java` — graph CRUD 改为调 BfiaGraphService
- `secretpad-web/.../controller/bfia/BfiaDataController.java` — 无需改（数据集已独立）
- 新建 `secretpad-web/.../controller/bfia/BfiaResultController.java`

### 修改文件（后端 service 层）
- `secretpad-service/.../service/impl/bfia/BfiaFlowServiceImpl.java` — startGraph 改用 BfiaGraphRepository 读写，job 持久化改写 BfiaJobRepository

### 修改文件（前端）
- `secretpad-frontend/apps/platform/src/pages/edge.tsx` — 确认 BFIA 菜单项的 API 路径
- `secretpad-frontend/apps/platform/src/modules/record/` — BFIA 结果管理调用 /api/v1bfia/result/*

---

## Task 1: BfiaNodeDO — BFIA 独立节点表

**Files:**
- Create: `secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaNodeDO.java`
- Create: `secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/repository/bfia/BfiaNodeRepository.java`
- Modify: `secretpad-web/src/main/java/org/secretflow/secretpad/web/controller/bfia/BfiaNodeController.java`

- [ ] **Step 1: 创建 BfiaNodeDO 实体**

文件：`secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaNodeDO.java`

```java
package org.secretflow.secretpad.persistence.entity.bfia;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.*;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.Where;
import org.secretflow.secretpad.persistence.entity.BaseAggregationRoot;

@Builder
@Entity
@NoArgsConstructor
@AllArgsConstructor
@ToString
@Setter
@Getter
@Table(name = "bfia_node")
@SQLDelete(sql = "update bfia_node set is_deleted = 1 where node_id = ?")
@Where(clause = "is_deleted = 0")
public class BfiaNodeDO extends BaseAggregationRoot<BfiaNodeDO> {

    @Id
    @Column(name = "node_id", unique = true, nullable = false, length = 64)
    private String nodeId;

    @Column(name = "name", nullable = false, length = 256)
    private String name;

    @Column(name = "net_address", length = 200)
    private String netAddress;

    @Column(name = "pad_address", length = 200)
    private String padAddress;

    @Column(name = "inst_id", length = 64)
    private String instId;

    @Column(name = "status", length = 32)
    private String status;

    @Column(name = "description", columnDefinition = "text")
    private String description;

    @Override
    public String getProjectId() {
        return null;
    }
}
```

- [ ] **Step 2: 创建 BfiaNodeRepository**

文件：`secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/repository/bfia/BfiaNodeRepository.java`

```java
package org.secretflow.secretpad.persistence.repository.bfia;

import org.secretflow.secretpad.persistence.entity.bfia.BfiaNodeDO;
import org.secretflow.secretpad.persistence.repository.BaseRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface BfiaNodeRepository extends BaseRepository<BfiaNodeDO, String> {
}
```

- [ ] **Step 3: 修改 BfiaNodeController 改为查 BfiaNodeRepository**

文件：`secretpad-web/src/main/java/org/secretflow/secretpad/web/controller/bfia/BfiaNodeController.java`

将 `listApproved()` 和 `listNode()` 方法中的 `nodeRepository.findAll()` 改为 `bfiaNodeRepository.findAll()`。移除对 `NodeRepository` 和 `NodeDO` 的依赖，改用 `BfiaNodeRepository` 和 `BfiaNodeDO`。

`toNodeVO` 方法改为接收 `BfiaNodeDO`：
```java
private NodeVO toNodeVO(BfiaNodeDO do_) {
    NodeVO vo = new NodeVO();
    vo.setNodeId(do_.getNodeId());
    vo.setNodeName(do_.getName());
    vo.setName(do_.getName());
    vo.setContractId(do_.getNodeId());
    vo.setNetAddress(do_.getNetAddress());
    return vo;
}
```

注入改为：
```java
private final BfiaNodeRepository bfiaNodeRepository;
private final BfiaContractRepository bfiaContractRepository;
```

`listApproved()` 改为：
```java
String ownerId = UserContext.getUser().getOwnerId();
List<BfiaNodeDO> allNodes = bfiaNodeRepository.findAll();
List<NodeVO> nodes = allNodes.stream()
        .map(this::toNodeVO)
        .filter(n -> !ownerId.equals(n.getNodeId()))
        .collect(Collectors.toList());
```

`listNode()` 改为：
```java
List<NodeVO> nodes = bfiaNodeRepository.findAll().stream()
        .map(this::toNodeVO)
        .collect(Collectors.toList());
```

- [ ] **Step 4: 编译验证**

```bash
cd secretpad && mvn compile -pl secretpad-persistence,secretpad-web -am -DskipTests -q
```
Expected: BUILD SUCCESS

- [ ] **Step 5: Commit**

```bash
git add secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaNodeDO.java \
  secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/repository/bfia/BfiaNodeRepository.java \
  secretpad-web/src/main/java/org/secretflow/secretpad/web/controller/bfia/BfiaNodeController.java
git commit -m "feat(bfia): add independent bfia_node table for protocol isolation"
```

---

## Task 2: BfiaGraphDO — BFIA 独立流程图表

**Files:**
- Create: `secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaGraphDO.java`
- Create: `secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaGraphNodeDO.java`
- Create: `secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/repository/bfia/BfiaGraphRepository.java`
- Create: `secretpad-service/src/main/java/org/secretflow/secretpad/service/bfia/BfiaGraphService.java`
- Create: `secretpad-service/src/main/java/org/secretflow/secretpad/service/impl/bfia/BfiaGraphServiceImpl.java`

- [ ] **Step 1: 创建 BfiaGraphNodeDO（图节点子实体）**

文件：`secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaGraphNodeDO.java`

```java
package org.secretflow.secretpad.persistence.entity.bfia;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.Where;

import java.io.Serial;
import java.io.Serializable;

@Getter
@Setter
@Builder
@AllArgsConstructor
@NoArgsConstructor
@ToString
@Entity
@Table(name = "bfia_graph_node")
@SQLDelete(sql = "update bfia_graph_node set is_deleted = 1 where graph_node_id = ?")
@Where(clause = "is_deleted = 0")
public class BfiaGraphNodeDO {
    @EmbeddedId
    private UPK upk;

    @Column(name = "graph_node_name")
    private String graphNodeName;

    @Column(name = "node_def_id", length = 128)
    private String nodeDefId;

    @Column(name = "params", columnDefinition = "text")
    private String params;

    @Getter
    @Setter
    @AllArgsConstructor
    @NoArgsConstructor
    @EqualsAndHashCode
    @ToString
    @Embeddable
    public static class UPK implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;
        @Column(name = "project_id", nullable = false, length = 64)
        private String projectId;
        @Column(name = "graph_id", nullable = false, length = 64)
        private String graphId;
        @Column(name = "graph_node_id", nullable = false, length = 64)
        private String graphNodeId;
    }
}
```

- [ ] **Step 2: 创建 BfiaGraphDO（流程图主实体）**

文件：`secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaGraphDO.java`

```java
package org.secretflow.secretpad.persistence.entity.bfia;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.Where;
import org.secretflow.secretpad.persistence.entity.BaseAggregationRoot;

import java.io.Serial;
import java.io.Serializable;
import java.util.List;

@Getter
@Setter
@Builder
@AllArgsConstructor
@NoArgsConstructor
@Entity
@ToString
@Table(name = "bfia_graph")
@SQLDelete(sql = "update bfia_graph set is_deleted = 1 where project_id = ? and graph_id = ?")
@Where(clause = "is_deleted = 0")
public class BfiaGraphDO extends BaseAggregationRoot<BfiaGraphDO> {
    @EmbeddedId
    private UPK upk;

    @Column(name = "name")
    private String name;

    @Column(name = "edges", columnDefinition = "text")
    private String edges;

    @OneToMany(fetch = FetchType.EAGER, cascade = CascadeType.ALL, orphanRemoval = true)
    @JoinColumns(value = {
            @JoinColumn(name = "project_id", referencedColumnName = "project_id", nullable = false, updatable = false, insertable = false),
            @JoinColumn(name = "graph_id", referencedColumnName = "graph_id", nullable = false, updatable = false, insertable = false)
    })
    private List<BfiaGraphNodeDO> nodes;

    @Column(name = "owner_id", length = 64)
    private String ownerId;

    @Column(name = "max_parallelism")
    private Integer maxParallelism;

    @Override
    public String getProjectId() {
        return this.upk.projectId;
    }

    @Getter
    @Setter
    @AllArgsConstructor
    @NoArgsConstructor
    @EqualsAndHashCode
    @ToString
    @Embeddable
    public static class UPK implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;
        @Column(name = "project_id", nullable = false, length = 64)
        private String projectId;
        @Column(name = "graph_id", nullable = false, length = 64)
        private String graphId;
    }
}
```

- [ ] **Step 3: 创建 BfiaGraphRepository**

文件：`secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/repository/bfia/BfiaGraphRepository.java`

```java
package org.secretflow.secretpad.persistence.repository.bfia;

import org.secretflow.secretpad.persistence.entity.bfia.BfiaGraphDO;
import org.secretflow.secretpad.persistence.repository.BaseRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface BfiaGraphRepository extends BaseRepository<BfiaGraphDO, BfiaGraphDO.UPK> {
    @Query("from BfiaGraphDO g where g.upk.projectId = :projectId")
    List<BfiaGraphDO> findByProjectId(@Param("projectId") String projectId);
}
```

- [ ] **Step 4: 创建 BfiaGraphService 接口**

文件：`secretpad-service/src/main/java/org/secretflow/secretpad/service/bfia/BfiaGraphService.java`

```java
package org.secretflow.secretpad.service.bfia;

import org.secretflow.secretpad.persistence.entity.bfia.BfiaGraphDO;
import org.secretflow.secretpad.service.model.graph.*;

import java.util.List;

public interface BfiaGraphService {
    CreateGraphVO createGraph(CreateGraphRequest request);
    void fullUpdateGraph(FullUpdateGraphRequest request);
    GraphDetailVO getGraphDetail(GetGraphRequest request);
    List<GraphMetaVO> listGraph(ListGraphRequest request);
    void deleteGraph(DeleteGraphRequest request);
    void updateGraphNode(UpdateGraphNodeRequest request);
    BfiaGraphDO getGraphDO(String projectId, String graphId);
}
```

- [ ] **Step 5: 创建 BfiaGraphServiceImpl 实现**

文件：`secretpad-service/src/main/java/org/secretflow/secretpad/service/impl/bfia/BfiaGraphServiceImpl.java`

实现所有 CRUD 方法，操作 BfiaGraphRepository 而非 ProjectGraphRepository。将 GraphNode/GraphEdge 转换为 BfiaGraphNodeDO。关键方法：

```java
package org.secretflow.secretpad.service.impl.bfia;

import org.secretflow.secretpad.common.util.UserContext;
import org.secretflow.secretpad.common.util.UUIDUtils;
import org.secretflow.secretpad.persistence.entity.bfia.BfiaGraphDO;
import org.secretflow.secretpad.persistence.entity.bfia.BfiaGraphNodeDO;
import org.secretflow.secretpad.persistence.repository.bfia.BfiaGraphRepository;
import org.secretflow.secretpad.service.bfia.BfiaGraphService;
import org.secretflow.secretpad.service.model.graph.*;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.CollectionUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class BfiaGraphServiceImpl implements BfiaGraphService {

    private final BfiaGraphRepository bfiaGraphRepository;

    @Override
    @Transactional
    public CreateGraphVO createGraph(CreateGraphRequest request) {
        String projectId = request.getProjectId();
        String graphId = UUIDUtils.random(8);
        String ownerId = UserContext.getUser().getOwnerId();
        BfiaGraphDO graphDO = BfiaGraphDO.builder()
                .upk(new BfiaGraphDO.UPK(projectId, graphId))
                .name(request.getName())
                .ownerId(ownerId)
                .maxParallelism(1)
                .build();
        if (!CollectionUtils.isEmpty(request.getNodes())) {
            graphDO.setNodes(request.getNodes().stream()
                    .map(n -> toGraphNodeDO(projectId, graphId, n))
                    .collect(Collectors.toList()));
        }
        if (!CollectionUtils.isEmpty(request.getEdges())) {
            graphDO.setEdges(toEdgesJson(request.getEdges()));
        }
        bfiaGraphRepository.save(graphDO);
        return CreateGraphVO.builder().graphId(graphId).build();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void fullUpdateGraph(FullUpdateGraphRequest request) {
        BfiaGraphDO.UPK upk = new BfiaGraphDO.UPK(request.getProjectId(), request.getGraphId());
        Optional<BfiaGraphDO> opt = bfiaGraphRepository.findById(upk);
        if (opt.isEmpty()) {
            // 不存在则创建
            BfiaGraphDO graphDO = BfiaGraphDO.builder()
                    .upk(upk)
                    .name(request.getGraphId())
                    .ownerId(UserContext.getUser().getOwnerId())
                    .maxParallelism(1)
                    .build();
            applyNodesAndEdges(graphDO, request);
            bfiaGraphRepository.save(graphDO);
            return;
        }
        BfiaGraphDO graphDO = opt.get();
        applyNodesAndEdges(graphDO, request);
        if (request.getMaxParallelism() != null) {
            graphDO.setMaxParallelism(request.getMaxParallelism());
        }
        bfiaGraphRepository.save(graphDO);
    }

    private void applyNodesAndEdges(BfiaGraphDO graphDO, FullUpdateGraphRequest request) {
        if (request.getNodes() != null) {
            if (graphDO.getNodes() != null) {
                graphDO.getNodes().clear();
            } else {
                graphDO.setNodes(new ArrayList<>());
            }
            graphDO.getNodes().addAll(request.getNodes().stream()
                    .map(n -> toGraphNodeDO(graphDO.getUpk().getProjectId(), graphDO.getUpk().getGraphId(), n))
                    .collect(Collectors.toList()));
        }
        if (request.getEdges() != null) {
            graphDO.setEdges(toEdgesJson(request.getEdges()));
        }
    }

    @Override
    public GraphDetailVO getGraphDetail(GetGraphRequest request) {
        BfiaGraphDO graphDO = getGraphDO(request.getProjectId(), request.getGraphId());
        return BfiaGraphToVOConverter.convert(graphDO);
    }

    @Override
    public List<GraphMetaVO> listGraph(ListGraphRequest request) {
        List<BfiaGraphDO> list = bfiaGraphRepository.findByProjectId(request.getProjectId());
        if (CollectionUtils.isEmpty(list)) {
            return new ArrayList<>();
        }
        return list.stream().map(g -> GraphMetaVO.builder()
                .graphId(g.getUpk().getGraphId())
                .projectId(g.getUpk().getProjectId())
                .name(g.getName())
                .build()).collect(Collectors.toList());
    }

    @Override
    public void deleteGraph(DeleteGraphRequest request) {
        bfiaGraphRepository.deleteById(new BfiaGraphDO.UPK(request.getProjectId(), request.getGraphId()));
    }

    @Override
    public void updateGraphNode(UpdateGraphNodeRequest request) {
        // 简化实现：全量更新图
        fullUpdateGraph(new FullUpdateGraphRequest());
    }

    @Override
    public BfiaGraphDO getGraphDO(String projectId, String graphId) {
        return bfiaGraphRepository.findById(new BfiaGraphDO.UPK(projectId, graphId))
                .orElse(null);
    }

    private BfiaGraphNodeDO toGraphNodeDO(String projectId, String graphId, GraphNodeInfo node) {
        BfiaGraphNodeDO.UPK upk = new BfiaGraphNodeDO.UPK(projectId, graphId, node.getGraphNodeId());
        return BfiaGraphNodeDO.builder()
                .upk(upk)
                .graphNodeName(node.getGraphNodeName())
                .nodeDefId(node.getNodeDefId())
                .params(node.getParams() != null ? node.getParams().toString() : null)
                .build();
    }

    private String toEdgesJson(List<GraphEdge> edges) {
        if (CollectionUtils.isEmpty(edges)) {
            return "[]";
        }
        // 简单 JSON 序列化
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < edges.size(); i++) {
            GraphEdge e = edges.get(i);
            if (i > 0) sb.append(",");
            sb.append("{\"source\":").append(e.getSource())
              .append(",\"target\":").append(e.getTarget())
              .append(",\"sourcePort\":").append(e.getSourcePort())
              .append(",\"targetPort\":").append(e.getTargetPort())
              .append("}");
        }
        sb.append("]");
        return sb.toString();
    }
}
```

同时创建辅助转换类 `BfiaGraphToVOConverter`（内部静态类即可）将 BfiaGraphDO 转为 GraphDetailVO。

- [ ] **Step 6: 编译验证**

```bash
cd secretpad && mvn compile -pl secretpad-persistence,secretpad-service -am -DskipTests -q
```
Expected: BUILD SUCCESS

- [ ] **Step 7: Commit**

```bash
git add secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaGraph*.java \
  secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/repository/bfia/BfiaGraphRepository.java \
  secretpad-service/src/main/java/org/secretflow/secretpad/service/bfia/BfiaGraphService.java \
  secretpad-service/src/main/java/org/secretflow/secretpad/service/impl/bfia/BfiaGraphServiceImpl.java
git commit -m "feat(bfia): add independent bfia_graph table for flow isolation"
```

---

## Task 3: BfiaJobDO — BFIA 独立任务表

**Files:**
- Create: `secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaJobDO.java`
- Create: `secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/repository/bfia/BfiaJobRepository.java`
- Modify: `secretpad-service/src/main/java/org/secretflow/secretpad/service/impl/bfia/BfiaFlowServiceImpl.java`

- [ ] **Step 1: 创建 BfiaJobDO 实体**

文件：`secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaJobDO.java`

```java
package org.secretflow.secretpad.persistence.entity.bfia;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.Where;
import org.secretflow.secretpad.persistence.entity.BaseAggregationRoot;

@Getter
@Setter
@Builder
@AllArgsConstructor
@NoArgsConstructor
@Entity
@ToString
@Table(name = "bfia_job")
@SQLDelete(sql = "update bfia_job set is_deleted = 1 where job_id = ?")
@Where(clause = "is_deleted = 0")
public class BfiaJobDO extends BaseAggregationRoot<BfiaJobDO> {
    @Id
    @Column(name = "job_id", unique = true, nullable = false, length = 64)
    private String jobId;

    @Column(name = "project_id", nullable = false, length = 64)
    private String projectId;

    @Column(name = "graph_id", nullable = false, length = 64)
    private String graphId;

    @Column(name = "initiator_id", length = 64)
    private String initiatorId;

    @Column(name = "status", length = 32)
    private String status;

    @Column(name = "job_params", columnDefinition = "text")
    private String jobParams;

    @Override
    public String getProjectId() {
        return this.projectId;
    }
}
```

- [ ] **Step 2: 创建 BfiaJobRepository**

文件：`secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/repository/bfia/BfiaJobRepository.java`

```java
package org.secretflow.secretpad.persistence.repository.bfia;

import org.secretflow.secretpad.persistence.entity.bfia.BfiaJobDO;
import org.secretflow.secretpad.persistence.repository.BaseRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface BfiaJobRepository extends BaseRepository<BfiaJobDO, String> {
    @Query("from BfiaJobDO j where j.projectId = :projectId order by j.gmtCreate desc")
    List<BfiaJobDO> findByProjectId(@Param("projectId") String projectId);
}
```

- [ ] **Step 3: 修改 BfiaFlowServiceImpl 的 persistJobRecords 方法**

将 job 持久化从 `ProjectJobRepository`/`ProjectJobDO` 改为 `BfiaJobRepository`/`BfiaJobDO`。

注入改为：
```java
private final BfiaGraphRepository bfiaGraphRepository;
private final BfiaJobRepository bfiaJobRepository;
```

`persistJobRecords` 方法改为写 `BfiaJobDO`：
```java
private void persistJobRecords(ProjectJob job, String initiatorId) {
    try {
        BfiaJobDO jobDO = BfiaJobDO.builder()
                .jobId(job.getJobId())
                .projectId(job.getProjectId())
                .graphId(job.getGraphId())
                .initiatorId(initiatorId)
                .status("SUBMITTED")
                .build();
        bfiaJobRepository.save(jobDO);
        log.info("Persisted BFIA job record: projectId={}, jobId={}, graphId={}, initiatorId={}",
                job.getProjectId(), job.getJobId(), job.getGraphId(), initiatorId);
    } catch (Exception e) {
        log.warn("Failed to persist BFIA job record for {}", job.getJobId(), e);
    }
}
```

`startGraph` 方法中读取图数据的部分改为从 `bfiaGraphRepository` 读取：
```java
if (CollectionUtils.isEmpty(request.getNodes())) {
    BfiaGraphDO graphDO = bfiaGraphRepository
            .findById(new BfiaGraphDO.UPK(request.getProjectId(), request.getGraphId()))
            .orElse(null);
    if (graphDO != null && graphDO.getNodes() != null) {
        List<String> allNodeIds = new ArrayList<>();
        for (BfiaGraphNodeDO node : graphDO.getNodes()) {
            allNodeIds.add(node.getUpk().getGraphNodeId());
        }
        request.setNodes(allNodeIds);
    }
}
```

- [ ] **Step 4: 编译验证**

```bash
cd secretpad && mvn compile -pl secretpad-persistence,secretpad-service -am -DskipTests -q
```
Expected: BUILD SUCCESS

- [ ] **Step 5: Commit**

```bash
git add secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaJobDO.java \
  secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/repository/bfia/BfiaJobRepository.java \
  secretpad-service/src/main/java/org/secretflow/secretpad/service/impl/bfia/BfiaFlowServiceImpl.java
git commit -m "feat(bfia): add independent bfia_job table for job isolation"
```

---

## Task 4: BfiaResultDO — BFIA 独立结果表

**Files:**
- Create: `secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaResultDO.java`
- Create: `secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/repository/bfia/BfiaResultRepository.java`
- Create: `secretpad-web/src/main/java/org/secretflow/secretpad/web/controller/bfia/BfiaResultController.java`

- [ ] **Step 1: 创建 BfiaResultDO 实体**

文件：`secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaResultDO.java`

```java
package org.secretflow.secretpad.persistence.entity.bfia;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.Where;
import org.secretflow.secretpad.persistence.entity.BaseAggregationRoot;

import java.io.Serial;
import java.io.Serializable;

@Getter
@Setter
@Builder
@AllArgsConstructor
@NoArgsConstructor
@Entity
@ToString
@Table(name = "bfia_result")
@SQLDelete(sql = "update bfia_result set is_deleted = 1 where result_id = ?")
@Where(clause = "is_deleted = 0")
public class BfiaResultDO extends BaseAggregationRoot<BfiaResultDO> {
    @Id
    @Column(name = "result_id", unique = true, nullable = false, length = 64)
    private String resultId;

    @Column(name = "project_id", nullable = false, length = 64)
    private String projectId;

    @Column(name = "job_id", length = 64)
    private String jobId;

    @Column(name = "task_id", length = 64)
    private String taskId;

    @Column(name = "node_id", length = 64)
    private String nodeId;

    @Column(name = "kind", length = 32)
    private String kind;

    @Column(name = "ref_id", length = 64)
    private String refId;

    @Column(name = "output_uri", columnDefinition = "text")
    private String outputUri;

    @Override
    public String getProjectId() {
        return this.projectId;
    }
}
```

- [ ] **Step 2: 创建 BfiaResultRepository**

文件：`secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/repository/bfia/BfiaResultRepository.java`

```java
package org.secretflow.secretpad.persistence.repository.bfia;

import org.secretflow.secretpad.persistence.entity.bfia.BfiaResultDO;
import org.secretflow.secretpad.persistence.repository.BaseRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface BfiaResultRepository extends BaseRepository<BfiaResultDO, String> {
    @Query("from BfiaResultDO r where r.projectId = :projectId order by r.gmtCreate desc")
    List<BfiaResultDO> findByProjectId(@Param("projectId") String projectId);
}
```

- [ ] **Step 3: 创建 BfiaResultController**

文件：`secretpad-web/src/main/java/org/secretflow/secretpad/web/controller/bfia/BfiaResultController.java`

```java
package org.secretflow.secretpad.web.controller.bfia;

import org.secretflow.secretpad.persistence.repository.bfia.BfiaResultRepository;
import org.secretflow.secretpad.service.model.common.SecretPadResponse;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@Slf4j
@RestController
@RequestMapping("/api/v1bfia/result")
@RequiredArgsConstructor
public class BfiaResultController {

    private final BfiaResultRepository bfiaResultRepository;

    @PostMapping("list")
    public SecretPadResponse<Map<String, Object>> list(@RequestBody(required = false) Map<String, Object> body) {
        String projectId = body != null ? (String) body.get("projectId") : null;
        List<Map<String, Object>> records = new ArrayList<>();
        if (projectId != null) {
            records = bfiaResultRepository.findByProjectId(projectId).stream()
                    .map(this::toVO)
                    .collect(java.util.stream.Collectors.toList());
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("records", records);
        result.put("total", records.size());
        return SecretPadResponse.success(result);
    }

    @PostMapping("get")
    public SecretPadResponse<Map<String, Object>> get(@RequestBody Map<String, Object> body) {
        String resultId = (String) body.get("resultId");
        return bfiaResultRepository.findById(resultId)
                .map(r -> SecretPadResponse.success(toVO(r)))
                .orElse(SecretPadResponse.success(null));
    }

    private Map<String, Object> toVO(org.secretflow.secretpad.persistence.entity.bfia.BfiaResultDO do_) {
        Map<String, Object> vo = new LinkedHashMap<>();
        vo.put("resultId", do_.getResultId());
        vo.put("projectId", do_.getProjectId());
        vo.put("jobId", do_.getJobId());
        vo.put("taskId", do_.getTaskId());
        vo.put("nodeId", do_.getNodeId());
        vo.put("kind", do_.getKind());
        vo.put("refId", do_.getRefId());
        vo.put("outputUri", do_.getOutputUri());
        vo.put("gmtCreate", do_.getGmtCreate());
        return vo;
    }
}
```

- [ ] **Step 4: 编译验证**

```bash
cd secretpad && mvn compile -pl secretpad-persistence,secretpad-web -am -DskipTests -q
```
Expected: BUILD SUCCESS

- [ ] **Step 5: Commit**

```bash
git add secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/entity/bfia/BfiaResultDO.java \
  secretpad-persistence/src/main/java/org/secretflow/secretpad/persistence/repository/bfia/BfiaResultRepository.java \
  secretpad-web/src/main/java/org/secretflow/secretpad/web/controller/bfia/BfiaResultController.java
git commit -m "feat(bfia): add independent bfia_result table and controller"
```

---

## Task 5: BfiaFlowController 改用 BfiaGraphService

**Files:**
- Modify: `secretpad-web/src/main/java/org/secretflow/secretpad/web/controller/bfia/BfiaFlowController.java`
- Modify: `secretpad-service/src/main/java/org/secretflow/secretpad/service/impl/bfia/BfiaFlowServiceImpl.java`

- [ ] **Step 1: BfiaFlowController 的 graph CRUD 改为调 BfiaGraphService**

将 `createFlow`、`fullUpdateGraph`、`saveGraph`、`getGraphDetail`、`listFlow`、`deleteGraph`、`updateGraphNode` 方法从调用 `graphService`（标准 GraphService）改为调用 `bfiaGraphService`（BfiaGraphService）。

注入改为：
```java
private final BfiaGraphService bfiaGraphService;
private final BfiaFlowService bfiaFlowService;
```

各方法改为：
```java
@PostMapping("/create")
public SecretPadResponse<CreateGraphVO> createGraph(@RequestBody Map<String, Object> body) {
    return SecretPadResponse.success(bfiaGraphService.createGraph(toRequest(body, CreateGraphRequest.class)));
}

@PostMapping("/update")
public SecretPadResponse<Void> fullUpdateGraph(@RequestBody Map<String, Object> body) {
    bfiaGraphService.fullUpdateGraph(toRequest(body, FullUpdateGraphRequest.class));
    return SecretPadResponse.success();
}

@PostMapping("/save")
public SecretPadResponse<Void> saveGraph(@RequestBody Map<String, Object> body) {
    bfiaGraphService.fullUpdateGraph(toRequest(body, FullUpdateGraphRequest.class));
    return SecretPadResponse.success();
}

@PostMapping("/detail")
public SecretPadResponse<GraphDetailVO> getGraphDetail(@RequestBody Map<String, Object> body) {
    return SecretPadResponse.success(bfiaGraphService.getGraphDetail(toRequest(body, GetGraphRequest.class)));
}

@PostMapping("/list")
public SecretPadResponse<List<GraphMetaVO>> listFlow(@RequestBody Map<String, Object> body) {
    return SecretPadResponse.success(bfiaGraphService.listGraph(toRequest(body, ListGraphRequest.class)));
}
```

- [ ] **Step 2: BfiaFlowServiceImpl 移除对 GraphService 的依赖**

`startGraph` 方法中 `graphService.buildProjectJob(request)` 这一行需要重构。因为 buildProjectJob 依赖标准 ProjectGraphDO，现在 BFIA 图在 bfia_graph 表中。

改为从 BfiaGraphDO 手动构建 ProjectJob：
```java
@Override
public StartGraphVO startGraph(StartGraphRequest request) {
    try {
        // 从 bfia_graph 读取图节点
        BfiaGraphDO graphDO = bfiaGraphRepository
                .findById(new BfiaGraphDO.UPK(request.getProjectId(), request.getGraphId()))
                .orElse(null);
        if (graphDO == null || CollectionUtils.isEmpty(graphDO.getNodes())) {
            throw new IllegalStateException("BFIA flow graph is empty or not found");
        }
        // 构建 ProjectJob（手动构建，不依赖 GraphService.buildProjectJob）
        String jobId = UUIDUtils.random(8);
        ProjectJob job = new ProjectJob();
        job.setJobId(jobId);
        job.setProjectId(request.getProjectId());
        job.setGraphId(request.getGraphId());
        // ... 将 BfiaGraphNodeDO 转为 ProjectJob.JobTask
        // 提交到 Kuscia interconn API
        // ...（保留原有提交逻辑）
        persistJobRecords(job, initiatorId);
        return new StartGraphVO(jobId);
    } finally {
        if (!Boolean.TRUE.equals(GraphContext.isScheduled())) {
            GraphContext.remove();
        }
    }
}
```

注意：`buildProjectJob` 的逻辑较复杂（包含节点依赖解析、party 解析等），这部分需要从 GraphServiceImpl 中提取或手动实现简化版。由于 BFIA 的 DAG 结构较简单（通常是线性 data_source → ecdh_psi），可以简化构建逻辑。

- [ ] **Step 3: 编译验证**

```bash
cd secretpad && mvn compile -pl secretpad-service,secretpad-web -am -DskipTests -q
```
Expected: BUILD SUCCESS

- [ ] **Step 4: Commit**

```bash
git add secretpad-web/src/main/java/org/secretflow/secretpad/web/controller/bfia/BfiaFlowController.java \
  secretpad-service/src/main/java/org/secretflow/secretpad/service/impl/bfia/BfiaFlowServiceImpl.java
git commit -m "refactor(bfia): flow controller uses BfiaGraphService for graph CRUD"
```

---

## Task 6: 前端 BFIA 结果管理页对接独立 API

**Files:**
- Modify: `secretpad-frontend/apps/platform/src/pages/edge.tsx` — 确认 BFIA 菜单"结果管理"指向 /api/v1bfia/result/*
- Modify: BFIA 结果管理相关组件（如果有独立的 record 模块）

- [ ] **Step 1: 检查前端 BFIA 结果管理 API 调用路径**

用 Grep 搜索前端中 BFIA 模式下的结果管理 API 调用，确认调用的是 `/api/v1bfia/result/*` 而非 `/api/v1alpha1/record/*`。

```bash
grep -rn "v1alpha1/record\|v1bfia/result" secretpad-frontend/apps/platform/src/
```

- [ ] **Step 2: 如有调用标准 API 的地方，改为调用 BFIA API**

在 BFIA 模式下，结果列表调用 `/api/v1bfia/result/list`，结果详情调用 `/api/v1bfia/result/get`。

- [ ] **Step 3: Commit（如有修改）**

```bash
git add secretpad-frontend/
git commit -m "feat(frontend): BFIA result page uses independent /api/v1bfia/result API"
```

---

## Task 7: 全量构建与部署验证

**Files:**
- 无新文件，仅构建和验证

- [ ] **Step 1: 后端全量编译**

```bash
cd secretpad && mvn compile -DskipTests -q
```
Expected: BUILD SUCCESS

- [ ] **Step 2: 后端打包**

```bash
cd secretpad && mvn package -pl secretpad-web -am -DskipTests -Dmaven.gitcommitid.skip=true -q
```
Expected: BUILD SUCCESS，生成 target/secretpad.jar

- [ ] **Step 3: 前端构建**

```bash
cd secretpad-frontend/apps/platform && npx umi build
```
Expected: 构建成功，生成 dist/

- [ ] **Step 4: 同步前端产物到 Spring Boot**

```bash
rm -rf secretpad/secretpad-web/src/main/resources/static/*
cp -r secretpad-frontend/apps/platform/dist/* secretpad/secretpad-web/src/main/resources/static/
```

- [ ] **Step 5: 重新打包 JAR（含前端产物）**

```bash
cd secretpad && mvn package -pl secretpad-web -am -DskipTests -Dmaven.gitcommitid.skip=true -q
```

- [ ] **Step 6: 重启 Alice 和 Bob 服务**

```bash
kill -9 $(lsof -tiTCP:18080 -sTCP:LISTEN) 2>/dev/null
kill -9 $(lsof -tiTCP:28080 -sTCP:LISTEN) 2>/dev/null
sleep 3

cd /path/to/secretpad
nohup java -jar target/secretpad.jar --server.http-port=18080 ... > /tmp/alice.log 2>&1 &
cd /path/to/secretpad-bob
nohup java -jar target/secretpad.jar --server.http-port=28080 ... > /tmp/bob.log 2>&1 &

sleep 35
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18080/
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:28080/
```
Expected: 两个都返回 200

- [ ] **Step 7: 验证数据隔离**

1. 登录 Alice（admin/123456）
2. 切换到"隐语"协议，查看节点列表 — 应只看到隐语节点
3. 切换到"BFIA"协议，查看节点列表 — 应只看到 BFIA 节点（bfia_node 表）
4. 在 BFIA 模式下创建流程、提交任务，验证数据写入 bfia_graph / bfia_job 表
5. 切换回"隐语"模式，确认看不到 BFIA 的流程和任务

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "build: full isolation between BFIA and native protocols"
```

---

## 自检清单

- [ ] bfia_node 表独立，BfiaNodeController 查 bfia_node 不查 node
- [ ] bfia_graph 表独立，BfiaFlowController 的 CRUD 调 BfiaGraphService 不调 GraphService
- [ ] bfia_job 表独立，BfiaFlowServiceImpl.persistJobRecords 写 BfiaJobDO
- [ ] bfia_result 表独立，BfiaResultController 查 bfia_result
- [ ] 隐语原生 API（/api/v1alpha1/*）不受影响，仍查标准表
- [ ] 前端 BFIA 模式下所有 API 调用走 /api/v1bfia/*
- [ ] 两种协议切换后，数据完全不可见
