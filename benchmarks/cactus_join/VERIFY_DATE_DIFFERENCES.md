# chr21 验证中 20 个 FAIL 的解释

本次报告完整运行结束：37 项中 17 PASS、20 FAIL。这表示在当前比较规则下存在差异，不等于已经发现 20 个图或基因型错误。

| 类型 | FAIL 数 | 当前证据 |
|---|---:|---|
| VCF | 8 | 用户已提供的 `chr21.raw.vcf.gz` 元数据差异只有 bcftools 命令尾部的日期；此前比较在这里便返回 FAIL，尚不能据此判断变异记录是否相同 |
| TBI | 7 | 比较的是索引文件字节；索引包含压缩文件中的位置，VCF 压缩布局改变也会导致索引不同，不能当作 7 个独立的变异差异 |
| GBZ | 4 | 目前只有整个二进制文件字节不同；是否仅存储/编号顺序不同，尚未验证 |
| ODGI `.og` | 1 | 同样只有二进制字节不等的证据；尚未核对其导出图和路径 |

已通过的证据很强：full、clip、gref、SV 四份 GFA 的完整记录一致（允许记录之间重排，保留路径内部顺序）；clip XG 的节点、邻接和完整路径摘要完全相同，且整个 XG 文件字节相同。其图指纹记录 3,516,917 个节点、6,471 条路径和 2,332,833,946 个路径步。

因此，已验证的 full/clip/gref 图记录和 clip XG 保持一致。但这些 PASS 不能代替 filter GBZ、其他 GBZ 内部索引以及 ODGI 的独立验证。

## 已确认的 VCF 比较遗漏

用户实际得到的元数据差异：

```diff
-##bcftools_concatCommand=concat -O z --threads 6 0.clip.raw.vcf.gz; Date=Fri Oct 16 09:45:56 2026
+##bcftools_concatCommand=concat -O z --threads 6 0.clip.raw.vcf.gz; Date=Wed Nov  4 04:17:53 2026
```

原验证器忽略 `##fileDate`，却漏掉了 bcftools 写在 `##bcftools_*Command` 尾部的日期。Cactus 的 `vcf_cat()` 确实调用 `bcftools concat`，见 [固定版本源码](https://github.com/ComparativeGenomicsToolkit/cactus/blob/7f34bb7a65af5816835ef79b7ae5e2f3c277b305/src/cactus/refmap/cactus_graphmap_join.py#L2626)。

本次修复**只剔除这种命令行末尾的 Date**，保留完整命令参数、软件版本、contig/INFO/FORMAT 定义、样本列、记录顺序和每个变异字段。没有把整行 bcftools 元数据忽略，也没有放宽任何二进制文件判定。

## 下一步只复查 8 个 VCF

无需重跑 graph，也不重复已完成的 GFA/XG 检查。只更新同一目录中的 `verify.py` 和 `recheck_vcfs.py`；后者调用前者的真实比较实现。

在可联网的机器下载这两个文件后上传 B 的 `vg-join-candidate-r2/benchmarks/cactus_join/`；若 B 可联网，可使用：

```bash
set -euo pipefail
SRC="$HOME/softwares/vg-join-candidate-r2"
VERIFY_REF=cactus-7f34bb7-lowmem
for name in verify.py recheck_vcfs.py; do
    curl --fail --location \
        "https://raw.githubusercontent.com/yeeus/vg/$VERIFY_REF/benchmarks/cactus_join/$name" \
        -o "$SRC/benchmarks/cactus_join/$name.new"
    mv "$SRC/benchmarks/cactus_join/$name.new" "$SRC/benchmarks/cactus_join/$name"
done
```

下载使用本次给出的固定 commit。然后从 chr21 目录，在已分配的计算资源中运行：

```bash
SRC="$HOME/softwares/vg-join-candidate-r2"
WORK="$PWD/join_bench_r2"
/usr/bin/time -v -o "$WORK/recheck_vcf_dates.time.log" \
python3 "$SRC/benchmarks/cactus_join/recheck_vcfs.py" \
    "$WORK/verify_original/report.json" \
    --threads 16 --output "$WORK/recheck_vcf_dates.json" \
    > "$WORK/recheck_vcf_dates.log" 2>&1
```

这是低内存流式比较，每个 VCF 对是一个任务；线程上限为 16，本次最多 8 对并行。PASS 会扫描到文件末尾；有差异时记录首处差异及周边文本。

- `vcf_pass=true`：8 个 VCF 在仅排除运行日期后，全部元数据、样本列及变异记录完全一致。
- 仍有 FAIL：看 `files[].first_difference`。`header_difference=true` 表示首处差异在头部；否则是记录内容。`field_number` 为 VCF 字段号，1–9 分别是 CHROM/POS/ID/REF/ALT/QUAL/FILTER/INFO/FORMAT，10 起是样本列。
- `previous_non_vcf_failures`：保留原报告中未解决的 TBI/GBZ/ODGI 失败。该脚本不对它们重新判断，也不把 VCF_ONLY PASS 写成全流程 PASS。

原 `verify_original/report.json` 和所有输入保持不变。二进制文件后续应检查图、路径、样本元数据及索引功能，不应为了让报告变绿而跳过失败项。

本地回归已确认：日期单独变化可通过；命令参数、软件版本、相位及其他内容变化仍失败；VCF 专项复查不会掩盖原二进制失败。真实 chr21 的记录内容是否全部一致，以本次复查输出为准。
