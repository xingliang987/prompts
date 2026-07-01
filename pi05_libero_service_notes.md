# pi0.5 LIBERO 服务配置记录

日期：2026-05-25

目标机器：

- SSH：`arm@192.168.127.61`
- Docker 容器：`pi_dev`
- 宿主机 workspace：`/home/arm/pi05_workspace`
- 容器 workspace：`/workspace`
- openpi 代码：`/workspace/openpi`
- LIBERO checkpoint：`/workspace/pi05_libero`
- 对外服务端口：`192.168.127.61:8000`

## 当前可用入口

宿主机上一键启动脚本：

```bash
/home/arm/pi05_workspace/start_pi05_libero_service.sh start
```

停止：

```bash
/home/arm/pi05_workspace/start_pi05_libero_service.sh stop
```

查看状态：

```bash
/home/arm/pi05_workspace/start_pi05_libero_service.sh status
```

看日志：

```bash
/home/arm/pi05_workspace/start_pi05_libero_service.sh logs
```

健康检查：

```bash
curl http://192.168.127.61:8000/healthz
```

应返回：

```text
OK
```

## 服务组成

这个服务实际由两层组成：

1. 容器内 policy server

```bash
cd /workspace/openpi
XLA_PYTHON_CLIENT_PREALLOCATE=false \
.venv/bin/python scripts/serve_policy_float32.py \
  --config=pi05_libero \
  --checkpoint-dir=/workspace/pi05_libero \
  --port=8000
```

2. 宿主机端口转发

容器 `pi_dev` 没有用 Docker `-p 8000:8000` 发布端口。为了不重建容器，使用宿主机 Python TCP forwarder，把宿主机 `0.0.0.0:8000` 转到容器 IP 的 `8000`。

脚本会自动获取容器 IP：

```bash
docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' pi_dev
```

然后启动 forwarder：

```text
0.0.0.0:8000 -> <container_ip>:8000
```

PID 和日志：

```text
/tmp/pi_dev_8000_forward.pid
/tmp/pi_dev_8000_forward.log
```

## 为什么新增 float32 server

原始命令是：

```bash
uv run scripts/serve_policy.py \
  policy:checkpoint \
  --policy.config=pi05_libero \
  --policy.dir=/workspace/pi05_libero
```

它能加载模型并通过 `/healthz`，但第一次 websocket `infer` 时服务端崩溃：

```text
Unsupported conversion from bf16 to f16
LLVM ERROR: Unsupported rounding mode for conversion.
```

这发生在 GB10 / aarch64 / JAX CUDA 路线下的模型完整图编译阶段。单独的 bf16/f16 cast 小测试可以通过，但 pi0.5 模型图在第一次推理 JIT 时触发 XLA/LLVM lowering 问题。

规避方案：使用 float32 方式加载参数和构建模型。

新增脚本：

```text
/workspace/openpi/scripts/serve_policy_float32.py
```

关键逻辑：

- `train_config.model.dtype = "float32"`
- `restore_params(..., dtype=jnp.float32)`
- 其余 transforms、norm stats、websocket server 逻辑保持和原 openpi policy server 一致

这样可以避免 bf16 到 f16 的 XLA crash。代价是模型参数和部分计算占用更高，但 GB10 这台机器有 121GiB RAM，实测可用。

## Unified memory / JAX 内存问题

GB10 是 unified memory。JAX 默认会在第一次 GPU 操作时预分配较大比例的 GPU memory；在 unified memory 机器上，这会表现成系统 RAM 被大量占用。我们看到过服务启动时 RAM 占用约 100GiB。

解决：

```bash
XLA_PYTHON_CLIENT_PREALLOCATE=false
```

这个环境变量已经写进一键启动脚本。它让 JAX 按需分配内存，避免启动时大规模预分配。

## tokenizer 缓存

启动时需要 `paligemma_tokenizer.model`。远端下载可能慢或卡住。手动下载后已放入容器缓存：

```text
/root/.cache/openpi/big_vision/paligemma_tokenizer.model
```

来源：

```text
gs://big_vision/paligemma_tokenizer.model
```

宿主机曾下载到：

```text
/home/arm/paligemma_tokenizer.model
```

然后复制进容器：

```bash
docker exec pi_dev mkdir -p /root/.cache/openpi/big_vision
docker cp /home/arm/paligemma_tokenizer.model pi_dev:/root/.cache/openpi/big_vision/paligemma_tokenizer.model
docker exec pi_dev chmod a+rw /root/.cache/openpi/big_vision/paligemma_tokenizer.model
```

## Docker 容器状态

当前容器原始配置：

- image：`ngc.nju.edu.cn/nvidia/cuda:12.2.0-base-ubuntu22.04`
- restart policy：`always`
- bind mount：`/home/arm/pi05_workspace:/workspace`
- GPU：`--gpus all`
- 没有 Docker port binding

由于已有容器不能原地新增 `-p 8000:8000`，且重建容器有风险，所以使用宿主机转发而不是重建容器。

## PyTorch CUDA 问题

主 openpi venv 里：

```text
torch 2.7.1+cpu
torch.cuda.is_available() = False
```

这不影响当前 pi0.5 LIBERO JAX policy server，因为服务走 JAX 路线。早期曾尝试查找 aarch64 CUDA PyTorch wheel，但 GB10/CUDA 13 不适合退到老 CUDA wheel；并且 PyTorch 路线不是当前 blocker，所以没有继续修改主 `.venv`。

## LIBERO 客户端/仿真环境

为了不污染 openpi 主推理环境，LIBERO 仿真客户端装在独立 venv：

```text
/workspace/openpi/examples/libero/.venv
```

使用清华 PyPI 镜像安装依赖，因为默认 PyPI 在机器上多次超时：

```bash
uv pip install \
  --python examples/libero/.venv/bin/python \
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
  ...
```

补充安装了：

- `libero`
- `robosuite`
- `mujoco`
- `openpi-client`
- `torch` CPU 版
- `matplotlib`
- `future`
- `gym`
- `hydra-core`
- 以及相关依赖

LIBERO 首次导入会交互式询问 dataset 路径。为了非交互运行，写入：

```text
/root/.libero/config.yaml
```

内容指向仓库里的 `third_party/libero` 路径。

## 已验证测试

### 随机 LIBERO observation 推理

使用 websocket client 发送 LIBERO-style random observation：

```text
actions shape: (10, 7)
server infer: ~0.5s after JIT warmup
```

第一次重新启动服务后的第一次 inference 会触发 JIT，可能需要十几秒。

### 真实 LIBERO rollout

命令：

```bash
cd /workspace/openpi

PYTHONPATH=/workspace/openpi/third_party/libero \
MUJOCO_GL=egl \
examples/libero/.venv/bin/python examples/libero/main.py \
  --args.host=127.0.0.1 \
  --args.port=8000 \
  --args.task-suite-name=libero_spatial \
  --args.num-trials-per-task=1 \
  --args.video-out-path=/workspace/video
```

最近一次结果：

```text
Total success rate: 0.9
Total episodes: 10
```

视频输出：

```text
/workspace/video
```

宿主机可见路径：

```text
/home/arm/pi05_workspace/video
```

## 已知 warning

### EGL cleanup warning

rollout 结束后可能出现：

```text
EGLError: EGL_NOT_INITIALIZED
Failed to load library ('libGLU.so.0')
```

这是 robosuite/Mujoco EGL context 析构清理阶段的 warning，发生在 rollout 完成之后。已确认不影响 episode 执行、成功率统计和视频保存。

### Gym unmaintained warning

会出现：

```text
Gym has been unmaintained since 2022...
```

这是老 LIBERO/robosuite 依赖链的提示，不影响当前测试。

## 常用排障命令

查看服务：

```bash
/home/arm/pi05_workspace/start_pi05_libero_service.sh status
```

查看日志：

```bash
/home/arm/pi05_workspace/start_pi05_libero_service.sh logs
```

容器内直接查：

```bash
docker exec pi_dev bash -lc 'ps -eo pid,ppid,stat,etime,rss,cmd | grep serve_policy_float32 | grep -v grep'
docker exec pi_dev bash -lc 'tail -200 /workspace/openpi/logs/pi_policy_server_float32.log'
docker exec pi_dev bash -lc 'curl -fsS http://127.0.0.1:8000/healthz'
```

宿主机查转发：

```bash
cat /tmp/pi_dev_8000_forward.pid
tail -80 /tmp/pi_dev_8000_forward.log
curl http://127.0.0.1:8000/healthz
curl http://192.168.127.61:8000/healthz
```

重启全套服务：

```bash
/home/arm/pi05_workspace/start_pi05_libero_service.sh restart
```
