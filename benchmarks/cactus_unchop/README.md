# chr21 unchop 对照运行

基线：`f2ed0bbd4f7d1e7f8c8f4df4a84018f388194d51`（`v1.76.1-89-gf2ed0bbd4`）。

| 模式 | 内容 |
|---|---|
| control | 原版管道 |
| v1 | 去掉无用路径序列缓存，保留管道 |
| v2 | v1 + 导入、unchop 合为一个进程 |
| v3 | v2 + 并行只读邻接分析；修改图仍串行 |

三种实验模式共用一次编译。原版单独保留，不覆盖 Cactus 中的 vg。

## 1. 下载并编译原版

先激活现有 Cactus/GCC 环境。首次构建仍需满足 [vg 开发依赖](https://github.com/vgteam/vg/blob/f2ed0bbd4f7d1e7f8c8f4df4a84018f388194d51/README.md#building-vg)。

```bash
git clone --filter=blob:none --no-checkout https://github.com/yeeus/vg.git vg-unchop-bench
cd vg-unchop-bench
git checkout --detach f2ed0bbd4f7d1e7f8c8f4df4a84018f388194d51
git submodule update --init --recursive
make -j 16 > build.control.log 2>&1 && cp bin/vg bin/vg.control
./bin/vg.control version

git checkout cactus-7f34bb7-unchop-bench
REPO="$PWD"
CHR21=/path/to/chr21
WORK="$CHR21/unchop_bench"
```

确认编译成功后再继续；失败时查看 `build.control.log`。

## 2. 从原始 VG 生成共同输入

使用 Cactus 环境中原有的 gfaffix：

```bash
bash "$REPO/benchmarks/cactus_unchop/prepare_input.sh" \
    "$CHR21/align/chr21.vg" "$WORK/input" "$REPO/bin/vg.control"
GFA="$WORK/input/chr21.vg.gfaffixed.gfa"
```

脚本按 [Cactus 7f34bb7 的 full 阶段](https://github.com/ComparativeGenomicsToolkit/cactus/blob/7f34bb7a65af5816835ef79b7ae5e2f3c277b305/src/cactus/refmap/cactus_graphmap_join.py#L1470-L1511) 依次运行 `vg paths -x … -L`、`vg convert -f …` 和：

```bash
gfaffix chr21.vg.gfa --output_refined chr21.vg.gfaffixed.gfa \
    --check_transformation --threads 1 --dont_collapse 'GRCh38#[.]*'
```

对应你本轮的 `reference[0]=GRCh38`、`defaultCores=1`。输入只生成一次，四组共用。

## 3. 编译三个实验方向

```bash
cd "$REPO"
git submodule sync --recursive
git submodule update --init --recursive
make -j 16 > build.experiment.log 2>&1 && cp bin/vg bin/vg.experiment
./bin/vg.experiment version
OMP_NUM_THREADS=1 python3 benchmarks/cactus_unchop/test_cli.py
```

确认编译和小图检查成功后再跑 chr21。libhandlegraph 的修改已由 submodule 固定，不需要手工打补丁。

## 4. 分别运行四组并记录资源

分别放到各自计算作业中运行，避免四组争用同一份 CPU／内存：

```bash
bash "$REPO/benchmarks/cactus_unchop/run.sh" control "$GFA" "$WORK/results/control"
bash "$REPO/benchmarks/cactus_unchop/run.sh" v1      "$GFA" "$WORK/results/v1"
bash "$REPO/benchmarks/cactus_unchop/run.sh" v2      "$GFA" "$WORK/results/v2"
bash "$REPO/benchmarks/cactus_unchop/run.sh" v3      "$GFA" "$WORK/results/v3" 32
```

control/v1 严格使用原管道 `vg convert -g -p INPUT | vg mod -u -`。v2 使用 `vg convert -g -p --unchop INPUT`；v3 再加 `--unchop-threads 32`。融合版执行同样的导入与 unchop，不改变参考或图处理参数；v3 需分配多核。

每组生成 `result.vg`、`time.log`、`cpu_memory.tsv`、`summary.json` 和 `run.log`。每 5 秒记录实际用核数及进程 RSS 之和；同时保留 GNU time 的最大单进程 RSS。RSS 求和可能重复计算共享页，采样峰值也不是瞬时峰值。psutil 已是 Toil 的依赖。已有输出目录会被拒绝，避免覆盖。

## 5. 检查图结果与资源

```bash
bash "$REPO/benchmarks/cactus_unchop/verify.sh" "$WORK/results"
```

验证时一次加载一个图，比较节点 ID／序列、全部双向邻接、路径元数据及完整有序 step 的 SHA256 指纹，包含未被路径覆盖的结构；忽略序列化存储布局。四次运行均成功且指纹全部相同才输出 PASS，随后打印耗时、CPU、内存表。

已完成：80 个小型 PackedGraph 的原版／优化版、串行／2／4／8 线程、序列化重读／直接处理对照（环状路径仅做原版差分对照），以及监控程序小样本检查。完整 vg CLI 和 chr21 实测仍需在集群执行以上命令。
