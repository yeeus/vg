# Cactus 7f34bb7：原版与一个低内存候选

只运行 `control` 和 `candidate`，不再运行 V1–V7。原 `04.join.sh` 不改；每组使用独立 jobStore、workDir、final 和日志目录。保持三参考、filter=132 及原输出集合。

## 1. 下载、编译

先激活原来的 Cactus/GCC 环境，确认 `vg version` 为 `v1.76.1-89-gf2ed0bbd4`。需要 GCC≥10、C++20、原 vg 的构建依赖、Meson≥1.3、Rust/Cargo≥1.85、Python及psutil；verify另需 GNU sort、h5diff。依赖说明见 [vg README](../../README.md#compiling-vg)。

```bash
SOFT=/path/to/softwares
SRC="$SOFT/vg-join-candidate-r1"
PREFIX="$SOFT/cactus-join-candidate-r1"
ORIGINAL_VG="$SOFT/cactus-master-7f34bb7/bin/vg"

git clone --filter=blob:none --branch cactus-7f34bb7-lowmem https://github.com/yeeus/vg.git "$SRC"
cd "$SRC"
# 如聊天给出了固定提交，在此执行 git checkout --detach <该提交>。
bash benchmarks/cactus_join/build.sh "$PREFIX" "$ORIGINAL_VG" 16
```

`SRC`、`PREFIX` 均使用新目录。脚本编译一个候选；control 的 vg 使用原二进制和单独构建的原版 libhandlegraph，gfaffix/clip-vg 则在同一编译环境分别构建原版与候选。构建失败会停止；通过小图检查后才输出 `Build and small differential checks passed`。全部构建日志、依赖版本及源码提交保存在 PREFIX。

本候选包括：GFA 导出时检查参考样本；gfaffix 流式输入/路径和紧凑原图校验；融合 GFA 导入与 unchop；融合 full 后四段、clip 后三段、filter 三段；vg 与 clip-vg 各自的路径成员数组原地整理；按路径最多4线程更新编号；直接按位宽构建 XG 索引。保留 gfaffix transformation check、vg validate、vg ids -j、HAL、ODGI 和统计步骤。

## 2. 运行两组完整 join

以下命令从同一个 **chr21 目录**执行；该目录保留原 `cactus.config.sh`、`align/chr21.vg`、HAL 和 SV-GFA。`SCRIPT` 指向原始04脚本。两条命令放在**资源相同、分别分配资源的计算作业**中；首轮保留之前64核/500G预算，不据源码分析提前降低内存。

```bash
SRC=/path/to/softwares/vg-join-candidate-r1
PREFIX=/path/to/softwares/cactus-join-candidate-r1
SCRIPT=/path/to/original/04.join.sh
WORK="$PWD/join_bench_r1"

# 作业一
python3 "$SRC/benchmarks/cactus_join/run.py" control "$PREFIX" "$WORK/control" "$SCRIPT"

# 作业二；独立作业，仍从同一个chr21目录启动
python3 "$SRC/benchmarks/cactus_join/run.py" candidate "$PREFIX" "$WORK/candidate" "$SCRIPT"
```

外层仍需 Slurm 提供正整数 `SLURM_CPUS_PER_TASK` 和 `SLURM_MEM_PER_NODE`；不手工伪造资源分配。可顺序提交，避免共享节点竞争干扰性能比较。失败后保留所有文件，不自动覆盖或重跑。

脚本在加载原配置后切换对应工具/库，候选通过私有 `PYTHONPATH` 覆盖 join 模块，不改共享 Cactus。科学参数原样保留，只隔离运行目录，并设置 Toil `retryCount=0` / `stopOnFirstFailure=True`。非目标配置继续使用原始子命令链，不盲目套用融合。

每组主要看：

- `logs/04.join.log`：实际子命令、阶段耗时、错误；`logs/04.join.time.log`：GNU time。
- `cpu_memory.tsv`、`process_cpu_memory.tsv`、`summary.json`：每5秒总/逐进程CPU、RSS及全程汇总。
- `tools.log`、`inputs.log`、`run.join.sh`：实际工具/动态库、输入配置和完整执行脚本。

## 3. 多线程 verify

两组成功退出后，申请独立验证作业。线程示例为8；内存首轮保留足以加载原图的预算，验证器一次只加载一个图。

```bash
VERIFY_THREADS=8
/usr/bin/time -v -o "$WORK/verify.time.log" \
python3 "$SRC/benchmarks/cactus_join/verify.py" \
    "$WORK/control" "$WORK/candidate" \
    --vg "$PREFIX/candidate/bin/vg" \
    --threads "$VERIFY_THREADS" --tmp "$WORK" --output "$WORK/verify"
```

通过标准：退出码0，`verify/report.json` 的 `pass` 为 `true`，且每个交付文件均为PASS。核对内容如下：

| 文件 | 检查 | 并行方式 |
|---|---|---|
| VG | 节点ID/序列、完整双向邻接、路径元数据和全部有序step | 图内节点/边分块、路径多线程；图逐个加载 |
| XG | 上述图内容，以及整个索引字节 | 图内多线程；完整字节检查另做 |
| GFA/GFA.gz | 全部记录和字段；仅忽略记录之间的输出顺序，保留P/W内部step顺序 | GNU sort多线程，512MiB排序缓冲，外部磁盘排序 |
| VCF/VCF.gz | 所有头部及全部记录、样本、基因型和相位；仅忽略fileDate | 多文件并行流式比较 |
| HAL | 全部HDF5数据集和属性，忽略物理布局/容器时间戳 | h5diff；与其他普通文件检查并发 |
| GBZ、ODGI、haplo及其余索引/统计文件 | 全文件字节；gzip文件比较解压后全内容 | 多文件并行，每个缓冲4MiB |

图指纹升级为v3；不能直接和旧v1/v2指纹比较，verify会用同一个新验证器重算两组。加载图、排序节点、磁盘读取仍有串行部分，`--threads 8`不代表每一秒都使用8核。

GFA外部排序使用磁盘换内存；临时盘需容纳两份最大解压GFA及sort溢写文件。`--tmp`可改为计算节点的大容量scratch。

GBZ/haplo等二进制若因合法存储顺序不同而字节不一致，也会保守地FAIL并保留文件，需进一步核对；不会悄悄退化成“路径序列相同就算通过”。只有全部检查通过，才能称本次交付结果一致。

## 4. 比较资源

`verify/report.json` 包含两组 `workflow_resources`。比较墙钟小时、CPU核小时（`cpu_seconds/3600`）、最大单进程RSS和采样进程树RSS。后者求和可能重复计算共享页；5秒采样可能漏掉瞬时峰值。GNU time另保留文件系统输入/输出计数。

这是候选版本，不预先承诺chr21加速倍数或chr1/chr2内存上限。完整染色体性能及全交付物一致性，以上述两组集群结果为准。

本地已完成Linux工具编译、32组GFAffix对照、40组路径成员整理及9000节点并行指纹检查、四组完整图处理命令链的原版/候选对照（含实际GBZ→XG和交付verify）。私有Cactus命令拼接与原脚本保留已检查；完整Slurm/Toil染色体作业尚未在本地执行。
