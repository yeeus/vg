# r4：只修复 Full / Clip 的路径数组深拷贝

这一轮只有一个候选：**r3 + clip-vg 的 PackedGraph 路径数组扩容修复**。复用已有 r3 染色体缓存，只重新执行两个受影响的 `clip-vg` 命令。原 `04.join.sh`、vg、GFAffix、裁剪参数和路径处理顺序保持不变。

## 修改与验证范围

`PackedPath` 的步骤/链接数组拥有大量内存；其底层 SDSL 移动构造没有 `noexcept`。`std::vector::reserve()` 因而可能复制所有已有路径数组。Full 删除 minigraph 片段、Clip 切断路径时都会新增路径，触发这次扩容。补丁先分配新的外层容器，再显式移动数组所有权，保持路径顺序、路径编号与步骤偏移。只修改 clip-vg 使用的 STL backend，Mapped backend 不改。

旧 r3 的 chr21 Full / Clip 峰值分别约 418.3 / 419.4 GiB。**本轮目标是两步分别不超过 300 GiB，且图内容验证全部 PASS；300 GiB 是验收目标，不是已经测得的 chr21 结果。**

使用同一固定 jemalloc `54eaed1d8b56b1aa528be3bdd1877e59c56fa90c` 的本地 60,000 节点差分测试：

| 步骤 | r3 RSS（KiB） | r4 RSS（KiB） | 内存降低 | r3 / r4 耗时 |
|---|---:|---:|---:|---:|
| Full | 267,416 | 180,884 | 32.4% | 1.02 / 0.83 秒 |
| Clip | 308,328 | 197,816 | 35.8% | 25.83 / 26.26 秒 |

Full 的 60,001 个输出节点、323 条路径与 Clip 的 60,000 个输出节点、641 条路径都通过逐节点/边/有序路径步骤比较。该合成测试支持根因和内容等价性，不代表 chr21 将获得相同比例的改善；本轮主要降低内存，不承诺 Clip 提速。

本轮两项阶段验证覆盖全部节点 ID/序列、双向邻接、路径名称/元数据/环形标记和完整有序带方向步骤。它不冒充一次新的全流程 37 文件验证。r3 的 37/37 已有结果继续保留。

## 1. 在 A 增量编译

激活与 r3 相同的 GCC/Cactus 环境。本轮仅编译 clip-vg 及其 libbdsg，不重新编译整个 vg。需要 A 上原有的 r2/r3 构建目录；使用新目录，保留旧安装。

```bash
SOFT="$HOME/softwares"
SRC="$SOFT/vg-join-candidate-r4"
R2="$SOFT/cactus-join-candidate-r2"
R3="$SOFT/cactus-join-candidate-r3"
R4="$SOFT/cactus-join-candidate-r4"

git clone --no-checkout https://github.com/yeeus/vg.git "$SRC"
# 此处使用本轮回复提供的完整固定 commit。
git -C "$SRC" checkout --detach <R4_COMMIT>
bash "$SRC/benchmarks/cactus_join/upgrade_r4.sh" "$R3" "$R2" "$R4" 8
```

通过标准：`PASS r4 clip-vg build and exact graph checks`。构建会用新旧两个真实 clip-vg 测试 Full/Clip，并以 1/4 线程执行同一严格图验证。编译日志在 `$R4/build.clip.candidate.log`。

仍沿用原来的 A→B 传输方式：把 `$R4/candidate/`、`$R4/source.commit`、`$R4/reused_r3.prefix` 和本轮 `$SRC` 的 benchmark 脚本传到 B 对应目录。B 不需要编译源码或安装新的图依赖。

## 2. 在 B 从现有 chr21 缓存测试

在 chr21 目录、已有 Slurm 计算资源中运行。最后一轮保留 r3 相同的外层资源和节点类型；先测真实 RSS，再决定其他染色体申请多少内存。

```bash
SRC="$HOME/softwares/vg-join-candidate-r4"
PREFIX="$HOME/softwares/cactus-join-candidate-r4"
CACHE="$PWD/join_bench_r3/candidate/stage_cache"
WORK="$PWD/join_bench_r4"

python3 -u "$SRC/benchmarks/cactus_join/clip_stages.py" run \
    --stage full --cache "$CACHE" --prefix "$PREFIX" --out "$WORK"

python3 -u "$SRC/benchmarks/cactus_join/clip_stages.py" run \
    --stage clip --cache "$CACHE" --prefix "$PREFIX" --out "$WORK"
```

两条命令顺序运行；也可分别放入两个已有资源配置的作业。脚本自动检查缓存标记与保存大小，拒绝覆盖同名测试目录。

Full 的实际命令来自 `27e9f0581e2fa662ae912b1b/04-clip-0.json`：

```bash
clip-vg 03-unchop-0.gfaffixed -f -e GRCh38 -d _MINIGRAPH_ -L -F
```

Clip 先把 `27e9f0581e2fa662ae912b1b/04-clip-1.clip` 复制到新目录，对副本执行原 `join_vg()` 中的 `vg ids -j`，再运行 `d5a62368ba95a450c7748df9/04-clip-0.json` 的命令：

```bash
vg ids -j clip.input.vg
clip-vg clip.input.vg -f -e GRCh38 -d _MINIGRAPH_ \
    -u 10000 -a _MINIGRAPH_ -I 100000 -k 50000 -T -1.0
```

对照输出就是已有 r3 两个 `04-clip-0.stage0`，不新增 control 作业。Clip 使用旧 r3 Full 的输出，以隔离这一次裁剪的内存变化；新 Full 输出则独立验证与旧 Full 完全相同。后续融合 vg 命令的实现没有变化，本次不重复执行。

新生成数据约 410 GiB：Full 结果约 192 GiB、Clip 输入副本约 192 GiB、Clip 结果约 23 GiB；另留运行余量。原 r3 缓存不会被改写，也不使用硬链接。

每个阶段的输出在 `$WORK/full/`、`$WORK/clip/`：

- `result.vg`：新结果。
- `time.log`：GNU time 的 wall/CPU/Maximum resident set size；该 Linux RSS 单位是 KiB。
- `cpu_memory.tsv`、`process_cpu_memory.tsv`：每 5 秒采样。
- `run.log`：包含 `clip_phase=` 的日志；其中峰值是截至该阶段的累计最高值。
- `summary.json`：退出状态、资源汇总。
- `command.json`：实际命令和所比较的 r3 文件。

Clip 的复制/编号同步单独记在 `prepare.log`、`prepare.time.log`，不混入 clip-vg 本身的耗时与峰值。

## 3. 多线程 verify

两步都成功后，在有足够内存的计算资源中执行：

```bash
python3 -u "$SRC/benchmarks/cactus_join/clip_stages.py" verify \
    --prefix "$PREFIX" --out "$WORK" --threads 16 \
    > "$WORK/verify.log" 2>&1
```

通过标准：`PASS full`、`PASS clip`，且 `$WORK/verify/report.json` 的 `pass` 为 `true`。每张图的遍历/散列使用 16 线程；加载和验证两张图仍顺序执行，避免内存相加。这里比较图内容，允许 PackedGraph 的容量/序列化布局变化。

请回传两个 `time.log`、两个 `summary.json` 及 `verify/report.json`。这些足以判断此次内存是否达标，不必上传几百 GiB 的图。

## 4. 通过后用于其他染色体

继续使用原来的 `04.join.sh`，只换隔离 runtime 与新输出目录：

```bash
python3 "$SRC/benchmarks/cactus_join/run.py" candidate "$PREFIX" \
    "$PWD/join_bench_r4/candidate" "$PWD/04.join.sh"
```

这会生成新的全流程结果。若需要与 chr21 的 r3 37 个最终文件再次整体对照，完整跑完后使用已有统一验证器：

```bash
python3 -u "$SRC/benchmarks/cactus_join/verify.py" \
    "$PWD/join_bench_r3/candidate" "$PWD/join_bench_r4/candidate" \
    --vg "$PREFIX/candidate/bin/vg" --threads 16 \
    --tmp "$PWD/join_bench_r4" --output "$PWD/join_bench_r4/verify_all"
```

单阶段内存达标加上两项严格图验证后，不必为测内存再重复整条 chr21 join；上述完整比较是重新运行全流程后才适用的验证范围。
