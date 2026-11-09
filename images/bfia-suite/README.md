# 八算法验证镜像

镜像包含 SGB、HE-WOE 的 Python 实现，六项 C++ 算法共用的 `ic_main`，公开样本、执行脚本及数值/协议校验器。镜像内不需要源码挂载或编译器，也不调用 Docker daemon/socket；宿主仍需 Docker 或 Kuscia 运行时。

当前 suite 镜像已公开，全部镜像层匿名下载、完整归档校验及公司浏览器八算法运行、刷新和报告导出已通过。它独立于尚待验收和封存的整个平台发布清单。

## 直接运行已发布镜像

在 Linux amd64 的 Docker 主机执行，首次自动拉取固定摘要的镜像；计算时关闭外网，只挂载本轮结果目录：

```bash
run_id=$(cat /proc/sys/kernel/random/uuid)
output=/var/log/ppci/bfia-standalone/$run_id
sudo install -d -m 700 "$output"
sudo docker run --rm --platform linux/amd64 --network none --read-only \
  --cpus 4 --memory 6g --pids-limit 512 --shm-size 512m \
  --tmpfs /tmp:rw,nosuid,size=512m -v "$output:/results:Z" \
  ghcr.io/reacher1130/bfia-suite@sha256:fa639734c9bc5b7d778c1289a2ed13ef5661a01edf2133bbb67b52e02a159d7c \
  "$run_id"
sudo cat "$output/report.json"
```

结果、数值/协议校验和双方完整日志保存在该目录；成功退出码为 0。`Z` 只对新建的专用结果目录设置 SELinux 容器标签。ARM 主机使用根部署脚本提供的 amd64 虚拟机，再在虚拟机内执行。

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
