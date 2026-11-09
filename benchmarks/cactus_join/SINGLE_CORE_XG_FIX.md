# r3 的单核 XG 续跑修复

Cactus 7f34bb7 创建 XG 任务时使用 cores=max(options.indexCores, 4)。设置 --maxCores 1 --indexCores 1 会使 Toil 在派发 XG 任务前报 InsufficientSystemResources。r3 沿用了这个上游下限。

本次修复将 XG 的任务核数设为 options.indexCores。已有 jobStore 需要同时更新尚未执行的 make_xg 描述，否则源码修复后仍会申请已保存的 4 核。

## 修复已停止的 candidate

在 B 的原 Cactus 环境、原 chr21 目录下执行。把本提交的 fix_single_core_xg.py 下载到当前目录。下面的 SRC 使用原来的 r3 benchmark 源码目录。

~~~bash
SRC="$HOME/softwares/vg-join-candidate-r3"
RUN="$PWD/join_bench_r3.1_core/candidate"
PREFIX="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["identity"]["prefix"])' "$RUN/run.json")"
SCRIPT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["identity"]["script"])' "$RUN/run.json")"

python3 ./fix_single_core_xg.py "$PREFIX/candidate" "$RUN/js.join"
~~~

脚本先检查保存的预算确为 1 核，并检查所有超预算的未完成任务。随后备份和更新私有 join 模块，将已保存的 make_xg 任务从 4 核改为 1 核。可重复执行。通过标准是 PASS single-core XG repair。

修复后，在具有原内存预算的 Slurm 作业中继续运行。保持首次运行的脚本及单核参数。

~~~bash
python3 "$SRC/benchmarks/cactus_join/run.py" \
    candidate "$PREFIX" "$RUN" "$SCRIPT" --restart
~~~

原有监控脚本会把上一轮日志移入 previous_attempts/，继续记录本轮 CPU、RSS 和汇总。已完成的 Toil 任务从 jobStore 恢复，原先尚未完成的任务可能重新执行。新日志应出现 make_xg 的 cores: 1 以及 vg convert -x … -t 1。

control 的同类单核报错可对对应的 control runtime 和 jobStore 执行该脚本。新建 runtime 使用更新后的 prepare.py 即可生成修复后的覆盖模块。

本地使用 Toil 9.3.0 的真实工作流验证 4 核任务在 1 核预算下被拒绝，并通过本脚本修复后以 1 核续跑成功。完整 chr21 的续跑结果以集群日志为准。
