#!/usr/bin/env python3
"""Move a real Toil jobStore: links, unresolved promises and future resources."""
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap

from toil.common import Toil
from toil.job import Job, JobFunctionWrappingJob, Promise
from toil.leader import FailedJobsException
from migrate_join import prepare_store


def options_for(root, restart=False):
    options = Job.Runner.getDefaultOptions(str(root / 'js.join'))
    options.workDir = str(root / 'toil_work')
    (root / 'toil_work').mkdir(exist_ok=True)
    options.maxCores = 4 if restart else 1
    options.maxMemory = (256 if restart else 512) * 2**20
    options.defaultMemory = options.defaultDisk = 32 * 2**20
    options.defaultCores = 1
    options.max_jobs = 1
    options.disableChaining = True
    options.clean = 'never'
    options.retryCount = 0
    options.logLevel = 'ERROR'
    options.caching = False
    options.restart = restart
    return options


def main():
    os.environ['PATH'] = str(Path(sys.executable).parent) + ':' + os.environ['PATH']
    if len(sys.argv) > 1 and sys.argv[1] == '--resume':
        assert Promise._resolve.__func__.__name__ == '_resolve_relocated'
        assert JobFunctionWrappingJob.run.__name__ == '_run_migrated_join'
        with Toil(options_for(Path(sys.argv[2]), True)) as toil:
            toil.restart()
        return
    with tempfile.TemporaryDirectory(prefix='r4-migration-test-') as directory:
        root = Path(directory)
        old, new = root / 'A/chr2', root / 'B/chr2'
        (old / 'code').mkdir(parents=True)
        (old / 'align').mkdir()
        (old / 'align/chr2.vg').write_text('tiny input')
        fixture = textwrap.dedent('''\
            from pathlib import Path
            def merge_hal(job, root):
                counter = Path(root) / 'merge.count'
                counter.write_text(str(int(counter.read_text()) + 1) if counter.exists() else '1')
                return 'HAL already merged'
            def clip_vg(job, options, vg_id, merged):
                assert merged == 'HAL already merged'
                downloaded = job.fileStore.readGlobalFile(vg_id)
                assert Path(downloaded).read_text() == 'tiny input'
                failed = Path(options.root) / 'failed.once'
                if not failed.exists():
                    failed.write_text('yes')
                    raise RuntimeError('Intentional failure before unfinished graph processing')
                assert job.cores == 4 and job.memory == 256 * 2**20
                assert options.defaultCores == 1 and options.indexCores == 4
                assert options.maxMemory == options.indexMemory == 256 * 2**20
                (Path(options.root) / 'full.done').write_text('full')
            def make_vcf(job, options, index_mem):
                assert index_mem == 256 * 2**20
                job.addChildJobFn(deconstruct, options, cores=options.indexCores,
                                 memory=index_mem, disk='32Mi')
            def deconstruct(job, options):
                assert job.cores == 4 and job.memory == 256 * 2**20
                assert options.reference == ['GRCh38', 'CHM13v2', 'CN1v1']
                assert options.filter == 132
                (Path(options.root) / 'vcf.done').write_text('vcf')
        ''')
        (old / 'code/migration_fixture.py').write_text(fixture)
        sys.path.insert(0, str(old / 'code'))
        module = importlib.import_module('migration_fixture')
        from argparse import Namespace
        saved_options = Namespace(root=str(old), defaultCores=8, indexCores=8, maxCores=8,
                                  maxMemory=400 * 2**20, indexMemory=400 * 2**20,
                                  reference=['GRCh38', 'CHM13v2', 'CN1v1'], filter=132)
        try:
            with Toil(options_for(old)) as toil:
                vg_id = toil.importFile((old / 'align/chr2.vg').as_uri())
                first = Job.wrapJobFn(module.merge_hal, str(old))
                full = first.addChildJobFn(module.clip_vg, saved_options, vg_id, first.rv(),
                                          cores=1, memory='400Mi', disk='32Mi')
                full.addFollowOnJobFn(module.make_vcf, saved_options, 400 * 2**20,
                                      cores=1, memory='32Mi', disk='32Mi')
                toil.start(first)
        except FailedJobsException:
            pass
        else:
            raise AssertionError('The original workflow must fail')
        new.parent.mkdir()
        shutil.copytree(old, new, symlinks=True)
        old.rename(root / 'A/chr2.archived')
        assert not old.exists()
        store = Toil.resumeJobStore(str(new / 'js.join'))
        bodies = {}
        for job in store.jobs():
            if job.has_body():
                with store.read_file_stream(job.get_body()[0]) as stream:
                    bodies[str(job.jobStoreID)] = stream.read()
        path_hook = Path(__file__).with_name('restart_path_hook') / 'sitecustomize.py'
        config = dict(old_root=str(old), new_root=str(new), runtime=None, path_hook=str(path_hook), cores=4,
                      index_cores=4, memory_bytes=256 * 2**20, join_module='migration_fixture')
        attempt = new / 'migration-attempt'
        attempt.mkdir()
        prepare_store(new / 'js.join', config, attempt)
        store = Toil.resumeJobStore(str(new / 'js.join'))
        for job in store.jobs():
            if job.has_body():
                with store.read_file_stream(job.get_body()[0]) as stream:
                    assert stream.read() == bodies[str(job.jobStoreID)]
        config_path = attempt / 'migration.json'
        config_path.write_text(json.dumps(config))
        env = dict(os.environ, R4_JOIN_MIGRATION_CONFIG=str(config_path),
                   CACTUS_RESTART_OLD_JOBSTORE=str(old / 'js.join'),
                   CACTUS_RESTART_NEW_JOBSTORE=str(new / 'js.join'))
        env['PYTHONPATH'] = str(Path(__file__).with_name('migration_hook')) + ':' + str(new / 'code')
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--resume', str(new)], env=env, check=True)
        assert (new / 'merge.count').read_text() == '1'
        assert (new / 'full.done').read_text() == 'full'
        assert (new / 'vcf.done').read_text() == 'vcf'
        changes = json.loads((attempt / 'metadata_backup/changes.json').read_text())
        assert changes['links']
        assert any(item['old_memory'] > item['new_memory'] for item in changes['jobs'])
        assert (new / 'align/chr2.vg').read_text() == 'tiny input'
        print('PASS real moved Toil workflow: old root removed, imported links repaired, '
              'promises resolved, completed HAL task reused, saved/future CPU and memory updated; bodies unchanged')


if __name__ == '__main__':
    main()
