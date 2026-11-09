# 冻结 r4：其他染色体首次运行和 2T 续跑

计算版本固定为 `9952f0fe7cc270d67d28d896096311499d9095f1`。继续使用 B 上已经通过 chr21 测试的 `vg-join-candidate-r4` 源码和 `cactus-join-candidate-r4` 安装；不要更新、重新编译或替换其中的工具/私有模块。此目录只提供资源调度和续跑脚本，图计算代码与参数保持 r4。

## 放置脚本

将 `start.sh`、`restart.sh`、`launch.py` 放到：

```text
/public/home/u12518101/softwares/cactus-r4-run/
```

不需要重新编译。每条染色体保留自己的 `cactus.config.sh`、原 `04.join.sh`、`align/<染色体>.vg`、`align/<染色体>.hal` 和 minigraph 输入。`CHROM` 必须是该染色体。原 `04.join.sh` 中是否传入 HAL 等输出参数原样保留。

## 首次运行

在分配好 **56 CPU / 500G** 的普通节点作业中，先进入对应染色体目录，再执行：

```bash
cd /public/home/u12518101/project/APGp2/00.data/00.assembly/06.graph/chr2
bash /public/home/u12518101/softwares/cactus-r4-run/start.sh
```

每条染色体各运行一次，无须修改脚本中的染色体名称。安装目录的 `source.commit` 必须对应冻结版本；运行器会核对。源码目录只需保留之前传入 B 的冻结版 benchmark 脚本，不要求 B 上存在完整 Git 仓库。已有 `join_r4/` 时首次脚本会停止，不覆盖结果。

外层 500G，Toil 内部预算为 **480 GiB**，留出至少约 20 GiB 余量。`--defaultCores 1` 保留经过验证的 Full 融合路径；`--maxCores 56 --indexCores 56` 保留索引可用线程。r4 的 unchop 仍为最多 4 线程。

## OOM 后在 2T 节点续跑

确认旧作业已经退出。在 **2T 内存、至少 56 CPU** 的新作业中，进入**同一个染色体目录**：

```bash
cd /public/home/u12518101/project/APGp2/00.data/00.assembly/06.graph/chr2
bash /public/home/u12518101/softwares/cactus-r4-run/restart.sh
```

Toil 内部预算升为 **1900 GiB**。脚本备份并上调 jobStore 中尚未执行完的任务内存申请，然后对原 `join_r4/js.join` 执行 `--restart`。只改任务资源，不反序列化任务主体，不改变图参数。

两种入口均使用 `--maxJobs 1`：一次运行一个 Toil 任务，任务内部仍可使用所设线程。原因是 Toil 续跑保留原任务参数；未来动态创建的子任务可能仍带旧的内存申请值。`single_machine` 下这些值用于调度，不是每个进程的独立硬限制。一次一个任务可避免多个此类大任务同时挤满 2T 节点。Slurm 的外层内存限制仍生效。

保留整个 `join_r4/`、输入文件、原 `04.join.sh` 和配置；不要移动或清空目录。已完成的 Toil 任务不会重算；失败任务从自身起点重试，其中成功保存的 `stage_cache` 子步骤可复用。正在执行但未保存完成的命令需要重算。两个入口共用文件锁，避免同一染色体同时启动/续跑。

## 结果与日志

```text
join_r4/final/                         最终图、VCF、索引及原脚本请求的其他输出
join_r4/logs/04.join.log               当前轮主日志
join_r4/logs/04.join.time.log          当前轮 GNU time
join_r4/summary.json                   当前轮退出码与 CPU/RSS
join_r4/cpu_memory.tsv                 当前轮进程树资源采样
join_r4/process_cpu_memory.tsv         当前轮各进程采样
join_r4/stage_cache/                   已完成子步骤缓存
join_r4/previous_attempts/1/           第一次续跑时保留的旧日志；以后依次编号
join_r4/restart_resources/             内存申请修改前的任务元数据备份
```

若 OOM 直接杀死外层 Python，旧轮 `summary.json` 可能没有写完；旧日志仍会在续跑时归档。各轮资源汇总分别保存，不把最后一轮耗时当作整个染色体总耗时。

成功标准：Bash 返回 0，主日志出现 workflow 完成信息，`summary.json` 中 `exit_code` 为 0，且原脚本请求的最终文件生成。这表示流程成功完成；不等同于与另一个版本进行过图/VCF 一致性验证。
