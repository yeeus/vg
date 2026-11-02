# chr21 OOM 后的 r2 重跑

这次需要重算 full 阶段一次。原脚本把 GFA 导出、GFAffix、unchop、full 裁剪放在同一个 Toil job；只有最后才 `writeGlobalFile`。因此 GFAffix/unchop 成功的日志不代表它们已经进入 jobStore。临时目录已清理、又没有其他备份时，原来的局部计算无法恢复。**不要对 r1 原样 `--restart`。**

r2 保留 control + 一个 candidate，原 `04.join.sh` 不改：

- full/clip/filter 和 control 的 import→unchop 改成逐条执行、通过文件交接。消除管道上下游同时持有大图的内存叠加；原操作顺序及科学参数保留，候选仍沿用 r1 的融合命令。
- 每条成功命令的图文件与 stderr 保存在 `stage_cache/`；完成标记在命令成功、文件保存完毕后才写入。后续 r2 续跑可复用，失败阶段重算。校验和统计仍执行。
- 修正 r1 手工编译 clip-vg 漏掉 jemalloc、关闭 assertions 的问题。两组均按 pinned hal2vg 的配置链接 jemalloc、启用 assertions。

这会增加磁盘占用和读写。阶段缓存放在持久项目盘；为缓存、Toil workDir 和最终输出预留足够磁盘。它降低的是**大图交接时的峰值内存**，不承诺整个 join 更快，也不能提前保证 chr21 或更大染色体能在 480G 内完成。

## 1. 下载 r2，增量编译

沿用 r1 已编译成功的 Cactus、GCC 和依赖环境。以下使用你当前 `/public/home/u12518101` 集群路径。保留 r1 目录，**不重新编译 vg 或 GFAffix**；只编译 jemalloc、clip-vg 的两个 backend 和两个 clip-vg。

```bash
SOFT=/public/home/u12518101/softwares
SRC="$SOFT/vg-join-candidate-r2"
PREFIX="$SOFT/cactus-join-candidate-r2"

git clone --filter=blob:none --no-checkout --branch cactus-7f34bb7-lowmem \
    https://github.com/yeeus/vg.git "$SRC"
git -C "$SRC" sparse-checkout set benchmarks/cactus_join benchmarks/cactus_unchop
R2=$(git -C "$SRC" rev-parse origin/cactus-7f34bb7-lowmem)
git -C "$SRC" checkout --detach "$R2"

bash "$SRC/benchmarks/cactus_join/upgrade_r2.sh" \
    "$SOFT/cactus-join-candidate-r1" "$PREFIX" 8
```

看到 `PASS r2 upgrade and small graph comparisons` 才运行 chr21。两组 vg 的 `version` 仍显示 r1 版本是正常的：r2 复用它们；r2 编排代码版本记录在 `$PREFIX/source.commit`。

## 2. 新作业、新输出目录

从原来的 **chr21 目录**执行，使用集群上你当前的 `04.join.sh` 和 `cactus.config.sh`；不要用其他副本覆盖它们。输入仍是 `align/chr21.vg` 和原 SV-GFA；是否处理 HAL 完全沿用该脚本。

在已分配的 Slurm 计算作业内执行，首轮可维持当前 56 核 / 480G，不主动降低预算。建议先跑 candidate；成功后，再用相同资源跑 control。每个作业都先设置以下变量：

```bash
SOFT=/public/home/u12518101/softwares
SRC="$SOFT/vg-join-candidate-r2"
PREFIX="$SOFT/cactus-join-candidate-r2"
WORK="$PWD/join_bench_r2"
SCRIPT="$PWD/04.join.sh"

# candidate 作业
python3 "$SRC/benchmarks/cactus_join/run.py" \
    candidate "$PREFIX" "$WORK/candidate" "$SCRIPT"

# control 作业；单独分配相同资源，仍从原 chr21 目录启动
python3 "$SRC/benchmarks/cactus_join/run.py" \
    control "$PREFIX" "$WORK/control" "$SCRIPT"
```

保留 `join_bench_r1`。r2 不接管 r1 jobStore；两组现在都使用私有 Cactus override，加入相同的文件交接和阶段保存，避免把执行方式差异混入候选比较。共享 Cactus 安装不改。

日志和 CPU/RSS 仍在各自输出目录；阶段文件、完成标记在 `stage_cache/<输入与配置标识>/`。`01-export` 是导出 GFA，`02-gfaffix` 是修正 GFA，`03-unchop-*` 是转换/unchop，`04-clip-*`、`05-filter-*` 是后续图处理。

## 3. 仅当 r2 失败时续跑

先根据失败日志处理原因，保持同一工具版本、输入、配置、脚本及工作目录，保留 **r2 jobStore 和 stage_cache**；重新分配 Slurm 资源后，原命令增加 `--restart`：

```bash
python3 "$SRC/benchmarks/cactus_join/run.py" \
    candidate "$PREFIX" "$WORK/candidate" "$SCRIPT" --restart
```

control 同理。已完成阶段会记录 `JOIN_STAGE reuse`，只重算未完成或缓存不匹配的阶段；统计/校验可能重新执行。上一轮日志移入 `previous_attempts/`，不会覆盖。失败命令内部的进度无法恢复。

`summary.json`、GNU time 和 TSV 记录的是**本次尝试**；若续跑过，评估完整资源消耗需同时计入 `previous_attempts/`，不能把最后一次续跑的时间当成全流程耗时。

## 4. 两组成功后，多线程 verify

```bash
/usr/bin/time -v -o "$WORK/verify.time.log" \
python3 "$SRC/benchmarks/cactus_join/verify.py" \
    "$WORK/control" "$WORK/candidate" \
    --vg "$PREFIX/candidate/bin/vg" \
    --threads 8 --tmp "$WORK" --output "$WORK/verify"
```

通过标准：退出码 0，`verify/report.json` 的 `pass` 为 `true`。沿用原验证范围：完整节点/边/路径、XG/GBZ、GFA、VCF、HAL（如有）、ODGI 及其他交付文件。图内指纹和外部 GFA 排序支持多线程；图逐个加载，避免同时加载两张大图。完整文件比较不通过时保留 FAIL，不降低验证标准。

本地已通过：两个 clip-vg 的 Linux 编译及 jemalloc 链接检查；四组真实小图的两组命令链对照（含大 deletion、GBZ→XG、1/4 线程图指纹及交付 verify）；阶段失败、删除临时目录后复用、stderr 和缓存身份检查。尚未在你的集群重跑完整 chr21；480G 是否足够由该轮实测决定。
