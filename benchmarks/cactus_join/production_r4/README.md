# 冻结 r4：资源可调的首次运行和续跑

计算版本固定为 `9952f0fe7cc270d67d28d896096311499d9095f1`。只调整启动参数，不修改已通过 chr21 验证的工具或私有 Cactus 模块，不需要重新编译。

原版 chr2 `js.join` 从 A 搬到 B 的特殊续跑，使用 [迁移入口](MIGRATE_JOIN.md)，不使用下面针对 `join_r4/js.join` 的普通续跑入口。

将 `start.sh`、`restart.sh`、`launch.py` 一起放到 `/public/home/u12518101/softwares/cactus-r4-run/`。每条染色体仍使用自己的 `cactus.config.sh`、原 `04.join.sh` 和输入文件。在对应染色体目录内执行，确认 `CHROM` 正确。安装目录的 `source.commit` 必须是冻结版本；源码目录可沿用此前传入 B 的 benchmark 脚本，不需要完整 Git 仓库。

## 首次运行

普通节点示例，外层已分配 56 CPU / 500G：

```bash
bash /public/home/u12518101/softwares/cactus-r4-run/start.sh --cores 56 --memory 480Gi
```

chr1 可以直接从 2T 节点开始，外层已分配至少 56 CPU / 2T：

```bash
bash /public/home/u12518101/softwares/cactus-r4-run/start.sh --cores 56 --memory 1900Gi
```

| 参数 | 用途 | 不指定时 |
|---|---|---|
| `--memory 1900Gi` | Toil 总内存和 indexMemory 预算 | Slurm 内存分配的 95% |
| `--cores 56` | 首次 maxCores/indexCores 及 OMP 上限 | 首次取 Slurm CPU 数；续跑继承首次值 |
| `--max-jobs 1` | 同时运行的 Toil 任务数上限 | 首次为 1；续跑继承上次值 |

也可以不传参数，直接运行 `bash .../start.sh`。不必先尝试 500G。软件根目录可通过 `R4_SOFT=/其他路径` 指定。

预算不能超过外层分配，内存需留下余量。提高 `--max-jobs` 会允许多个任务同时占用内存，默认 1 便于控制总 RSS；任务内部仍可多线程。`--defaultCores 1` 和 r4 最多 4 线程的 unchop 保持冻结，以保留已验证的 Full 融合路径。

## 失败后续跑

旧作业退出后，在同一个染色体目录、所需资源的新作业中执行：

```bash
bash /public/home/u12518101/softwares/cactus-r4-run/restart.sh --memory 1900Gi
```

可换用其他内存值，或省略 `--memory` 使用当前分配的 95%。脚本会备份并上调尚未完成任务的内存申请，不能将预算降到已有任务申请值以下。线程配置已保存在 jobStore，续跑沿用首次值，节点可申请更多 CPU；显式传入不同 `--cores` 时会停止说明原因，避免只修改 CLI 而保存任务线程不变。

保留整个 `join_r4/`、输入、原脚本和配置，不要移动或清空。已完成的 Toil 任务不重算；失败任务重试，并复用已成功保存的 stage_cache 子步骤。未保存完成的命令需要重算。旧日志自动归档，两个入口共用文件锁。

## 输出

最终文件在 `join_r4/final/`；当前主日志和 GNU time 在 `join_r4/logs/`，资源汇总在 `join_r4/summary.json`，并保留逐进程 CPU/RSS 采样。历史轮次在 `join_r4/previous_attempts/`，任务资源修改前的元数据在 `join_r4/restart_resources/`。

OOM 若杀死外层 Python，旧轮 summary 可能未写完，已有日志仍保留。成功标准是退出码 0、主日志确认完成且所请求文件已生成；这不等同于不同版本之间的全文件一致性验证。
