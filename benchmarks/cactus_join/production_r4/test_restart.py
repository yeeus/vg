#!/usr/bin/env python3
"""Real Toil failure/restart; preserve completed ancestors, promises and stage cache."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import runpy
from argparse import Namespace

from toil.common import Toil
from toil.job import Job
from toil.leader import FailedJobsException
from launch import parse_allocation, promote_pending, resource_render, resources

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from checkpoint import JoinStages


def ancestor(job, root):
    counter = Path(root) / 'ancestor.count'
    counter.write_text(str(int(counter.read_text()) + 1) if counter.exists() else '1')
    return 'promised-input'


def probe(job, root, index):
    assert job.cores == 4 and job.memory == 512 * 2**20
    guard = Path(root) / 'active'
    descriptor = os.open(guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        time.sleep(0.2)
        (Path(root) / f'child.{index}').write_text('done')
    finally:
        os.close(descriptor)
        guard.unlink()


def deconstruct(job, root, options):
    assert job.cores == options.indexCores == 4
    assert job.memory == options.indexMemory == 512 * 2**20
    (Path(root) / 'index.done').write_text('done')


def fail_then_resume(job, root, promised, options, index_mem):
    assert promised == 'promised-input'
    root = Path(root)
    work = Path(job.fileStore.getLocalTempDir())
    target = work / 'cached.vg'
    def call(parameters, **kwargs):
        result = subprocess.run(parameters, capture_output=True, text=True, check=True)
        return result.stderr
    stages = JoinStages(call, work, dict(input_id=promised, phase='full', cores=job.cores))
    code = ('from pathlib import Path; import sys; p=Path(sys.argv[1]); '
            'p.write_text(str(int(p.read_text())+1) if p.exists() else "1"); '
            'Path(sys.argv[2]).write_text("saved graph")')
    stages.run('01-export', [sys.executable, '-c', code, str(root / 'command.count'), str(target)], target)
    failure = root / 'failed.once'
    if not failure.exists():
        failure.write_text('yes')
        raise RuntimeError('Intentional failure after the successful cached command')
    assert target.read_text() == 'saved graph'
    assert job.memory == 512 * 2**20, job.memory
    assert job.cores == 2, job.cores
    (root / 'resumed.memory').write_text(str(job.memory))
    assert options.defaultCores == 1 and options.maxCores == options.indexCores == 4
    assert index_mem == options.maxMemory == options.indexMemory == 512 * 2**20
    # Newly generated jobs must use the new resources too, with maxJobs=1.
    for index in range(2):
        job.addChildJobFn(probe, str(root), index, cores=options.indexCores, memory=index_mem, disk='32Mi')


def main():
    os.environ['PATH'] = str(Path(sys.executable).parent) + ':' + os.environ['PATH']
    with tempfile.TemporaryDirectory(prefix='r4-restart-') as directory:
        root = Path(directory)
        os.environ['CACTUS_JOIN_STAGE_CACHE'] = str(root / 'stage_cache')
        os.environ['CACTUS_JOIN_STAGE_TAG'] = 'frozen-r4-test'
        options = Job.Runner.getDefaultOptions(str(root / 'js.join'))
        options.maxCores = 2
        options.defaultCores = 1
        options.defaultMemory = 32 * 2**20
        options.defaultDisk = 32 * 2**20
        options.maxMemory = 128 * 2**20
        options.max_jobs = 1
        options.disableChaining = True
        options.clean = 'never'
        options.retryCount = 0
        options.logLevel = 'ERROR'
        options.caching = False
        first = Job.wrapJobFn(ancestor, str(root))
        saved_options = Namespace(defaultCores=1, maxCores=2, indexCores=1,
                                  maxMemory=128 * 2**20, indexMemory=64 * 2**20)
        first.addChildJobFn(fail_then_resume, str(root), first.rv(), saved_options, 64 * 2**20,
                            cores=2, memory='64Mi', disk='32Mi')
        first.addFollowOnJobFn(deconstruct, str(root), saved_options, cores=1, memory='64Mi', disk='32Mi')
        try:
            with Toil(options) as toil:
                toil.start(first)
        except FailedJobsException:
            pass
        else:
            raise AssertionError('The first workflow must fail')
        store = Toil.resumeJobStore(str(root / 'js.join'))
        settings = resources(None, None, None, 8, 2000 * 1024, store.config)
        assert settings[1:] == (1900 * 2**30, 2, 1)
        assert resources(None, 4, None, 8, 2000 * 1024, store.config)[2] == 4
        pending = [j for j in store.jobs() if j.has_body()]
        original_bodies = {str(j.jobStoreID): j.get_body() for j in pending}
        promote_pending(root / 'js.join', 512 * 2**20, root, 4, 4)
        promote_pending(root / 'js.join', 512 * 2**20, root, 4, 4)
        store = Toil.resumeJobStore(str(root / 'js.join'))
        for j in store.jobs():
            if j.has_body():
                assert j.memory == 512 * 2**20
                assert j.get_body() == original_bodies[str(j.jobStoreID)]
                if j.jobName == 'deconstruct':
                    assert j.cores == 4
        config_path = root / 'resource_override.json'
        config_path.write_text(json.dumps(dict(old_root=str(root), new_root=str(root), runtime=None,
                              path_hook=None, cores=4, index_cores=4, memory_bytes=512 * 2**20,
                              join_module='test_restart')))
        hook = Path(__file__).with_name('migration_hook')
        os.environ['R4_JOIN_MIGRATION_CONFIG'] = str(config_path)
        os.environ['PYTHONPATH'] = str(hook) + ':' + str(Path(__file__).resolve().parent)
        runpy.run_path(str(hook / 'sitecustomize.py'))
        options.restart = True
        options.maxMemory = 512 * 2**20
        options.maxCores = 4
        with Toil(options) as toil:
            toil.restart()
        assert (root / 'ancestor.count').read_text() == '1'
        assert (root / 'command.count').read_text() == '1'
        assert (root / 'resumed.memory').read_text() == str(512 * 2**20)
        assert all((root / f'child.{i}').exists() for i in range(2))
        assert (root / 'index.done').exists()
        assert list((root / 'restart_resources').glob('*/*.pickle'))
        print('PASS real Toil restart: maxCores 2 -> 4, saved/future index cores 1 -> 4, memory raised; ancestor/cache reused, bodies/promises preserved')
    spec = importlib.util.spec_from_file_location('r4_run_test', Path(__file__).resolve().parents[1] / 'run.py')
    frozen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen)
    original = ('source ./cactus.config.sh\nmkdir -p ./logs ./toil_work\n'
                'cactus-graphmap-join ./js.join --workDir "$PWD/toil_work" --outDir ./final "$@"\n')
    with tempfile.TemporaryDirectory(prefix='r4-render-') as directory:
        root = Path(directory)
        os.environ['SLURM_CPUS_PER_TASK'] = '56'
        a, flags = resource_render(frozen.render, '480Gi', 56, 1)(original, root, 'candidate', root / 'out', 56)
        b, resumed = resource_render(frozen.render, '1900Gi', 56, 1)(original, root, 'candidate', root / 'out', 56)
        assert a == b and 'export OMP_NUM_THREADS=56' in a
        assert flags[-4:] == ['--maxJobs', '1', '--clean', 'onSuccess']
        assert resumed[resumed.index('--maxMemory') + 1] == '1900Gi'
        assert original.endswith('"$@"\n')
        source, custom = resource_render(frozen.render, '1900Gi', 32, 2)(original, root, 'candidate', root / 'out', 56)
        assert 'export OMP_NUM_THREADS=32' in source
        assert custom[custom.index('--maxCores') + 1] == '32'
        assert custom[custom.index('--indexCores') + 1] == '32'
        assert custom[custom.index('--maxJobs') + 1] == '2'
        assert resources(None, None, None, 56, 500 * 1024)[1:] == (475 * 2**30, 56, 1)
        assert resources('1900Gi', 56, 2, 56, 2048 * 1024)[1:] == (1900 * 2**30, 56, 2)
        record = 'JobId=4280075 NumNodes=1 NumCPUs=96 CPUs/Task=96 TRES=cpu=96,mem=2000G,node=1,billing=96'
        assert parse_allocation(record) == (96, 2048000)
        assert resources('1000G', 90, 1, *parse_allocation(record))[1:] == (1000000000000, 90, 1)
        source, flags = resource_render(frozen.render, '1000G', 90, 1, root / 'resources.json')(
            original, root, 'candidate', root / 'out', 96)
        assert 'export R4_JOIN_MIGRATION_CONFIG=' in source
        assert source.index('migration_hook') < source.index('/candidate/override')
        assert 'R4_JOIN_MIGRATION_CONFIG' in flags
        print('PASS frozen run.py rendering: only resource flags differ; original script preserved')


if __name__ == '__main__':
    main()
