#!/usr/bin/env python3
"""Resource-only launcher around the frozen r4 workflow and its restart support."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import pickle
import re
import shlex
import subprocess
import sys
import time

FROZEN = '9952f0fe7cc270d67d28d896096311499d9095f1'
INDEX_JOBS = {'make_vg_indexes', 'make_xg', 'make_haplo_index', 'deconstruct',
              'odgi_squeeze', 'snarl_stats', 'compute_gref_paths'}


def parse_allocation(record):
    fields = dict(item.split('=', 1) for item in record.split() if '=' in item)
    if int(fields['NumNodes']) != 1:
        raise ValueError('The single_machine launcher requires a single-node allocation')
    cores = int(fields['NumCPUs'])
    tres = dict(item.split('=', 1) for item in fields.get('AllocTRES', fields.get('TRES', '')).split(',') if '=' in item)
    value, unit = re.fullmatch(r'([0-9.]+)([KMGTPE]?)', tres['mem']).groups()
    memory_mib = int(float(value) * 1024 ** ('KMGTPE'.index(unit) - 1)) if unit else int(value)
    return cores, memory_mib


def allocation():
    """Refresh inherited hints from the actual allocation, without changing Slurm."""
    if os.environ.get('SLURM_JOB_ID'):
        record = subprocess.check_output(['scontrol', 'show', 'job', os.environ['SLURM_JOB_ID'], '-o'], text=True)
        cores, memory_mib = parse_allocation(record)
        os.environ['SLURM_CPUS_PER_TASK'] = str(cores)
        os.environ['SLURM_MEM_PER_NODE'] = str(memory_mib)
        return cores, memory_mib
    return int(os.environ['SLURM_CPUS_PER_TASK']), int(os.environ['SLURM_MEM_PER_NODE'])


def promote_pending(jobstore, memory, out, cores=None, index_cores=None):
    """Update descriptions only; never unpickle bodies or resolve pending promises."""
    from toil.common import Toil
    store = Toil.resumeJobStore(str(jobstore))
    pending = [job for job in store.jobs() if job.has_body()]
    oversized = [job for job in pending if job.memory > memory]
    if oversized:
        raise RuntimeError('Saved job exceeds the new budget: ' + ', '.join(str(j) for j in oversized))
    changed = []
    for job in pending:
        new_cores = job.cores
        if cores is not None:
            if job.jobName in INDEX_JOBS:
                new_cores = index_cores
            elif job.jobName == 'vcf_cat':
                new_cores = min(6, index_cores)
            else:
                new_cores = min(job.cores, cores)
        if job.memory != memory or job.cores != new_cores:
            changed.append((job, new_cores))
    if not changed:
        print('No pending job resources need an update', flush=True)
        return
    backup = out / 'restart_resources' / str(time.time_ns())
    backup.mkdir(parents=True)
    records = []
    for number, (job, new_cores) in enumerate(changed):
        with (backup / f'{number}.pickle').open('xb') as stream:
            pickle.dump(job, stream, protocol=pickle.HIGHEST_PROTOCOL)
        records.append(dict(id=str(job.jobStoreID), name=job.jobName, old_bytes=job.memory,
                            new_bytes=memory, old_cores=job.cores, new_cores=new_cores))
        job.memory, job.cores = memory, new_cores
        store.update_job(job)
        saved = store.load_job(str(job.jobStoreID))
        if saved.memory != memory or saved.cores != new_cores:
            raise RuntimeError('Resource update did not persist: ' + str(job.jobStoreID))
    (backup / 'changes.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
    print(f'Updated {len(changed)} pending jobs; memory {memory / 2**30:.1f} GiB; metadata backup: {backup}', flush=True)


def resources(memory, cores, max_jobs, allocated_cores, allocated_mib, saved=None):
    from toil.lib.conversions import human2bytes
    if cores is None:
        cores = int(saved.maxCores) if saved is not None else allocated_cores
    if not 1 <= cores <= allocated_cores:
        raise ValueError(f'--cores {cores} must be positive and no greater than allocated CPUs ({allocated_cores})')
    if memory is None:
        memory = f'{allocated_mib * 95 // 100}Mi'
    memory_bytes = human2bytes(memory)
    if not 0 < memory_bytes < allocated_mib * 2**20:
        raise ValueError(f'--memory {memory} must be positive and below allocated memory ({allocated_mib / 1024:.1f} GiB)')
    if max_jobs is None:
        max_jobs = saved.max_jobs if saved is not None else 1
    if max_jobs < 1:
        raise ValueError('--max-jobs must be positive')
    return memory, memory_bytes, cores, max_jobs


def resource_render(render, memory, cores, max_jobs, override=None):
    def wrapped(source, prefix, mode, out, threads):
        source, extra = render(source, prefix, mode, out, cores)
        source = source.replace('export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:?}"',
                                f'export OMP_NUM_THREADS={cores}', 1)
        if override is not None:
            source = source.replace('export PYTHONPATH=',
                                    'export R4_JOIN_MIGRATION_CONFIG=' + shlex.quote(str(override)) + '\n'
                                    'export PYTHONPATH=' + shlex.quote(str(Path(__file__).with_name('migration_hook'))) + ':', 1)
            extra += ['--setEnv', 'R4_JOIN_MIGRATION_CONFIG']
        extra += ['--batchSystem', 'single_machine', '--defaultCores', '1',
                  '--maxCores', str(cores), '--indexCores', str(cores),
                  '--maxMemory', memory, '--indexMemory', memory,
                  '--maxJobs', str(max_jobs), '--clean', 'onSuccess']
        return source, extra
    return wrapped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'restart'])
    parser.add_argument('src', type=Path)
    parser.add_argument('prefix', type=Path)
    parser.add_argument('script', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--memory', help='Toil/index budget, e.g. 480Gi or 1900Gi; default: 95%% of Slurm allocation')
    parser.add_argument('--cores', type=int, help='Max/index cores, adjustable on restart; default: Slurm CPUs initially, saved value on restart')
    parser.add_argument('--max-jobs', type=int, help='Concurrent Toil jobs; default: 1 initially, saved value on restart')
    args = parser.parse_args()
    args.src, args.prefix, args.script, args.out = (
        p.resolve() for p in (args.src, args.prefix, args.script, args.out))
    if (args.prefix / 'source.commit').read_text(encoding='utf-8').strip() != FROZEN:
        raise ValueError('Use the frozen r4 build: ' + FROZEN)
    saved = None
    if args.action == 'restart':
        previous = json.loads((args.out / 'run.json').read_text(encoding='utf-8'))
        expected = dict(mode='candidate', cwd=str(Path.cwd()), script=str(args.script),
                        script_text=args.script.read_text(encoding='utf-8'),
                        prefix=str(args.prefix), layout='r2')
        if previous['identity'] != expected:
            raise ValueError('Restart requires the same chromosome directory, original script and frozen runtime')
        if not (args.out / 'js.join').is_dir():
            raise ValueError('No existing join_r4/js.join to restart')
        from toil.common import Toil
        saved = Toil.resumeJobStore(str(args.out / 'js.join')).config
    memory, memory_bytes, cores, max_jobs = resources(
        args.memory, args.cores, args.max_jobs,
        *allocation(), saved)
    override = None
    if args.action == 'restart':
        from cactus.shared.common import cactus_cpu_count
        index_cores = min(cores, max(1, cactus_cpu_count() - 1))
        promote_pending(args.out / 'js.join', memory_bytes, args.out, cores, index_cores)
        override = args.out / 'resource_override.json'
        config = dict(old_root=str(Path.cwd()), new_root=str(Path.cwd()),
                      runtime=str(args.prefix / 'candidate'), path_hook=None,
                      cores=cores, index_cores=index_cores, memory_bytes=memory_bytes,
                      join_module='cactus.refmap.cactus_graphmap_join')
        override.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    spec = importlib.util.spec_from_file_location('frozen_r4_run', args.src / 'benchmarks/cactus_join/run.py')
    frozen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen)
    frozen.render = resource_render(frozen.render, memory, cores, max_jobs, override)
    sys.argv = [str(spec.origin), 'candidate', str(args.prefix), str(args.out), str(args.script)]
    if args.action == 'restart':
        sys.argv.append('--restart')
    print(f'r4 {FROZEN}: {args.action}, {cores} cores, {memory}, maxJobs={max_jobs}', flush=True)
    frozen.main()


if __name__ == '__main__':
    main()
