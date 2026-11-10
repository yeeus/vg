#!/usr/bin/env python3
"""Adopt an original join jobStore on cluster B without rewriting job bodies."""
import argparse
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
import uuid

from launch import FROZEN, resources

INDEX_JOBS = {'make_vg_indexes', 'make_xg', 'make_haplo_index', 'deconstruct',
              'odgi_squeeze', 'snarl_stats', 'compute_gref_paths'}


def prepare_store(jobstore, config, attempt):
    """Repair imported links and pending resource descriptions; preserve bodies."""
    from toil.common import Toil
    store = Toil.resumeJobStore(str(jobstore))
    old, new = config['old_root'], config['new_root']
    links = []
    for directory, dirs, files in os.walk(jobstore, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if not path.is_symlink():
                continue
            target = os.readlink(path)
            if target == old or target.startswith(old + '/'):
                replacement = new + target[len(old):]
                if not Path(replacement).exists():
                    raise FileNotFoundError(f'Copy this imported input to B first: {replacement} (link {path})')
                links.append(dict(path=str(path), old=target, new=replacement))
    pending = [job for job in store.jobs() if job.has_body()]
    backup = attempt / 'metadata_backup'
    backup.mkdir()
    with (backup / 'config.pickle').open('xb') as stream:
        pickle.dump(store.config, stream, protocol=pickle.HIGHEST_PROTOCOL)
    records = []
    for number, job in enumerate(pending):
        if job.jobName in INDEX_JOBS:
            cores = config['index_cores']
        elif job.jobName == 'clip_vg':
            cores = min(4, config['cores'])
        elif job.jobName == 'vcf_cat':
            cores = min(6, config['index_cores'])
        else:
            cores = 1
        records.append(dict(id=str(job.jobStoreID), name=job.jobName,
                            old_cores=job.cores, new_cores=cores,
                            old_memory=job.memory, new_memory=config['memory_bytes'], disk=job.disk))
        with (backup / f'job.{number}.pickle').open('xb') as stream:
            pickle.dump(job, stream, protocol=pickle.HIGHEST_PROTOCOL)
    (backup / 'changes.json').write_text(json.dumps(dict(jobs=records, links=links), indent=2) + '\n', encoding='utf-8')
    for link in links:
        path = Path(link['path'])
        temporary = path.with_name(path.name + '.r4-relocate-' + uuid.uuid4().hex)
        os.symlink(link['new'], temporary)
        os.replace(temporary, path)
    for job, record in zip(pending, records):
        job.cores, job.memory = record['new_cores'], record['new_memory']
        body = job.get_body()
        store.update_job(job)
        saved = store.load_job(str(job.jobStoreID))
        if saved.cores != job.cores or saved.memory != job.memory or saved.get_body() != body:
            raise RuntimeError('Saved task resource update failed: ' + str(job.jobStoreID))
        print(f"{job.jobName}: cores {record['old_cores']} -> {job.cores}; "
              f"memory {record['old_memory']/2**30:.1f} -> {job.memory/2**30:.1f} GiB; "
              f'disk unchanged {job.disk/2**40:.2f} TiB', flush=True)
    print(f'Remapped {len(links)} imported links; backed up {len(pending)} pending tasks: {backup}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-root', type=Path, required=True)
    parser.add_argument('--src', type=Path, required=True)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--path-hook', type=Path,
                        default=Path(__file__).with_name('restart_path_hook') / 'sitecustomize.py',
                        help='Existing Promise relocation hook; the bundled copy is unchanged')
    parser.add_argument('--chrom', required=True)
    parser.add_argument('--sv-gfa', required=True)
    parser.add_argument('--reference', nargs='+', required=True)
    parser.add_argument('--cores', type=int)
    parser.add_argument('--memory')
    parser.add_argument('--max-jobs', type=int, default=1)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    old_root = str(args.old_root.absolute())
    if args.chrom != root.name or args.chrom != args.old_root.name:
        raise ValueError('Check CHROM and the old/new chromosome directories')
    if args.reference != ['GRCh38', 'CHM13v2', 'CN1v1']:
        raise ValueError('Keep the original reference order: GRCh38 CHM13v2 CN1v1')
    if old_root == str(root):
        raise ValueError('This entrypoint is for relocated jobStores')
    prefix, src = args.prefix.resolve(), args.src.resolve()
    path_hook = args.path_hook.resolve()
    if not path_hook.is_file():
        raise FileNotFoundError('Existing restart_path_hook is missing: ' + str(path_hook))
    if (prefix / 'source.commit').read_text(encoding='utf-8').strip() != FROZEN:
        raise ValueError('Use the frozen r4 runtime: ' + FROZEN)
    memory, memory_bytes, cores, max_jobs = resources(
        args.memory, args.cores, args.max_jobs,
        int(os.environ['SLURM_CPUS_PER_TASK']), int(os.environ['SLURM_MEM_PER_NODE']))
    from cactus.shared.common import cactus_cpu_count
    from cactus.shared.version import cactus_commit
    if cactus_commit != '7f34bb7a65af5816835ef79b7ae5e2f3c277b305':
        raise ValueError('Use Cactus 7f34bb7 for this jobStore')
    index_cores = min(cores, max(1, cactus_cpu_count() - 1))
    out = root / 'join_migrated_r4'
    attempts = out / 'attempts'
    attempts.mkdir(parents=True, exist_ok=True)
    number = 1
    while (attempts / str(number)).exists():
        number += 1
    attempt = attempts / str(number)
    (attempt / 'logs').mkdir(parents=True)
    (out / 'toil_work').mkdir(exist_ok=True)
    runtime = prefix / 'candidate'
    config = dict(old_root=old_root, new_root=str(root), runtime=str(runtime), path_hook=str(path_hook), cores=cores,
                  index_cores=index_cores, memory_bytes=memory_bytes,
                  join_module='cactus.refmap.cactus_graphmap_join')
    config_path = out / 'migration.json'
    # Keep the original A locator on later attempts too; persisted promises retain it.
    if config_path.exists():
        before = json.loads(config_path.read_text(encoding='utf-8'))
        if before['old_root'] != old_root or before['new_root'] != str(root):
            raise ValueError('Keep the original A root and current B root on every restart')
    (attempt / 'migration.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    env = dict(os.environ)
    env.update(R4_JOIN_MIGRATION_CONFIG=str(attempt / 'migration.json'), OMP_NUM_THREADS=str(cores),
               CACTUS_RESTART_OLD_JOBSTORE=old_root + '/js.join',
               CACTUS_RESTART_NEW_JOBSTORE=str(root / 'js.join'),
               CACTUS_JOIN_STAGE_CACHE=str(out / 'stage_cache'), CACTUS_JOIN_STAGE_TAG='frozen-r4-' + FROZEN,
               VG_BENCH_NUMERIC_IDS='1', VG_BENCH_FAST_SERIALIZE='1', VG_BENCH_XG_MODE='compact',
               VG_BENCH_COMPACT_MEMBERSHIP='1', VG_BENCH_PATH_THREADS=str(min(4, cores)), VG_BENCH_PHASES='1',
               TOIL_HISTORY='False')
    env['PATH'] = str(runtime / 'bin') + ':' + env['PATH']
    env['LD_LIBRARY_PATH'] = str(runtime / 'lib') + ':' + env.get('LD_LIBRARY_PATH', '')
    env['PYTHONPATH'] = str(Path(__file__).with_name('migration_hook')) + ':' + str(runtime / 'override') + ':' + env.get('PYTHONPATH', '')
    check = ('import pathlib; from cactus.refmap import cactus_graphmap_join as j; '
             'from toil.job import JobFunctionWrappingJob, Promise; '
             f'assert pathlib.Path(j.__file__).resolve() == pathlib.Path({str(runtime / "override/cactus/refmap/cactus_graphmap_join.py")!r}).resolve(); '
             'assert JobFunctionWrappingJob.run.__name__ == "_run_migrated_join"; '
             'assert Promise._resolve.__func__.__name__ == "_resolve_relocated"; '
             'print("PASS frozen r4 module, migrated promises and resource argument hook", j.__file__)')
    subprocess.run([sys.executable, '-c', check], env=env, check=True)
    prepare_store(root / 'js.join', config, attempt)
    config_path.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    command = ['cactus-graphmap-join', str(root / 'js.join'), '--restart',
               '--workDir', str(out / 'toil_work'), '--vg', f'./align/{args.chrom}.vg',
               '--hal', f'./align/{args.chrom}.hal', '--sv-gfa', args.sv_gfa,
               '--reference', *args.reference, '--outDir', str(out / 'final'), '--outName', args.chrom,
               '--snarlStats', '--haplo', 'clip', '--filter', '132', '--vcf',
               '--vcfReference', *args.reference, '--gref', '--gfa', 'clip', 'full',
               '--gbz', 'clip', 'full', 'filter', '--xg', 'clip', '--odgi', 'clip',
               '--defaultCores', '1', '--maxCores', str(cores), '--indexCores', str(cores),
               '--maxMemory', memory, '--indexMemory', memory, '--maxJobs', str(max_jobs),
               '--batchSystem', 'single_machine', '--binariesMode', 'local',
               '--retryCount=0', '--stopOnFirstFailure=True', '--clean', 'onSuccess']
    for name in ('PATH', 'LD_LIBRARY_PATH', 'PYTHONPATH', 'OMP_NUM_THREADS', 'TOIL_HISTORY',
                 'CACTUS_RESTART_OLD_JOBSTORE', 'CACTUS_RESTART_NEW_JOBSTORE',
                 'R4_JOIN_MIGRATION_CONFIG', 'CACTUS_JOIN_STAGE_CACHE', 'CACTUS_JOIN_STAGE_TAG',
                 'VG_BENCH_NUMERIC_IDS', 'VG_BENCH_FAST_SERIALIZE', 'VG_BENCH_XG_MODE',
                 'VG_BENCH_COMPACT_MEMBERSHIP', 'VG_BENCH_PATH_THREADS', 'VG_BENCH_PHASES'):
        command += ['--setEnv', name]
    (attempt / 'command.json').write_text(json.dumps(command, indent=2) + '\n', encoding='utf-8')
    (attempt / 'logs/04.join.log').symlink_to('../run.log')
    print(f'Resume original js.join: maxCores={cores}, effective indexCores={index_cores}, memory={memory}; logs: {attempt}', flush=True)
    monitor = src / 'benchmarks/cactus_unchop/monitor.py'
    result = subprocess.run([sys.executable, str(monitor), str(attempt), '--output-name', 'stdout.log',
                             '/usr/bin/time', '-v', '-o', str(attempt / 'logs/04.join.time.log'), *command], env=env)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
