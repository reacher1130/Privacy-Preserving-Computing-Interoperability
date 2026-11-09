# 八算法验证镜像

镜像包含 SGB、HE-WOE 的 Python 实现，六项 C++ 算法共用的 `ic_main`，公开样本、执行脚本及数值/协议校验器。运行不需要源码挂载、编译器、Docker daemon 或 Docker socket。

## 维护者构建

先按根构建流程生成已验证的 Python 依赖镜像和 C++ 引擎镜像，再在 Linux amd64 构建机生成受控上下文：

```bash
python3 images/bfia-suite/prepare-context.py \
  --output /opt/ppci-build/bfia-suite-image \
  --rg /opt/ppci-tools/rg/rg
docker build --build-arg SOURCE_REVISION="$(git rev-parse HEAD)" \
  -t ppci/bfia-suite:verified /opt/ppci-build/bfia-suite-image
```

`rg` 旁需保留官方发布包中的 `LICENSE-MIT` 和 `UNLICENSE`。构建上下文只接收固定 Git 版本的算法源码及必要许可证，不包含 `.git`、旧运行结果、身份或私钥。基础镜像可通过 `BFIA_CPP_IMAGE` / `BFIA_PYTHON_BASE` 构建参数指定已核验版本。

C++ 引擎需要的新版 glibc 与动态库随镜像独立封装，仅通过引擎包装器加载，不改动 Python 已验证的运行库。

## 执行约定

- 入口为 `/usr/local/bin/bfia-suite`，参数为小写 UUID，或用 `BFIA_RUN_ID` 指定。
- 直接运行时，`BFIA_RESULT_ROOT` 默认 `/results`。每次运行使用新的私有结果目录。
- 结果保留 `python/<UUID>/`、`cpp/<UUID>/`，包含真实双方日志和四份数值/协议报告；顶层另有 `report.json`、`exit-code`。只有八项数值与协议校验全部成功才退出 0。
- Kuscia 使用 `--kuscia`，在任务临时目录运行，通过有大小限制、带 SHA256 的 stdout 分块传回日志快照和最终结果包，不需要给计算容器挂载宿主源码或 Docker socket。

当前镜像为 Linux amd64 的公开样本验证入口，不代表原生 ARM 或八项真实机构业务画布均已验收。
