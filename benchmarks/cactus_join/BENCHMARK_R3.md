# chr21 join r3

保留一组 control 和一组 candidate。control 的 vg 基于 `f2ed0bbd4`，仅应用已验证的 deconstruct header 修复。沿用 r2 的 control 裁剪和落盘方式。

candidate 的 full worker 为 unchop 只读分析申请 4 核。Full 的 PackedGraph 在翻转节点时搬移已有路径步骤及成员记录，仍使用原来的新节点编号。Clip 在 force 模式下按累计原路径步骤数分批释放已替换的路径。保留候选现有的图参数、GFAffix 线程和图验证。r2 的 chr21 阶段缓存记录导入 11,364.8 秒、unchop 31,683.8 秒、写出 1,413.57 秒。r3 优先并行 unchop 的只读部分。

## 在 A 编译

使用 r2 的 GCC、Cactus 和依赖环境。先准备独立的原版 vg 源码目录，并检出完整子模块。若 A 无法联网，按[原离线方式](CLUSTER_A_B_ENVIRONMENT.md)在联网端准备后再传入。

```bash
SOFT="$HOME/softwares"
SRC="$SOFT/vg-join-candidate-r3"
BASE="$SOFT/vg-control-f2ed0bbd4-source"
R2="$SOFT/cactus-join-candidate-r2"
R3="$SOFT/cactus-join-candidate-r3"
FIXED="$SOFT/vg-control-f2ed0bbd4-fixed"

git clone --no-checkout https://github.com/vgteam/vg.git "$BASE"
git -C "$BASE" checkout --detach f2ed0bbd4f7d1e7f8c8f4df4a84018f388194d51
git -C "$BASE" config submodule.deps/cairo.url https://gitlab.freedesktop.org/cairo/cairo.git
git -C "$BASE" config submodule.deps/pixman.url https://gitlab.freedesktop.org/pixman/pixman.git
git -C "$BASE" submodule update --init --recursive

# SRC 检出本轮给出的 r3 commit。R2 使用已修复 candidate VCF 的 A 集群构建目录。
bash "$SRC/benchmarks/cactus_join/build_control.sh" "$BASE" "$FIXED" 8
bash "$SRC/benchmarks/cactus_join/upgrade_r3.sh" "$R2" "$FIXED" "$R3" 8
```

通过标准是 `PASS r3 control and candidate`。测试对比完整的小图 deconstruct VCF，以及 full、clip、filter 图、GBZ 和 XG。把 R3 的 `control/`、`candidate/` 及 `source.commit` 传到 B，连同 r3 的 benchmark 脚本。

## 在 B 测试

从原 chr21 目录运行，每条命令用独立 Slurm 作业，资源与节点类型匹配。首轮用此前的 56 核及 480G，保持原 `04.join.sh`。

```bash
SRC="$HOME/softwares/vg-join-candidate-r3"
PREFIX="$HOME/softwares/cactus-join-candidate-r3"
SCRIPT="$PWD/04.join.sh"
WORK="$PWD/join_bench_r3"

# 作业一
python3 "$SRC/benchmarks/cactus_join/run.py" control "$PREFIX" "$WORK/control" "$SCRIPT"
# 作业二
python3 "$SRC/benchmarks/cactus_join/run.py" candidate "$PREFIX" "$WORK/candidate" "$SCRIPT"

rg 'phase=(import|unchop|serialize) |clip_phase=' "$WORK/candidate/logs/04.join.log"
```

候选日志里 `clip_phase=` 的 `peak_rss_kib` 是截至该阶段的累计最高值。比较两次 `clip-vg` 的峰值和整个融合命令耗时。分阶段计时用于定位收益。

## 多线程验证

```bash
python3 "$SRC/benchmarks/cactus_join/verify.py" "$WORK/control" "$WORK/candidate" \
    --vg "$PREFIX/candidate/bin/vg" --threads 16 --tmp "$WORK" --output "$WORK/verify"
```

若首轮仍有日期或二进制封装差异，按[现有复查步骤](VERIFY_HISTORICAL.md)检查 VCF、解码图和 TBI，保留全文件清单。检查完整报告里的 `pass` 和每个文件的结果。
