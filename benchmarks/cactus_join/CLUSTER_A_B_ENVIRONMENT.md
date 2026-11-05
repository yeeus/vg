
# Cluster A / B：Cactus 7f34bb7 + vg cactus_join 构建与运行环境记录

> 记录日期：2026-11-03。适用范围：`yeeus/vg` 的 `cactus-7f34bb7-lowmem`，以 `bbfdabe1372be6600021f7c9d86917bce12c1f73` 为记录基线；`cactus_join` R1、R2 及 VCF-header 单文件修复。**这是一份机器特定的操作记录，不是 Conda lockfile 或干净机器上已经验证的全自动构建脚本。**
>
> 证据：当时的交互命令和日志、Cluster A/B 的实际 `vg version`、`ldd` 和小图 VCF 测试，以及本目录 `README.md`、`RECOVERY_R2.md`、`VCF_HEADER_FIX.md`。未拿到两台机器完整的 `conda list --explicit`，故不声称所有依赖包版本均已精确锁定。

## 1. 先看结论和状态

| 环节 | Cluster A | Cluster B |
| --- | --- | --- |
| 用途 | 联网受限情况下**离线编译** vg、jemalloc、libbdsg、clip-vg | **运行和续跑** Slurm/Toil；本次 VCF 修复没有在 B 编译 |
| 用户目录 | `/share/home/zhanglab/user/chenquanyu` | `/public/home/u12518101` |
| 软件根目录 | `/share/home/zhanglab/user/chenquanyu/softwares` | `/public/home/u12518101/softwares` |
| Conda 环境 | `.../mambaforge/envs/bioinfo` | `.../miniforge3/envs/bioinfo` |
| Cactus | `cactus-master-7f34bb7/cactus_env` | 同名目录及独立激活脚本 |
| C++ 编译器 | **`/share/software/gcc/12.2/bin/g++`**，实际构建已确认 GCC 12.2 | 系统 `/usr/bin/gcc` 为 GCC 4.8.5；**不要用于重新编译 A 的 vg** |
| 链接器 | `/usr/bin/ld` 不兼容旧对象的压缩 `.debug_info`；VCF 修复重链接改用 **GNU ld 2.40** | 未编译，仅需解决可执行文件的动态库加载 |
| 已验证的结果 | R1/R2 部分构建和新的 VCF candidate vg 成功链接；**旧 control VCF 测试 SIGSEGV** | `vg.fixed version` 与 candidate-only VCF 小图测试成功（`TEST_EXIT_CODE=0`）；完整 chr21 续跑/最终 verify 尚无本记录中的 PASS 证据 |

**版本标识**：原始 control vg 为 `v1.76.1-89-gf2ed0bbd4`；新修复 candidate 在 B 上打印 `v1.76.1-93-gd8793fab9`，因为对旧构建树就地应用 VCF 补丁，`vg version` **不能单独证明**补丁版本。以源码补丁、构建日志及传输 SHA-256 为准。R2 编排源码原 commit 为 `679eaab69d940abac9a123292d7b15f81a8885f4`，VCF 修复文档所在 commit 为 `bbfdabe1372be6600021f7c9d86917bce12c1f73`。

## 2. WSL → A → B 的职责边界

1. 在 **WSL Ubuntu 的 Linux 文件系统**中准备 Git 仓库、固定 commit、递归 submodules、离线源码和 Cargo vendor；不要在 Windows NTFS 工作树直接 checkout 完整 vg（`test/`、`doc/wiki` 存在冒号文件名）。
2. 在 WSL 用 Linux `tar` 打包（含 `.git`、子模块和可执行权限），上传 cluster A；集群只做**编译**。遇到无法联网的 submodule（尤其 `jemalloc`），使用经验证的本地 Git URL rewrite，不直接改项目记录的目标 commit。
3. 在 A 编译、运行小样本测试，传输**实际需要的二进制、必要私有库、测试脚本及 SHA-256**到 cluster B；B 的系统库、glibc、GCC 和 Conda 布局不同，不能简单复制 A 的全部 `LD_LIBRARY_PATH` 或假设 A 二进制能直接运行。
4. B 在已分配的 Slurm 作业内使用其本地 Cactus 环境执行；重用已有 R2 jobStore 时加 `--restart`，保留旧日志。验证不通过时不替换生产二进制。

从 WSL 完整下载并传输时，执行 `git submodule status --recursive`，排除以 `-`、`+`、`U` 开头的项；检查嵌套源码、`pre-build.sh` 等文件执行权限；tar 包在两端按实际要求校验 SHA-256。**不要把“Git 克隆成功”当成“所有嵌套源码已完整检出”。**

## 3. Cluster A：从新 Shell 恢复已用过的环境

原 Cactus 激活脚本：

`/share/home/project/zhanglab/HumanGenomeArchive/GSA/APGp2/Graph/activate_cactus_7f34bb7.sh`

它激活 Cactus Python venv，设置 GCC 12.2 和 HDF5 1.12.1 的可执行/动态库优先级。**先激活 `bioinfo`，后 source Cactus；不要手动将整个 `bioinfo/lib` 放到 `LD_LIBRARY_PATH` 最前面**，否则旧的 `libacl.so` / `libattr.so` 组合可能使系统 `ls`、`mv` 报 relocation error。

```bash
source /share/home/zhanglab/user/chenquanyu/mambaforge/etc/profile.d/conda.sh
conda activate bioinfo
source /share/home/project/zhanglab/HumanGenomeArchive/GSA/APGp2/Graph/activate_cactus_7f34bb7.sh --check

SOFT=/share/home/zhanglab/user/chenquanyu/softwares
BIO=/share/home/zhanglab/user/chenquanyu/mambaforge/envs/bioinfo
GCC=/share/software/gcc/12.2/bin
OLD="$SOFT/cactus-join-candidate-r1"
EASY="$OLD/source/hal2vg/deps/libbdsg-easy"

export CC="$GCC/gcc"
export CXX="$GCC/g++"
unset CFLAGS CXXFLAGS LDFLAGS LIBS CPATH LD_PRELOAD

# For R2's libbdsg / clip-vg (and their Boost / handlegraph dependencies).
export CPLUS_INCLUDE_PATH="$BIO/include:$EASY/include"
export CPPFLAGS="-I$BIO/include -I$EASY/include"
export LIBRARY_PATH="$EASY/lib:$BIO/lib"
export PKG_CONFIG_PATH="$BIO/lib/pkgconfig:$BIO/share/pkgconfig:$OLD/source/hal2vg/deps/libbdsg-easy/lib/pkgconfig"

# Keep LD_LIBRARY_PATH from the Cactus activation script.
echo "CC=$CC CXX=$CXX"
"$CXX" --version | head -1
python3 -c 'import cactus, toil, psutil; print("PASS Python dependencies")'
/bin/ls -ld "$SOFT"
for tool in autoconf m4 make git ar nm pkg-config; do
    command -v "$tool" || exit 1
done
pkg-config --libs --static protobuf jansson
```

**成功标准**：C++ 编译器显示 GCC 12.2；Python 可导入 Cactus/Toil/psutil；`ls` 不发生 `libattr/libacl` 错误；`autoconf` 可执行；`pkg-config` 可以解析 Protobuf、Jansson 及其 Abseil 传递依赖。检查通过后才开始耗时的 `make`。不要仅凭提示符中的 `(bioinfo) (cactus_env)` 判断实际 Python/编译器路径。

此前保存过一个**用于人工对照、不是可 source 激活脚本**的环境快照（本次未直接回读其文件内容）：

`/share/home/zhanglab/user/chenquanyu/softwares/r2.cluster_a.build_environment.txt`

下一次真正冻结依赖时，建议从成功的实际 Shell 另存 `env | sort`、`conda list --explicit`、`pkg-config --modversion`、`gcc -v`、`ld --version`、`readlink -f` 和 `git submodule status --recursive`；避免把当前说明误认为完整的二进制可重现性保证。

### A.1 构建工具与已踩过的坑

| 现象 | 真正原因 / 已确认的处理 |
| --- | --- |
| `pre-build.sh`、`sdsl-lite/install.sh` 等 `Permission denied`；`deps/ssw/src/simde` 缺文件 | Windows 工作树及打包不完整；在 WSL/Linux Git 工作树做全递归检出并以 Linux tar 保留权限 |
| Conda GCC 11.2 链接失败（`.relr.dyn`）；混入 base GCC 14.2 | 明确使用**系统 GCC 12.2 的绝对路径**作为 `CC/CXX` |
| `boost/graph/adjacency_list.hpp` 找不到 | 将 `$BIO/include` 和 `libbdsg-easy/include` 加入 C++ 头文件路径 |
| `autogen.sh: autoconf: command not found` | 使用原环境中可运行的 `autoconf`；先做 `command -v autoconf` |
| `/usr/bin/ld: unable to initialize decompress status for section .debug_info` | R1 对象文件/静态库的压缩调试段与旧 ld 不兼容；VCF 增量链接使用 **GNU ld 2.40**（不是重编所有对象的证据） |
| `cannot find -llzma` | Makefile 强制 `-Bstatic`，而 `bioinfo` 有 `liblzma.so`、缺 `liblzma.a`；对该库切换动态链接 |
| Protobuf `Arena::Allocate` 等 undefined reference | 覆盖 `LD_STATIC_LIB_FLAGS` 时漏掉了 `-lprotobuf`；不能只靠源码头文件是否存在判断 |
| `absl::lts_20230802::log_internal::LogMessageFatal` undefined reference | 只手动写 `-lprotobuf -ljansson` 遗漏传递依赖；使用 `pkg-config --libs --static protobuf jansson` 得到**完整有序**的 Abseil 链接参数 |
| `libcairo.so.2: undefined symbol: FT_Get_Color_Glyph_Layer` | 链接成功不代表运行时库正确；需优先加载与 Cairo 匹配的 FreeType |
| 旧 control 的 `vg deconstruct` 退出 139 | **与链接器无关**：`assert(output_vcf.openForOutput(...))` 在 `-DNDEBUG` 下跳过初始化；需要分别修复 control/candidate 的相同缺陷 |

上面的历史错误不是每次重编都要重现的步骤。**不要重复安装、修改无关源码或盲目 `make clean`。**

### A.2 当时 VCF 修复的实际增量重链接方法

已通过的做法是：保留 `vg-join-candidate-r1` 完整构建树，只编译补丁修改的 `src/deconstructor.cpp` 和重新链接 `bin/vg`。不要反复运行 `fix_deconstruct.sh`：补丁已经应用后会再次应用失败。重建前先检查 `git diff` 与补丁状态。

```bash
SOFT=/share/home/zhanglab/user/chenquanyu/softwares
BIO=/share/home/zhanglab/user/chenquanyu/mambaforge/envs/bioinfo
VG_BUILD="$SOFT/vg-join-candidate-r1"
FIX_OUT="$SOFT/vg-vcf-header-fixed"
LINK_DIR="$SOFT/vg-vcf-linker-bin"

# Previously prepared: LINK_DIR/ld -> GNU ld 2.40.
"$LINK_DIR/ld" --version | head -1
grep -F 'Failed to initialize the VCF header' "$VG_BUILD/src/deconstructor.cpp"

# Use pkg-config; do not truncate protobuf's Abseil dependencies.
export PKG_CONFIG_PATH="$BIO/lib/pkgconfig:$BIO/share/pkgconfig"
PROTO_LIBS=$(pkg-config --libs --static protobuf jansson) || exit 1
echo "$PROTO_LIBS" | grep -q -- '-labsl_' || exit 1

# Re-link only after source/object has been built with the intended patch.
make -C "$VG_BUILD" -j 8 \
    CXX="$CXX -B$LINK_DIR/" \
    LDFLAGS="-L$BIO/lib" \
    LD_STATIC_LIB_FLAGS="-lvgio -lhts -ldeflate -lz -lbz2 -Wl,-Bdynamic -llzma $PROTO_LIBS" \
    bin/vg > "$FIX_OUT/build.relink.log" 2>&1
rc=$?
echo "LINK_EXIT_CODE=$rc"
```

这里的 `-Wl,-Bdynamic` 很重要：对于上述强制静态链接组，从 `liblzma` 起改为动态依赖。其他源码版本的 Makefile 可能调整了变量，**不能无检查地照搬**。`LINK_EXIT_CODE=0` 只证明链接成功，还需通过实际 `vg version` 和 VCF 小图测试。库依赖变化后需要重新 `ldd`，并注意 B 上是否有对应的动态库。

对于**从头编译**的 vg，历史上使用过 `make -j 16 START_STATIC= END_STATIC= bin/vg` 处理静态库缺失，但它并不能保证所有旧 `.o` 的编译选项一致；应另行检查当前 commit 的 Makefile 和所有构建依赖。对 R2 则使用 `upgrade_r2.sh`，不应把这两类构建混为一谈。

### A.3 R2 固定版本和离线 jemalloc

```bash
SOFT=/share/home/zhanglab/user/chenquanyu/softwares
SRC="$SOFT/vg-join-candidate-r2"
OLD="$SOFT/cactus-join-candidate-r1"
PREFIX="$SOFT/cactus-join-candidate-r2"
JEM_LOCAL="$SOFT/jemalloc-r2"
CFG="$SOFT/git-r2-offline.conf"

git config -f "$CFG" "url.file://$JEM_LOCAL.insteadOf" \
    "https://github.com/jemalloc/jemalloc.git"
git config -f "$CFG" protocol.file.allow always

GIT_CONFIG_GLOBAL="$CFG" \
    git ls-remote https://github.com/jemalloc/jemalloc.git HEAD

# Only for a NEW output prefix; do not overwrite the existing successful/partial R2.
# GIT_CONFIG_GLOBAL="$CFG" bash "$SRC/benchmarks/cactus_join/upgrade_r2.sh" \
#     "$OLD" "$PREFIX" 8
```

`upgrade_r2.sh` 复用 R1 的 vg/GFAffix，编译 jemalloc、两套 libbdsg backend 和 clip-vg，并运行小图验证。固定源 commit：`hal2vg 80112aa3de68be015093bb88c784f7911a74b09d`、`jemalloc 54eaed1d8b56b1aa528be3bdd1877e59c56fa90c`、`libbdsg a2e873b80b10b38b90f1f82bee3044116b6276fc`。验收看退出码及 `PASS r2 upgrade and small graph comparisons`；中途失败不代表已完成 R2。

## 4. Cluster B：这是运行时部署，不是复用 A 的编译环境

Cluster B 的基础激活脚本：

`/public/home/u12518101/softwares/cactus-master-7f34bb7/activate_cactus_7f34bb7_new_cluster.sh`

它设置 `cactus_env`、`bioinfo` 的 Python/可执行文件并执行自检，**但会覆盖原有的 `LD_LIBRARY_PATH`**：

```bash
export LD_LIBRARY_PATH="$RT:/lib64:/usr/lib64:$ROOT/lib"
```

所以在它**之前** export 新 vg 的运行库路径不会生效；必须在 `source ./cactus.config.sh` 中调用该激活脚本**之后**设置，才能使实际 `run.py`/Toil 工作流继承。

### B.1 已实测通过的 B 动态库组合

2026-11-03 的 candidate-only VCF 小图测试使用：

```text
/public/home/u12518101/softwares/vg-vcf-header-incoming/runtime-lib/
  libboost_program_options.so.1.82.0  (实际库文件，约 420 KiB)
  libfreetype.so.6  -> /public/home/u12518101/miniforge3/envs/bioinfo/lib/libfreetype.so.6
  libgomp.so.1      -> /public/home/u12518101/miniforge3/lib/libgomp.so.1
  libstdc++.so.6    -> /public/home/u12518101/miniforge3/envs/bioinfo/lib/libstdc++.so.6
  libz.so.1         -> /public/home/u12518101/miniforge3/envs/bioinfo/lib/libz.so.1
```

- `bioinfo/lib/libgomp.so.1 -> libomp.so` 是 LLVM OpenMP，**没有**这次需要的 `OMP_5.0`；系统 GCC 4.8.5 的 `/lib64/libgomp.so.1` 同样没有 `OMP_5.0`。真正通过 `readelf --version-info` 的 GNU libgomp 在 **Miniforge base** `/public/home/u12518101/miniforge3/lib/libgomp.so.1`。
- `bioinfo/lib/libstdc++.so.6` 提供 `GLIBCXX_3.4.30`；不要使用旧系统 `/lib64/libstdc++.so.6`。
- 系统 `libz.so.1` 不提供 `ZLIB_1.2.9`；`bioinfo` 中的 zlib 可以使用。
- Cairo 的 `FT_Get_Color_Glyph_Layer` 由 `bioinfo` 的 FreeType 提供。
- 候选需要**准确的** `libboost_program_options.so.1.82.0`，不能把其他 Boost 版本冒名软链接。
- 系统 `/lib64/libjansson.so.4: no version information available` 是当时仍存在的**警告**；候选在此警告下通过 `vg version` 和 VCF 小图测试。
- 只在命令前设置 `LD_LIBRARY_PATH` 时能运行、直接执行 `vg.fixed version` 却报 `libncurses.so.6`：这是**没有继承运行环境**，并非编译再次失败。

已在 B 实际通过的测试形式：

```bash
SOFT=/public/home/u12518101/softwares
PREFIX="$SOFT/cactus-join-candidate-r2"
INCOMING="$SOFT/vg-vcf-header-incoming"
BIO=/public/home/u12518101/miniforge3/envs/bioinfo
RUNTIME="$INCOMING/runtime-lib"

export VG_TEST_LD_LIBRARY_PATH="$RUNTIME:/lib64:/usr/lib64:$BIO/lib"
LD_LIBRARY_PATH="$PREFIX/candidate/lib:$VG_TEST_LD_LIBRARY_PATH" \
    "$PREFIX/candidate/bin/vg.fixed" version

LD_LIBRARY_PATH="$VG_TEST_LD_LIBRARY_PATH" \
    python3 "$INCOMING/test_deconstruct.py" \
    "$PREFIX/candidate/bin/vg.fixed" \
    "$PREFIX/candidate/bin/vg.fixed"
```

测试返回 `TEST_EXIT_CODE=0`，输出 `PASS standard/gref VCF: complete headers/records, chr21:2 C>G, GT=1|0, control/candidate x 1/4 threads`。但因为**两次传入的是相同的 fixed candidate**，这**不是**真实 control/candidate 差分测试。原 control 的 VCF 初始化 bug 仍待单独修复。

### B.2 建议持久化的运行库与配置（步骤未在聊天日志中最终确认）

临时 `incoming` 目录不应成为长期 Slurm 作业依赖。把上面的 `runtime-lib` 保存到 `$SOFT/cactus-join-vcf-runtime`（保持 B 上的软链接指向 B 的真实库），并**先复跑同一个小图测试**。之后在 chr21 的 `cactus.config.sh` 现有 Cactus source 行后面加入：

```bash
source /public/home/u12518101/softwares/cactus-master-7f34bb7/activate_cactus_7f34bb7_new_cluster.sh --check || exit 1

BIO=/public/home/u12518101/miniforge3/envs/bioinfo
RUNTIME=/public/home/u12518101/softwares/cactus-join-vcf-runtime
export LD_LIBRARY_PATH="$RUNTIME:$LD_LIBRARY_PATH:$BIO/lib"
```

这样既保留原 Cactus 动态库顺序，也把经过验证的五个库放在最前；`bioinfo/lib` 放最后以提供 `libncurses.so.6` 等。**不要修改全局 Cactus 激活脚本**。当前 chr21 的 `TOIL_ARGS` 已有 `--setEnv PATH` 和 `--setEnv LD_LIBRARY_PATH`；在未检查实际脚本时不要再重复给 R2 `run.py` 添加相同参数。

在原 chr21 目录执行持久化后的启动检查：

```bash
SOFT=/public/home/u12518101/softwares
PREFIX="$SOFT/cactus-join-candidate-r2"
(
    source ./cactus.config.sh
    LD_LIBRARY_PATH="$PREFIX/candidate/lib:$LD_LIBRARY_PATH" \
        "$PREFIX/candidate/bin/vg" version
)
```

**只有这条命令成功退出，再从原 jobStore 续跑。** 新二进制替换前，先检查 SHA-256、`cmp`、作业已停止，并备份原 `candidate/bin/vg`；control、`lib/`、`override/` 保持原样。

## 5. R2 restart 与验证边界

从**原始 chr21 目录**、已分配的 Slurm 作业内执行；当前实际 `run.json` 已通过身份检查：`cwd` 是 `/public/home/u12518101/project/APGp2/00.data/00.assembly/06.graph/chr21`，原始 `script` 是 `04.join.nohal.sh`，`js.join` 存在。不要修改 `04.join.nohal.sh` 的内容或输入。

```bash
SOFT=/public/home/u12518101/softwares
SRC="$SOFT/vg-join-candidate-r2"
PREFIX="$SOFT/cactus-join-candidate-r2"
WORK="$PWD/join_bench_r2"

python3 "$SRC/benchmarks/cactus_join/run.py" \
    candidate "$PREFIX" "$WORK/candidate" "$PWD/04.join.nohal.sh" \
    --restart
```

`run.py` 检查 `identity`、要求非空 Slurm CPU/内存环境变量，并归档先前尝试到 `previous_attempts/`。阶段缓存可复用的前提是输入/配置/二进制身份仍符合缓存要求；无法保证所有旧工作都不用重算。CPU/wall time 统计应计入此前尝试。

两组成功后按 `RECOVERY_R2.md` 进行完整 `verify.py`；要求 `verify/report.json` 的 `pass == true`。**截至本记录：只有 B 的 candidate-only VCF 小图功能检查通过，不声称 chr21 完整续跑已成功，也不声称真实 control 与 candidate 的最终输出相等。**

## 6. 下次遇到报错时的最小定位顺序

1. 源码：`git rev-parse HEAD`、`git submodule status --recursive`、可执行权限；WSL 打包而不是 Windows 文件树打包。
2. 编译：`command -v`、`$CC --version`、`$CXX --version`、`pkg-config --libs --static protobuf jansson`，先验证简单 C++20 编译/链接。
3. 链接：从 `build.*.log` 的**第一条实质性错误**判断是 `ld` 压缩调试信息、`-Bstatic` 缺 `.a`，还是 Protobuf/Abseil 漏传递依赖。不要根据最后一个 `collect2` 猜原因。
4. 运行：`ldd` 看 `not found`/version mismatch，`vg version` 是比 `ldd` 更强的启动检查；必要时用五项私有库构建 B 的最小运行时目录。
5. Cactus/Toil：先 `source cactus.config.sh` 后检查新 vg，再检查 Toil worker 是否继承 `LD_LIBRARY_PATH`，最后运行 VCF 小图/真实 chr21 verify。**不要因一次小图 PASS 宣称完整工作流 PASS。**

相关文档：[README.md](README.md)、[RECOVERY_R2.md](RECOVERY_R2.md)、[VCF_HEADER_FIX.md](VCF_HEADER_FIX.md)。

## 7. R3（2026-11-04 至 11-05）构建与 Cluster B 部署补记

本节在 2026-11-03 的 R1/R2 历史记录上追加，不覆盖前述成功记录。R3 benchmark 脚本固定在 yeeus/vg commit **44566df4f7d295fa40385227ad35cd0616e4492e**；新 control 源码为 **f2ed0bbd4f7d1e7f8c8f4df4a84018f388194d51**，并应用 deconstruct-header 修复。R3 candidate vg 沿用既有构建，主要重编 candidate libbdsg/clip-vg 并更新 Python override。**切勿把 R2 candidate 在 Cluster B 修复成功等同于 Cluster A 的 R2 candidate 也已修复。**

### 7.1 Cluster A：这次实际遇到的失败及处理边界

| 失败位置 / 日志特征 | 本次得到的教训 |
| --- | --- |
| 首次全量 control 构建：CMake 报 CMAKE_CXX_COMPILER 不是存在的可执行文件 | **不要把带空格和 -B 参数的字符串设为全局 CXX**：CMake 会把整个字符串当成编译器路径。嵌套构建保持 CC/CXX 为 GCC 12.2 的真实绝对路径；仅在明确的最终 vg 链接步骤使用带 -B 的 CXX 命令。 |
| SSW：fatal error: zlib.h: No such file or directory | SSW 的内部 Makefile 未必继承上层 CPPFLAGS；应检查实际编译行，必要时用 CPATH 指向 bioinfo/include。 |
| DYNAMIC：Assembler messages: no such instruction: vpopcntq | 其 Release 编译命令包含 -march=native，使 GCC 生成了汇编器不认识的 AVX-512 指令。曾针对 DYNAMIC 的 CMakeLists.txt 移除该选项，并单独检查失败目标；也可降低跨集群 CPU 指令集要求。**汇编器不识别不等于 CPU 不支持；A 机器能编译也不代表 B 机器能运行。** |
| vcflib/WFA2-lib：Could NOT find OpenMP_C，缺 OpenMP_pthread_LIBRARY、OpenMP::OpenMP_C | 属于 CMake 的 OpenMP 依赖检测失败，不是 vcflib 算法错误。GCC 的 -print-file-name=libpthread.a 在 A 只返回裸文件名 libpthread.a，**不能把裸文件名当成已找到的绝对路径**。需检查真实存在的 pthread 库并验证 CMake 配置；用户随后确认 vcflib 已编译通过，但本记录没有最终所用 pthread 路径的独立日志，不能将某个路径标为通用答案。 |
| vcflib 通过后最终 vg 链接失败：cannot find -llzma、-lprotobuf、-labsl_*、-lpthread、-ljansson | 这是原链接规则中 -Bstatic 与环境中动态库之间的冲突，以及手动覆盖链接变量时遗漏依赖。**不要因为依赖目标已构建成功就把最终链接参数简化。** |
| vg 链接成功但启动失败：GLIBCXX_3.4.31 / GLIBCXX_3.4.32 not found | A 的 Boost program_options 1.90.0 需要较新的 libstdc++ 符号，而运行时先加载了 GCC 12.2 自带的旧 libstdc++。用 control 私有 runtime-lib 优先加载已核验的 bioinfo/lib/libstdc++.so.6；不必重新编译 vg。 |
| control 的 vg version 成功，但 Python VCF 测试仍失败 | 命令前缀 LD_LIBRARY_PATH=... 只作用于**该命令**；随后单独运行的 Python 子进程不会自动继承。运行 test_deconstruct.py 前需 export LD_LIBRARY_PATH，或将环境显式附加在 python3 命令前。 |
| upgrade_r3.sh 运行后，candidate 的 vg deconstruct 退出 139 | 从 Cluster A 的 R2 前缀复制进 R3 的 candidate vg 仍有旧 VCF-header 初始化缺陷。升级脚本已构建 libbdsg/clip-vg、生成 override，却在 VCF 回归检查时停止。**不要因部分工具已生成就宣布 R3 升级成功。** |

这次成功的 control 最终重链接命令形式如下（**仅用于依赖已完成编译之后的 bin/vg 链接**；不能把带 -B 的 CXX 传递给依赖的 CMake 构建）：

~~~bash
SOFT=/share/home/zhanglab/user/chenquanyu/softwares
BASE="$SOFT/vg-control-f2ed0bbd4-source"
FIXED="$SOFT/vg-control-f2ed0bbd4-fixed"
BIO="$HOME/mambaforge/envs/bioinfo"
LINK_DIR="$SOFT/vg-vcf-linker-bin"
CXX=/share/software/gcc/12.2/bin/g++
export PKG_CONFIG_PATH="$BIO/lib/pkgconfig:$BIO/share/pkgconfig"
PROTO_LIBS=$(pkg-config --libs --static protobuf jansson) || exit 1

make -C "$BASE" -j 8 CXX="$CXX -B$LINK_DIR/" LDFLAGS="-L$BIO/lib" LD_STATIC_LIB_FLAGS="-lvgio -lhts -ldeflate -lz -lbz2 -Wl,-Bdynamic -llzma $PROTO_LIBS" bin/vg > "$FIXED/build.relink.log" 2>&1
rc=$?
echo "LINK_EXIT_CODE=$rc"
~~~

**已观察到** LINK_EXIT_CODE=0；单独用私有 runtime-lib 启动 control vg 成功；在将 LD_LIBRARY_PATH 传给 Python 后，control-only test_deconstruct.py 也返回 CONTROL_TEST_EXIT_CODE=0，并输出标准/gref VCF PASS。系统 Jansson 的 “no version information available” 此时仍有警告，**不是这一轮的致命错误**。成功链接、成功启动、VCF 功能测试是三个不同的验证层次。

当升级已经创建 R3 输出目录时，不要简单重跑要求“目标不存在”的升级脚本，也不要习惯性 rm -rf 完整 R3（会丢失已构建组件和失败现场）。本次 upgrade_r3.sh 失败后应保留目录，先验证旧修复版 candidate，再备份和替换 **R3/candidate/bin/vg**，随后分别重跑真正的 control/candidate test_deconstruct.py 和 test_join.py --sequential。确保两项均退出 0，且检查其 PASS 日志；相同 vg 路径传两次只能证明该单个二进制可用，**不是差分测试**。再次从 Cluster A 的 R2 生成 R3 时，需要先同步 A 的 candidate 修复，避免重新引入 SIGSEGV。构建溯源还应记录对 DYNAMIC 编译选项及 vcflib 配置所做的本地更改；source.commit 的一行不涵盖这些额外改动。

### 7.2 Cluster A → B：部署内容与动态库

按独立 R3 前缀传输，**不要覆盖 R2 或旧 jobStore**。交付物至少包括：R3/control 和 R3/candidate 各自的 bin、lib、override；R3/source.commit；以及 R3 benchmarks/cactus_join 和 benchmarks/cactus_unchop（后者含 monitor.py）。不需要携带完整 R3 构建源码和中间对象。对 tar 包及跨机传输使用 SHA-256 核对。

新 control 在 A 依赖 Boost program_options **1.90.0** 和能够提供 **GLIBCXX_3.4.32** 的 libstdc++.so.6；应将经过核对的**实际库文件**随 control 私有 lib 一起交付，避免把指向 A 目录的绝对路径软链接传给 B。B 原有的 candidate/R2 runtime-lib 使用 Boost **1.82.0**，不能将不同 Boost SONAME 冒名软链接。各工具需优先加载各自前缀的 lib，再按实际 ldd 结果处理其余依赖。

B 的 Cactus 激活脚本会重设 LD_LIBRARY_PATH；所以应在 **source ./cactus.config.sh** 激活 Cactus 之后追加项目专用 runtime-lib 路径，并确认 Toil worker 继承。不要修改系统库或全局 Cactus 激活脚本。

### 7.3 Cluster B：不要以 clip-vg -h 的退出码判断构建失败

2026-11-05 在 B 的实际日志中，Cactus 自检全部通过，R3 **control vg version** 正常打印 f2ed0bbd4；紧接着 clip-vg -h 显示 usage，整个包含 set -e 的子 Shell 就在进入 candidate 之前退出。**最可能原因**是 clip-vg 将帮助信息写到 stderr 且以非零状态退出；原日志未直接打印该命令的退出码，因此不可把这一推断写成已测得的具体返回值。重定向 > /dev/null 只隐藏 stdout，不隐藏 stderr。打印帮助信息本身也不等价于功能测试通过。

在 B 原 chr21 工作目录执行以下更稳妥的启动检查（需已正确设置 SOFT、PREFIX）：

~~~bash
(
    set -e
    source ./cactus.config.sh
    for mode in control candidate; do
        LIBS="$PREFIX/$mode/lib:$LD_LIBRARY_PATH"
        for tool in vg clip-vg; do
            LD_LIBRARY_PATH="$LIBS" ldd "$PREFIX/$mode/bin/$tool" > "$SOFT/r3.$mode.$tool.ldd.log" 2>&1
            if grep -E 'not found|version .*not found' "$SOFT/r3.$mode.$tool.ldd.log"; then
                echo "FAIL: $mode/$tool dependencies"
                exit 1
            fi
        done
        LD_LIBRARY_PATH="$LIBS" "$PREFIX/$mode/bin/vg" version
        if LD_LIBRARY_PATH="$LIBS" "$PREFIX/$mode/bin/clip-vg" -h > "$SOFT/r3.$mode.clip_help.log" 2>&1; then
            :
        else
            grep -Fq 'Chop out path intervals from a vg graph' "$SOFT/r3.$mode.clip_help.log" || {
                cat "$SOFT/r3.$mode.clip_help.log"
                exit 1
            }
        fi
        echo "PASS: $mode startup checks"
    done
)
~~~

以上检查仅排除显著的动态库问题并确认能打印版本/帮助；**必须**再运行两套不同 vg 的 test_deconstruct.py，以及真实调用 clip-vg、GFAffix 的 test_join.py --sequential，且均要求退出码为 0。只有完成这些检查才启动独立的 R3 chr21 control/candidate benchmark（均使用原始 04.join.nohal.sh、相同资源和新 jobStore），最后执行 verify.py 并检查报告中的 status=complete、pass=true。

**截至本次已提供的 B 日志**：只确认 control vg 能启动及 clip-vg 帮助内容已显示；candidate 的对应启动检查、B 上的两项小图测试、完整 chr21 及最终 verify **仍无通过证据**。后续取得日志后再更新状态，不从升级完成或启动自检推断完整 benchmark 成功。
