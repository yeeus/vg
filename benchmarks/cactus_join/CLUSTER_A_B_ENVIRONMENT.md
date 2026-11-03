
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
