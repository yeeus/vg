# chr2：原版 join 从 A 迁移到 B，接入冻结 r4

适用于这次已复制的 `chr2/js.join`，不是 `03.align`，也不要求存在 r4 的 `run.json`。算法继续固定为 `9952f0fe7cc270d67d28d896096311499d9095f1`，不重新编译。

A 原目录：`/share/home/project/zhanglab/HumanGenomeArchive/GSA/APGp2/Graph/chr2`。

B 新目录：`/public/home/u12518101/project/APGp2/00.data/00.assembly/06.graph/chr2`。

将更新后的完整 `cactus-r4-run` 文件夹放到 B 的 `/public/home/u12518101/softwares/`。现有冻结 r4 安装、benchmark 脚本继续使用。

路径映射直接复用你已有的 `restart_path_hook/sitecustomize.py`，不修改其内容。包内附相同文件；若 B 的 chr2 目录已保留原 hook，可在下列命令末尾加 `--path-hook "$PWD/restart_path_hook/sitecustomize.py"` 使用原文件。新的组合加载器只负责同时启用它、r4 私有模块和 join 资源更新。

## 在 96 CPU / 2T 作业内运行

先确认 A/B 的旧作业均已停止，保留 A 上原 jobStore 作为恢复副本。B 上保留完整 `js.join` 与已传入的 `align` 文件，`cactus.config.sh` 中设 `CHROM=chr2`，参考仍为 GRCh38、CHM13v2、CN1v1。

```bash
cd /public/home/u12518101/project/APGp2/00.data/00.assembly/06.graph/chr2

bash /public/home/u12518101/softwares/cactus-r4-run/restart_migrated.sh \
    --old-root /share/home/project/zhanglab/HumanGenomeArchive/GSA/APGp2/Graph/chr2 \
    --cores 96 --memory 1900Gi
```

不需要把 `js.join` 改名或搬入 `join_r4/`。本入口直接续跑 B 上的 `./js.join`。

资源可调：`--cores` 是工作流 CPU 上限，`--memory` 是内部 Toil 预算；不指定时采用已分配 CPU 与 95% 内存。任务并发默认 `--max-jobs 1`。Cactus 按自身规则为 leader 留核，因此 96 CPU 分配下索引通常为 95 核；Full 的 unchop 最多 4 线程，Full 融合仍为 `defaultCores=1`。

## 脚本会做什么

- 检查冻结 r4 的安装提交、Cactus 提交，以及 B 上私有 join 模块的实际加载位置。
- 检查 jobStore 内指向 A 的导入符号链接。只有 B 上对应文件存在才改链；不复制大图。缺少文件会先报出具体 B 路径，此时尚未修改任务资源。
- 在备份后更新尚未完成任务的 CPU/内存申请，保留完成任务和任务主体 pickle。新预算可能低于 A 的 3000G 预算；预算本身不代表实际 RSS，2T 是否足够仍由运行结果确定。
- 通过原 hook 及 `CACTUS_RESTART_OLD_JOBSTORE` / `CACTUS_RESTART_NEW_JOBSTORE` 映射 Promise 的 jobStore 地址；在 join 任务真正开始运行时更新其资源参数和 A 项目路径，后续动态创建的 VCF 等子任务也使用新的设置。
- 加载原有 r4 私有模块；不修改共享 Cactus 或冻结的计算代码。图处理选项沿用原命令：三参考、filter=132、clip/full GFA/GBZ、VCF/gref/haplo/XG/ODGI/snarlStats 和 HAL。

A 早期日志表明 HAL 合并已完成，而 Full 在首次 `vg paths -L` 处失败；后来 A 又续跑过，因此本脚本以实际 jobStore 的完成状态为准。已完成的 HAL/SV-GFA 等任务会复用，未完成的 Full 任务从自身起点重试；原版没有持久子步骤缓存，旧 scratch 中的未完成命令不能自动恢复。

原任务的磁盘申请不变。你提供的早期 Full 任务申请过 **18.2 TiB** 磁盘；仍需由当前 workDir 所在文件系统满足 Toil 的磁盘预检。增加内存不能替代磁盘空间。

## 日志和结果

```text
./js.join                                        原迁入的 jobStore
join_migrated_r4/final/                           最终输出
join_migrated_r4/stage_cache/                     从本次开始保存的 r4 子步骤缓存
join_migrated_r4/toil_work/                       B 上 worker 工作目录
join_migrated_r4/attempts/1/logs/04.join.log       第一轮主日志
join_migrated_r4/attempts/1/logs/04.join.time.log  第一轮 GNU time
join_migrated_r4/attempts/1/summary.json           第一轮 CPU/RSS 和退出码
join_migrated_r4/attempts/1/metadata_backup/       修改前的配置、任务描述及链接映射
```

以后再次续跑仍使用同一条 `restart_migrated.sh` 命令，并始终传入最初的 A `--old-root`。可以调整资源参数；新日志按 attempts/2、3…保存，之前的记录和缓存保留。不要改用普通 `restart.sh`，它针对的是由新入口创建的 `join_r4/js.join`。

本地验证使用与你一致提交的 Toil 源码，执行了实际的失败→复制 jobStore→旧路径失效→改链/资源→续跑小流程，检查完成任务未重算、Promise 解析、后续子任务资源和主体 pickle 不变。尚未在 B 的 chr2 大图上运行；这不是一次新的全图/VCF 一致性验证。
