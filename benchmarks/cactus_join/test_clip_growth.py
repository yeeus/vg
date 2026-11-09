#!/usr/bin/env python3
"""Real r3/r4 clipping and multithreaded strict graph-identity checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    old, new = (Path(p).resolve() for p in sys.argv[1:])
    generator = new / 'source/test_clip_growth'
    vg = new / 'candidate/bin/vg'
    env = dict(os.environ, OMP_NUM_THREADS='4', VG_BENCH_PHASES='1',
               VG_BENCH_COMPACT_MEMBERSHIP='1', VG_BENCH_PATH_THREADS='4',
               VG_BENCH_NUMERIC_IDS='1', VG_BENCH_FAST_SERIALIZE='1')
    env['LD_LIBRARY_PATH'] = str(new / 'candidate/lib') + ':' + env.get('LD_LIBRARY_PATH', '')
    with tempfile.TemporaryDirectory(prefix='clip-growth-') as directory:
        root = Path(directory)
        for phase in ('full', 'clip'):
            source = root / (phase + '.vg')
            with source.open('wb') as stream:
                subprocess.run([str(generator), phase, '512', '16'], stdout=stream, env=env, check=True)
            fingerprints = []
            for prefix in (old, new):
                output = root / (phase + '-' + prefix.name + '.vg')
                command = [str(prefix / 'candidate/bin/clip-vg'), str(source),
                           '-f', '-e', 'GRCh38', '-d', '_MINIGRAPH_']
                command += (['-L', '-F'] if phase == 'full' else
                            ['-u', '10000', '-a', '_MINIGRAPH_', '-I', '100000',
                             '-k', '50000', '-T', '-1.0'])
                with output.open('wb') as stream:
                    subprocess.run(command, stdout=stream, env=env, check=True)
                for threads in ('1', '4'):
                    fingerprints.append(json.loads(subprocess.check_output(
                        [str(vg), 'unchop-fingerprint', '--threads', threads, str(output)], env=env)))
            if not all(value == fingerprints[0] for value in fingerprints):
                raise RuntimeError('Graph identity changed: ' + phase)
            if fingerprints[0]['paths'] <= 18:
                raise RuntimeError('Fixture did not exercise replacement paths: ' + phase)
            print('PASS ' + phase + ': exact graph identity, 1/4-thread verification', flush=True)


if __name__ == '__main__':
    main()
