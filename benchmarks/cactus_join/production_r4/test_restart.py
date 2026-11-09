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

from toil.common import Toil
from toil.job import Job
from toil.leader import FailedJobsException
from launch import promote_pending, resource_render, resources

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from checkpoint import JoinStages


def ancestor(job, root):
    counter = Path(root) / 'ancestor.count'
    counter.write_text(str(int(counter.read_text()) + 1) if counter.exists() else '1')
    return 'promised-input'


def probe(job, root, index):
    guard = Path(root) / 'active'
    descriptor = os.open(guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        time.sleep(0.2)
        (Path(root) / f'child.{index}').write_text('done')
    finally:
        os.close(descriptor)
        guard.unlink()


def fail_then_resume(job, root, promised):
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
    # A future child can retain an explicit old memory argument. maxJobs=1
    # still prevents concurrent large commands; the two probes must not overlap.
    for index in range(2):
        job.addChildJobFn(probe, str(root), index, cores=1, memory='32Mi', disk='32Mi')


def main():
    os.environ['PATH'] = str(Path(sys.executable).parent) + ':' + os.environ['PATH']
    with tempfile.TemporaryDirectory(prefix='r4-restart-') as directory:
        root = Path(directory)
        os.environ['CACTUS_JOIN_STAGE_CACHE'] = str(root / 'stage_cache')
        os.environ['CACTUS_JOIN_STAGE_TAG'] = 'frozen-r4-test'
        options = Job.Runner.getDefaultOptions(str(root / 'js.join'))
        options.maxCores = 4
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
        first.addChildJobFn(fail_then_resume, str(root), first.rv(), cores=2, memory='64Mi', disk='32Mi')
        try:
            with Toil(options) as toil:
                toil.start(first)
        except FailedJobsException:
            pass
        else:
            raise AssertionError('The first workflow must fail')
        store = Toil.resumeJobStore(str(root / 'js.join'))
        settings = resources(None, None, None, 8, 2000 * 1024, store.config)
        assert settings[1:] == (1900 * 2**30, 4, 1)
        try:
            resources(None, 8, None, 8, 2000 * 1024, store.config)
        except ValueError:
            pass
        else:
            raise AssertionError('Restart must not silently change saved thread counts')
        pending = [j for j in store.jobs() if j.has_body()]
        original_bodies = {str(j.jobStoreID): j.get_body() for j in pending}
        promote_pending(root / 'js.join', 512 * 2**20, root)
        promote_pending(root / 'js.join', 512 * 2**20, root)
        store = Toil.resumeJobStore(str(root / 'js.join'))
        for j in store.jobs():
            if j.has_body():
                assert j.memory == 512 * 2**20
                assert j.get_body() == original_bodies[str(j.jobStoreID)]
        options.restart = True
        options.maxMemory = 512 * 2**20
        with Toil(options) as toil:
            toil.restart()
        assert (root / 'ancestor.count').read_text() == '1'
        assert (root / 'command.count').read_text() == '1'
        assert (root / 'resumed.memory').read_text() == str(512 * 2**20)
        assert all((root / f'child.{i}').exists() for i in range(2))
        assert list((root / 'restart_resources').glob('*/*.pickle'))
        print('PASS real Toil restart: memory raised, cores unchanged, promises preserved, ancestor/cache reused, child concurrency limited')
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
        print('PASS frozen run.py rendering: only resource flags differ; original script preserved')


if __name__ == '__main__':
    main()
