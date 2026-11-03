# candidate 的 VCF 崩溃：原因及续跑

## 原因

2026-11-03 的日志显示，candidate 已完成 full/clip 裁剪和图校验，在下列命令生成 VCF 时崩溃：

```bash
vg deconstruct chr21.chr21.gref.vg -C -a -t 55 -P gref_GRCh38 | bgzip --threads 55
```

退出码 139、SIGSEGV，栈顶是 `Deconstructor::add_contigs_to_vcf_header()` 的 `header_lines[i]`。该命令记录的最大 RSS 约 99.9 GiB；全程 GNU time 最大单进程 RSS 约 421.0 GiB，耗时 26:14:54。本次失败由下面的代码缺陷解释，不需要靠增加内存或降低线程数处理。

原版 vg f2ed0bbd4 与候选的这段源码相同：

```cpp
assert(output_vcf.openForOutput(hstr));
```

你提供的编译行明确包含 `-DNDEBUG`，因此整条 `assert(...)` 被删除，连其中必需的 `openForOutput()` 初始化也没有执行。随后传入空 VCF header，`header_lines.size() - 1` 发生无符号下溢，循环越界，落在日志里的第 1353 行。

修复：让初始化无条件执行，失败时明确报错；对空 header 做检查，循环避免无符号下溢。**VCF 算法、线程数和科学参数不变。** 上一轮小图检查遗漏了真实 VCF 生成；现在补上普通参考/gref、1/4 线程、完整 VCF 对照及已知相位 SNP 检查。

源码依据：[原版初始化](https://github.com/vgteam/vg/blob/f2ed0bbd4/src/deconstructor.cpp#L1524)、[原版越界位置](https://github.com/vgteam/vg/blob/f2ed0bbd4/src/deconstructor.cpp#L1352)。

## 1. cluster A 增量编译

你已确认 A 保留完整 `obj/deconstructor.o` 和 `lib/libvg.a`。在 A 沿用原 GCC 12.2/bioinfo 编译环境，给编译任务分配 8 核后执行。B 没有完整编译目录，无须在 B 重编整套 vg。

```bash
VG_BUILD="$HOME/softwares/vg-join-candidate-r1"
FIX_FILES="$HOME/softwares/vg-vcf-header-fix-source"
FIX_OUT="$HOME/softwares/vg-vcf-header-fixed"
CONTROL="$HOME/softwares/cactus-join-candidate-r1/control/bin/vg"

git -C "$VG_BUILD" fetch https://github.com/yeeus/vg.git cactus-7f34bb7-lowmem
FIX=$(git -C "$VG_BUILD" rev-parse FETCH_HEAD)
mkdir "$FIX_FILES"
git -C "$VG_BUILD" archive "$FIX" \
    benchmarks/cactus_join/fix_deconstruct.sh \
    benchmarks/cactus_join/test_deconstruct.py \
    benchmarks/cactus_join/patches/deconstruct-header.patch \
    | tar -x -C "$FIX_FILES"

bash "$FIX_FILES/benchmarks/cactus_join/fix_deconstruct.sh" \
    "$VG_BUILD" "$FIX_OUT" "$CONTROL" 8
```

不 checkout、不 `make clean`，保留现有依赖补丁和构建产物。脚本只修改 `src/deconstructor.cpp` 后增量构建及重新链接。通过标准是最后显示 `PASS incremental VCF header fix`；`test.log` 必须显示普通参考和 gref、1/4 线程 VCF 全部一致，并正确输出 `chr21:2 C>G`、`GT=1|0`。

输出目录保留 `vg`、`vg.sha256`、测试脚本、补丁和构建日志。vg 的版本字符串可能仍显示 r1；这是在原源码目录应用补丁、保留原 HEAD 的结果，以补丁和构建日志为准。

## 2. 传到 B，检查后替换 candidate

把 A 的 `$FIX_OUT` 中 **`vg`、`vg.sha256`、`test_deconstruct.py`** 传到 B 的新目录：

```text
/public/home/u12518101/softwares/vg-vcf-header-incoming/
```

使用你现有的跨集群传输方式；没有提供两集群的 SSH 主机名，所以这里不编造 scp 地址。B 上执行：

```bash
PREFIX=/public/home/u12518101/softwares/cactus-join-candidate-r2
INCOMING=/public/home/u12518101/softwares/vg-vcf-header-incoming

(cd "$INCOMING" && sha256sum -c vg.sha256)
cp "$INCOMING/vg" "$PREFIX/candidate/bin/vg.fixed"
chmod 755 "$PREFIX/candidate/bin/vg.fixed"
python3 "$INCOMING/test_deconstruct.py" \
    "$PREFIX/control/bin/vg" "$PREFIX/candidate/bin/vg.fixed"

# 仅上面的检查通过后执行；保留旧二进制，control 不改
test ! -e "$PREFIX/candidate/vg.before-vcf-header-fix"
cp -p "$PREFIX/candidate/bin/vg" "$PREFIX/candidate/vg.before-vcf-header-fix"
mv "$PREFIX/candidate/bin/vg.fixed" "$PREFIX/candidate/bin/vg"
```

原有 candidate `lib/` 保留：本补丁只重新编译 vg 的一个源文件，不更新依赖库。B 的小图测试用实际私有库加载新二进制，再核对 VCF。

## 3. B 从原 candidate jobStore 续跑

control 继续运行。candidate 的 full/clip 及其前置结果已经写入 jobStore，**这次无需重算 GFAffix、unchop 和裁剪**。保留原 `04.join.sh`、配置、输入及 `join_bench_r2/candidate`；重新申请原资源后，从原 chr21 目录执行：

```bash
SOFT=/public/home/u12518101/softwares
WORK="$PWD/join_bench_r2/candidate"
SCRIPT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["identity"]["script"])' "$WORK/run.json")
python3 "$SOFT/vg-join-candidate-r2/benchmarks/cactus_join/run.py" \
    candidate "$SOFT/cactus-join-candidate-r2" \
    "$WORK" "$SCRIPT" --restart
```

Toil 从失败的 deconstruct 和其他未完成任务继续，已完成任务复用；该次 deconstruct 进程内尚未输出的变异缓冲需要重算。旧日志由 r2 wrapper 移入 `previous_attempts/`。资源比较应计入此前尝试，不能只看续跑耗时。

两组最终成功后，按 [r2 说明](RECOVERY_R2.md#4-两组成功后多线程-verify) 执行完整多线程 verify；VCF 小图测试不替代 chr21 全部交付文件验证。

## 本地验证范围

Linux 下只把原版 `deconstructor.cpp` 用 `-DNDEBUG` 重编并重新链接，四节点小图复现了同一函数、第 1353 行的退出码 139。应用本补丁，继续保留 `-DNDEBUG`，两种参考模式 × 两个工具 × 1/4 线程全部通过，完整 VCF 一致。尚未在 B 运行完整 chr21 的修复版本；以 B 的续跑和最终 verify 为准。
