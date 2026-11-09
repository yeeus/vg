
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from toil.common import Toil
from toil.job import Job
from toil.batchSystems.abstractBatchSystem import InsufficientSystemResources


def make_index(job, marker):
    assert job.cores == 1, job.cores
    Path(marker).write_text(str(job.cores), encoding='utf-8')


def main():
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
    helper = Path(__file__).with_name('fix_single_core_xg.py')
    with tempfile.TemporaryDirectory(prefix='xg-single-core-') as temporary:
        root = Path(temporary)
        jobstore = str(root/'js')
        marker = root/'index.done'
        runtime = root/'candidate'
        module = runtime/'override/cactus/refmap/cactus_graphmap_join.py'
        module.parent.mkdir(parents=True)
        module.write_text('def workflow(options):\n    add_job(\n        cores=max(options.indexCores, 4),\n    )\n',encoding='utf-8')
        options = Job.Runner.getDefaultOptions(jobstore)
        options.maxCores = 1
        options.defaultCores = 1
        options.defaultMemory = 32 * 1024**2
        options.defaultDisk = 32 * 1024**2
        options.maxMemory = 512 * 1024**2
        options.clean = 'never'
        options.retryCount = 0
        options.logLevel = 'ERROR'
        options.caching = False
        first = Job()
        child = first.addChildJobFn(make_index, str(marker), cores=4, memory='32Mi', disk='32Mi')
        child.description.jobName = 'make_xg'
        try:
            with Toil(options) as toil:
                toil.start(first)
        except InsufficientSystemResources as error:
            assert '4.0 cores' in str(error) or '4 cores' in str(error), str(error)
            print('PASS reproduced 4-core XG request under --maxCores 1')
        else:
            raise AssertionError('Oversized job was accepted')
        assert not marker.exists()
        command = [sys.executable, str(helper), str(runtime), jobstore]
        subprocess.run(command,check=True)
        subprocess.run(command,check=True)
        options.restart = True
        with Toil(options) as toil:
            toil.restart()
        assert marker.read_text(encoding='utf-8') in ('1', '1.0')
        assert module.with_name(module.name+'.before-single-core').exists()
        print('PASS repaired saved XG job, idempotent rerun and successful real Toil restart at 1 core')


if __name__ == '__main__':
    main()
