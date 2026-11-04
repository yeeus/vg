# 原始 chr21 final 与新 candidate 的验证

旧版 `verify.py` 要求两边都是 `run.py` 的结果根目录，里面有 `summary.json`、`inputs.log` 和 `final/`。因此把原 chr21 根目录 `./` 传入后，它在查找 `./summary.json` 时退出，尚未比较任何结果文件。

新版增加 `--legacy-control`：**第一个参数直接传旧 `final/`，第二个参数仍传 candidate 结果根目录**。旧记录的资源与输入元数据记为不可用；新 candidate 仍要求真实 `summary.json` 的 `exit_code=0`。无需给旧结果伪造 summary 或复制 candidate 的 inputs.log。

你提供的新 candidate 已成功结束；清单中的 32 个主要交付文件均有旧版对应项。旧目录还混有后处理 VCF、参考 FASTA、工作脚本，以及本轮未请求生成的 `chr21.full.hal`。这些旧版额外文件需明确声明；脚本只允许忽略**旧版独有**的匹配项，两边共有的文件始终比较。其他新增、缺失文件会停止验证并写入清单，避免只比较交集后误报 PASS。

## 1. 更新一个 Python 文件

不需要编译 vg。在可访问 GitHub 的机器下载 [verify.py](verify.py)，上传并替换 B 上：

```text
/public/home/u12518101/softwares/vg-join-candidate-r2/benchmarks/cactus_join/verify.py
```

若 B 可直接访问 GitHub，也可执行下面的下载命令。正式运行请使用本次提供的固定 commit；这里记录当前分支快照：

```bash
SRC="$HOME/softwares/vg-join-candidate-r2"
VERIFY_REF=cactus-7f34bb7-lowmem
curl --fail --location \
    "https://raw.githubusercontent.com/yeeus/vg/$VERIFY_REF/benchmarks/cactus_join/verify.py" \
    -o "$SRC/benchmarks/cactus_join/verify.py.new"
mv "$SRC/benchmarks/cactus_join/verify.py.new" "$SRC/benchmarks/cactus_join/verify.py"
```

## 2. 从原 chr21 目录运行，使用 16 线程

沿用已跑通 candidate 的 B 运行环境，在 Slurm 验证作业内执行。`source ./cactus.config.sh` 用于恢复实际运行库路径；编排脚本会把 candidate 私有 `lib/` 放到图验证子进程的最前面。

```bash
#!/usr/bin/env bash
set -euo pipefail
source ./cactus.config.sh

SOFT="$HOME/softwares"
SRC="$SOFT/vg-join-candidate-r2"
PREFIX="$SOFT/cactus-join-candidate-r2"
WORK="$PWD/join_bench_r2"
VERIFY_THREADS=16

LD_LIBRARY_PATH="$PREFIX/candidate/lib:${LD_LIBRARY_PATH:-}" \
    "$PREFIX/candidate/bin/vg" version

/usr/bin/time -v -o "$WORK/verify_original.time.log" \
python3 -u "$SRC/benchmarks/cactus_join/verify.py" \
    "$PWD/final" "$WORK/candidate" \
    --legacy-control \
    --allow-control-extra 'chr21.full.hal' \
    --allow-control-extra 'chr21.biallele*' \
    --allow-control-extra 'GRCh38.chr21.fa*' \
    --allow-control-extra 'work.sh*' \
    --vg "$PREFIX/candidate/bin/vg" \
    --threads "$VERIFY_THREADS" --tmp "$WORK" --output "$WORK/verify_original" \
    > "$WORK/verify_original.log" 2>&1
```

`verify_original` 应为新的输出目录；已存在时会停止，保留旧验证记录。输入使用当前 `candidate/final`；`candidate_backup_old` 保留作历史日志，不作为本次结果输入。旧 `final`、新 `final` 及备份目录均只读。

GFA 排序、图内指纹和多文件流式比较沿用多线程；大图逐个加载，避免同时加载两张 XG。`--tmp` 所在磁盘需容纳解压 GFA 和外部排序临时文件；内存应足以加载一张 XG，16 线程本身不是内存上限。

## 3. 通过标准及失败定位

只有进程退出码 0、`verify_original/report.json` 的 `status="complete"` 且 `pass=true`，才表示本次范围内的输出全部通过既定比较。

- `files`：每个实际比较文件的结果。图比较完整节点、边、路径；XG 另要求全索引字节一致。GFA 比较完整记录且保留路径内部顺序；VCF 比较全部字段、样本及相位，仅忽略 fileDate。其余索引/统计保留原有严格检查。
- `ignored_control_outputs`：实际排除的旧版独有文件，逐项记录；这部分不属于 PASS 的验证范围。`chr21.stats/` 没有被排除，若出现文件缺失或差异，会如实报出。
- `control_only`、`candidate_only`：原始清单差异。若 `status="inventory_mismatch"`，先检查这些字段；不要直接把未知缺失项全部忽略。
- `input_metadata_check="unavailable_for_legacy_control"`、旧 `workflow_resources.control=null`：旧基线没有本轮 wrapper 元数据，不代表已经核实输入来源或统计出了旧作业资源。

二进制索引出现 FAIL 时保留失败状态，可能还需针对格式解释差异，不自动降级为“图序列一样就通过”。本地已通过正常/历史两种模式的实际校验测试，包括图多线程指纹、相位/路径/索引改变、未授权额外文件、缺失输出及未成功的 candidate 检出；完整 chr21 尚需在 B 执行上述验证。

新 summary 的约 5.52 小时是**最后一次续跑**。完整性能比较还需计入之前尝试和备份日志；本次历史模式只比较交付文件，不自动合计全程资源。
