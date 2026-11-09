#!/usr/bin/env python3
"""Resource-only launcher around the frozen r4 workflow and its restart support."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import pickle
import sys
import time

FROZEN = '9952f0fe7cc270d67d28d896096311499d9095f1'


def promote_pending(jobstore, memory, out):
    """Update descriptions only; never unpickle bodies or resolve pending promises."""
    from toil.common import Toil
    store = Toil.resumeJobStore(str(jobstore))
    pending = [job for job in store.jobs() if job.has_body()]
    oversized = [job for job in pending if job.memory > memory]
    if oversized:
        raise RuntimeError('Saved job exceeds the new budget: ' + ', '.join(str(j) for j in oversized))
    changed = [job for job in pending if job.memory < memory]
    if not changed:
        print('No pending job memory needs an increase', flush=True)
        return
    backup = out / 'restart_resources' / str(time.time_ns())
    backup.mkdir(parents=True)
    records = []
    for number, job in enumerate(changed):
        with (backup / f'{number}.pickle').open('xb') as stream:
            pickle.dump(job, stream, protocol=pickle.HIGHEST_PROTOCOL)
        records.append(dict(id=str(job.jobStoreID), name=job.jobName, old_bytes=job.memory,
                            new_bytes=memory, cores=job.cores))
        job.memory = memory
        store.update_job(job)
        if store.load_job(str(job.jobStoreID)).memory != memory:
            raise RuntimeError('Memory update did not persist: ' + str(job.jobStoreID))
    (backup / 'changes.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
    print(f'Raised {len(changed)} pending jobs to {memory / 2**30:.1f} GiB; metadata backup: {backup}', flush=True)


def resources(memory, cores, max_jobs, allocated_cores, allocated_mib, saved=None):
    from toil.lib.conversions import human2bytes
    if cores is None:
        cores = int(saved.maxCores) if saved is not None else allocated_cores
    if saved is not None and cores != int(saved.maxCores):
        raise ValueError(f'Restart keeps the saved thread configuration: use --cores {int(saved.maxCores)}; '
                         'a larger node allocation is allowed')
    if not 1 <= cores <= allocated_cores:
        raise ValueError('--cores must be positive and no greater than the allocated CPUs')
    if memory is None:
        memory = f'{allocated_mib * 95 // 100}Mi'
    memory_bytes = human2bytes(memory)
    if not 0 < memory_bytes < allocated_mib * 2**20:
        raise ValueError('The Toil memory budget must be positive and below the allocated memory')
    if max_jobs is None:
        max_jobs = saved.max_jobs if saved is not None else 1
    if max_jobs < 1:
        raise ValueError('--max-jobs must be positive')
    return memory, memory_bytes, cores, max_jobs


def resource_render(render, memory, cores, max_jobs):
    def wrapped(source, prefix, mode, out, threads):
        source, extra = render(source, prefix, mode, out, cores)
        source = source.replace('export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:?}"',
                                f'export OMP_NUM_THREADS={cores}', 1)
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
    parser.add_argument('--cores', type=int, help='Initial max/index cores; default: Slurm CPUs; restart retains saved cores')
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
        int(os.environ['SLURM_CPUS_PER_TASK']), int(os.environ['SLURM_MEM_PER_NODE']), saved)
    if args.action == 'restart':
        promote_pending(args.out / 'js.join', memory_bytes, args.out)
    spec = importlib.util.spec_from_file_location('frozen_r4_run', args.src / 'benchmarks/cactus_join/run.py')
    frozen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen)
    frozen.render = resource_render(frozen.render, memory, cores, max_jobs)
    sys.argv = [str(spec.origin), 'candidate', str(args.prefix), str(args.out), str(args.script)]
    if args.action == 'restart':
        sys.argv.append('--restart')
    print(f'r4 {FROZEN}: {args.action}, {cores} cores, {memory}, maxJobs={max_jobs}', flush=True)
    frozen.main()


if __name__ == '__main__':
    main()
