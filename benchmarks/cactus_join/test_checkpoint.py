#!/usr/bin/env python3
"""Run real subprocesses through the checkpoint helper, including a failed stage."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from checkpoint import JoinStages


def call(parameters, outfile, returnStdErr):
    with open(outfile, 'wb') as stream:
        result = subprocess.run(parameters, stdout=stream, stderr=subprocess.PIPE)
    result.check_returncode()
    return result.stderr.decode()


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        os.environ['CACTUS_JOIN_STAGE_CACHE'] = str(root/'saved')
        os.environ['CACTUS_JOIN_STAGE_TAG'] = 'test-tools'
        count, allow = root/'count', root/'allow'
        first = (f"from pathlib import Path; p=Path({str(count)!r}); "
                 "p.write_text(p.read_text()+'1' if p.exists() else '1'); "
                 "import sys; sys.stdout.write('ACGT'); sys.stderr.write('stage-one')")
        second = (f"from pathlib import Path; import sys; assert Path({str(allow)!r}).exists(); "
                  "sys.stdout.write(Path(sys.argv[1]).read_text()+'A'); sys.stderr.write('stage-two')")
        commands = [[sys.executable, '-c', first], [sys.executable, '-c', second, '-']]
        work = root/'work'
        work.mkdir()
        cache = JoinStages(call, work, dict(input_id='one'))
        try:
            cache.pipeline('graph', commands, str(work/'out.vg'), returnStdErr=True)
        except subprocess.CalledProcessError:
            pass
        else:
            raise AssertionError('Second subprocess must fail before allow exists')
        assert count.read_text() == '1'
        assert not (cache.directory/'graph-1.json').exists()
        # Mimic Toil deleting its worker directory after failure.
        shutil.rmtree(work)
        work = root/'new-worker'
        work.mkdir()
        allow.touch()
        cache = JoinStages(call, work, dict(input_id='one'))
        stderr = cache.pipeline('graph', commands, str(work/'out.vg'), returnStdErr=True)
        assert (work/'out.vg').read_text() == 'ACGTA'
        assert count.read_text() == '1', 'Completed stage must be restored, not run again'
        assert stderr == 'stage-one\nstage-two'
        cache.pipeline('graph', commands, str(work/'out.vg'))
        assert count.read_text() == '1'
        saved = cache.directory/'graph-0.stage0'
        saved.write_text('truncated')
        cache.pipeline('graph', commands, str(work/'out.vg'))
        assert count.read_text() == '11', 'Wrong-size cached artifact must be recomputed'
        changed = JoinStages(call, work, dict(input_id='two'))
        changed.pipeline('graph', commands, str(work/'out.vg'))
        assert count.read_text() == '111', 'A different input cannot reuse this cache'
    print('PASS sequential execution, failure, temp deletion, resume, stderr, size and input identity')


if __name__ == '__main__':
    main()
