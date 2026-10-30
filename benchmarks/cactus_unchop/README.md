# Cactus 7f34bb7：低内存对照测试

原版 vg：`f2ed0bbd4f7d1e7f8c8f4df4a84018f388194d51`。新代码在 `cactus-7f34bb7-lowmem` 分支；依赖由 submodule commit 固定，一次编译支持下列独立配置。

**旧 vg.control 与实验版共用过 libhandlegraph.so，旧 control/V1 不能用于判断原版收益。先隔离原版依赖，再开始新一轮；保留正在运行的旧测试。**

| 模式 | 内容／输入 |
|---|---|
| control | 原版 `convert -g -p GFA \| mod -u -` |
| v2 | 去无用缓存、融合导入与 unchop；本轮内部基线 |
| v4 | v2 + 数字 ID 直接查找；位图最多 64 MiB，特殊名称／大范围回退 |
| v5 | v4 + 跳过未请求的序列化结构统计 |
| v6 | v5 + 按路径并行重编号 |
| v7 | v6 + 已有的并行邻接检查，可选 |
| xg-control / xg-stream / xg-compact | 同一 GBZ；原实现／省一次路径遍历／再按实际位宽分配索引数组 |
| full-control / full-next | 同一 unchop 结果；原 full 管道／序列化与重编号优化 |
| clip-control / clip-fused | 同一 full VG；原 clip 管道／融合后三段 vg clip |
| filter-control / filter-fused | 同一 clip VG；原 filter 管道／融合三段 vg clip |

## 1．新目录构建，恢复独立原版

先激活原 Cactus/GCC 环境。以下路径自行替换；不要在正在跑测试的旧目录构建。

```bash
OLD_REPO=/path/to/existing/vg-unchop-bench
CONTROL_PREFIX=/path/to/vg-control-f2ed-runtime
git clone --filter=blob:none --branch cactus-7f34bb7-lowmem https://github.com/yeeus/vg.git vg-lowmem-next
cd vg-lowmem-next
NEXT_REPO="$PWD"
# 如需锁定聊天中给出的具体快照，在这里 git checkout --detach COMMIT
git submodule update --init --recursive

# 仅重编原版 libhandlegraph，配合原 vg.control；不重编整个原 vg。
bash benchmarks/cactus_unchop/freeze_control.sh "$OLD_REPO/bin/vg.control" "$CONTROL_PREFIX" 4
VG_CONTROL="$CONTROL_PREFIX/bin/vg.control"

make -j 16 > build.next.log 2>&1 && cp bin/vg bin/vg.experiment
VG_EXPERIMENT="$NEXT_REPO/bin/vg.experiment"
git rev-parse HEAD > build.source.log
git submodule status --recursive >> build.source.log

# 必须通过后再跑大图；脚本为各二进制指定各自的库目录。
VG_CONTROL="$VG_CONTROL" VG_EXPERIMENT="$VG_EXPERIMENT" python3 benchmarks/cactus_unchop/test_cli.py
VG_CONTROL="$VG_CONTROL" VG_EXPERIMENT="$VG_EXPERIMENT" python3 benchmarks/cactus_unchop/test_clipping.py
```

`freeze_control.sh` 检查原二进制版本，固定旧库为 `ae42926…`；`libraries.log` 必须指向独立目录。后续通过 `run_next.sh` 运行，确保使用该目录的库。

## 2．unchop：同一 GFA，各组单独提交

复用原 `chr21.vg.gfaffixed.gfa`；`WORK` 使用新目录。以下命令各自放入一个资源独立的计算作业。

```bash
GFA=/path/to/unchop_bench/input/chr21.vg.gfaffixed.gfa
WORK=/path/to/unchop_bench_next
RUN="$NEXT_REPO/benchmarks/cactus_unchop/run_next.sh"
bash "$RUN" control "$GFA" "$WORK/results/control" "$VG_CONTROL"
bash "$RUN" v2      "$GFA" "$WORK/results/v2"      "$VG_EXPERIMENT"
bash "$RUN" v4      "$GFA" "$WORK/results/v4"      "$VG_EXPERIMENT"
bash "$RUN" v5      "$GFA" "$WORK/results/v5"      "$VG_EXPERIMENT"
bash "$RUN" v6      "$GFA" "$WORK/results/v6"      "$VG_EXPERIMENT" 4
# 可选：v7，同时启用邻接检查并行。
```

## 3．验证：一次加载一个图，图内并行检查路径

```bash
VG_VERIFY="$VG_EXPERIMENT" bash "$NEXT_REPO/benchmarks/cactus_unchop/verify.sh" \
    "$WORK/results" 8 control v2 v4 v5 v6
```

保留完整节点、双向邻接、路径元数据和全部有序 step；8 指路径检查线程数，加载等步骤仍串行。新指纹格式为 v2，不能直接比较旧指纹；所有组由同一个新验证器重算。没有同时加载多份大图或缓存完整路径序列。

## 4．XG：同一份 chr21.gbz

```bash
GBZ=/path/to/chr21.gbz
bash "$RUN" xg-control "$GBZ" "$WORK/xg/xg-control" "$VG_EXPERIMENT" 63
bash "$RUN" xg-stream  "$GBZ" "$WORK/xg/xg-stream"  "$VG_EXPERIMENT" 63
bash "$RUN" xg-compact "$GBZ" "$WORK/xg/xg-compact" "$VG_EXPERIMENT" 63
python3 "$NEXT_REPO/benchmarks/cactus_unchop/verify_xg.py" "$WORK/xg"
```

三组均运行 `vg convert -x GBZ -t 63`，以记录在 `environment.log` 的开关选择实现；基线也用同一次编译，减少编译器差异。验证要求完整 XG 逐字节一致，使用小缓冲；不一致则停止并保留文件，不能只凭图拓扑相同认定索引正确。

## 5．full、clip、filter：成对测试

参数对应 chr21 日志：GRCh38 主参考、filter=132。若更改参考或配置，不能照搬这组硬编码参数。上游成功后再运行下游；每组成对比较共用同一份输入。

```bash
UNCHOP="$WORK/results/v6/result.vg"
bash "$RUN" full-control "$UNCHOP" "$WORK/full/full-control" "$VG_CONTROL"
bash "$RUN" full-next    "$UNCHOP" "$WORK/full/full-next"    "$VG_EXPERIMENT" 4
VG_VERIFY="$VG_EXPERIMENT" bash "$NEXT_REPO/benchmarks/cactus_unchop/verify.sh" "$WORK/full" 8 full-control full-next

# full 对照通过后共用这份 VG；单染色体 vg ids -j 不增加编号偏移。
FULL="$WORK/full/full-control/result.vg"
bash "$RUN" clip-control "$FULL" "$WORK/clip/clip-control" "$VG_CONTROL"
bash "$RUN" clip-fused   "$FULL" "$WORK/clip/clip-fused"   "$VG_EXPERIMENT"
VG_VERIFY="$VG_EXPERIMENT" bash "$NEXT_REPO/benchmarks/cactus_unchop/verify.sh" "$WORK/clip" 8 clip-control clip-fused

CLIP="$WORK/clip/clip-control/result.vg"
bash "$RUN" filter-control "$CLIP" "$WORK/filter/filter-control" "$VG_CONTROL"
bash "$RUN" filter-fused   "$CLIP" "$WORK/filter/filter-fused"   "$VG_EXPERIMENT"
VG_VERIFY="$VG_EXPERIMENT" bash "$NEXT_REPO/benchmarks/cactus_unchop/verify.sh" "$WORK/filter" 8 filter-control filter-fused
```

融合保留原函数顺序、各阶段参考集合和 min-fragment 值，减少中间读写与并存的图副本；clip-vg 自身算法尚未修改。原 04.join.sh 保持原样，待基准通过后接入。

各组保留 command/version/environment/libraries、GNU time、5 秒总 CPU/RSS、逐进程 CPU/RSS 和 summary。RSS 求和可能重复计算共享页，采样峰值不是瞬时峰值。full/clip 仍可能占用大量内存，先在资源独立的 chr21 作业测试。

本地已通过：80 个 PackedGraph 对照及 1/2/4/8 线程、串行/并行指纹一致性；数字索引边界/回退；序列化字节一致；14 个 XG 小图（含无路径和空路径）在原版/stream/compact 下的图指纹、节点到路径索引、位置查询及完整输出字节一致。完整 vg CLI、clip/filter 融合与 chr21 性能尚待上述集群检查；未承诺加速倍数或 chr1/chr2 内存上限。
