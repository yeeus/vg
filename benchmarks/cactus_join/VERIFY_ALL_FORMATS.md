# 统一的完整输出验证

本版 verify.py 已合并先前的 GBZ、ODGI 和 TBI 复查。使用一个 Python 文件即可执行原来的两种验证命令。需要原有 candidate vg、GNU sort，以及 PATH 中的 odgi、tabix。也可用 --odgi 和 --tabix 指定可执行文件。

| 文件 | PASS 的条件 |
|---|---|
| VCF | 全部字段和记录一致，仅忽略 fileDate 及 bcftools 命令末尾的运行日期 |
| TBI | 两边各自的索引都能查询出本侧 VCF 的全部记录，并与重建索引核对；有效载荷不同则进一步比较 16 kb 网格查询 |
| GBZ | 二进制字节一致，或完整解码后的 GFA 记录及 GBWT 元数据、标签一致 |
| ODGI | 二进制字节一致，或完整解码后的 GFA 记录一致 |
| GFA | 完整记录按行排序后相同，保留每条路径内部的节点、方向和次序 |
| VG | 严格图指纹一致 |
| XG | 严格图指纹和完整索引字节均一致 |
| HAL | 所有 HDF5 数据集及属性一致 |
| 其他输出 | 完整字节或解压后的完整字节一致 |

TBI 包含 BGZF 压缩文件中的虚拟偏移。VCF 记录相同而压缩块布局不同，也可能产生不同的 TBI。新版对每个 TBI 都检查它自己的 VCF，避免用两边索引是否逐字节相等来判定有效性。

GBZ、ODGI 的存储布局可以不同。字节不同时，新版实际解码并比较所有 GFA 记录。GBZ 另外比较 GBWT 元数据和标签。图内容、路径方向、路径次序、样本信息或标签有差异时仍会 FAIL。解码器出错会记录 ERROR，并使整体验证失败。

## 运行

保留原命令参数，使用新的输出目录以保存之前的报告。

~~~bash
python3 -u "$SRC/benchmarks/cactus_join/verify.py" \
    "$WORK/control" "$WORK/candidate" \
    --vg "$PREFIX/candidate/bin/vg" --threads 16 \
    --tmp "$WORK" --output "$WORK/verify_final" \
    > "$WORK/verify_final.log" 2>&1
~~~

历史 final/ 比较继续使用 --legacy-control 和原来的 --allow-control-extra 参数，将输出目录改为 verify_original_final。

普通文件和 TBI 跨文件并行检查。每次只加载一个大图，导出与外部排序分配线程预算。report.json 保留每个文件的检查方式、字节是否一致、解码内容是否一致和错误信息。任何文件失败都使整体 pass 为 false。输入和交付文件清单的核对规则沿用原版。

通过标准为退出码 0，报告 status 为 complete、pass 为 true，passed 等于 total，全部文件均通过。历史独有文件继续逐项列在 ignored_control_outputs。

## 本地验证

~~~bash
python3 benchmarks/cactus_join/test_verify_formats.py \
    --vg /path/to/vg --odgi /path/to/odgi
~~~

测试调用真实 vg、ODGI、bgzip 和 tabix。包含有效存储差异、无可选 TBI 尾部字段的有效索引、基因型相位改变、GBWT 标签改变、ODGI 路径名改变、两边完全相同但已损坏的 TBI、GBZ 解码失败及历史目录模式。完整 chr21 的判定仍以新报告为准。
