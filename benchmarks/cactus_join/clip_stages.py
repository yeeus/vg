#!/usr/bin/env python3
"""Test only the two changed clip-vg calls, using saved r3 chromosome graphs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def cached(cache, phase, label):
    matches = []
    for marker in sorted(cache.glob('*/' + label + '.json')):
        record = json.loads(marker.read_text(encoding='utf-8'))
        if record['identity']['phase'] == phase:
            files = [p for p in marker.parent.glob(label + '.*')
                     if p.is_file() and p.suffix not in ('.json', '.pending')]
            if len(files) != 1 or files[0].stat().st_size != record['size']:
                raise RuntimeError('Missing or incomplete cache artifact: ' + str(marker))
            matches.append((files[0].resolve(), record))
    if len(matches) != 1:
        raise RuntimeError(f'Need exactly one r3 cache for {phase}/{label}; found {len(matches)}')
    return matches[0]


def environment(prefix):
    env = dict(os.environ, OMP_NUM_THREADS='4', VG_BENCH_NUMERIC_IDS='1',
               VG_BENCH_FAST_SERIALIZE='1', VG_BENCH_PATH_THREADS='4',
               VG_BENCH_COMPACT_MEMBERSHIP='1', VG_BENCH_PHASES='1')
    env['LD_LIBRARY_PATH'] = str(prefix / 'candidate/lib') + ':' + env.get('LD_LIBRARY_PATH', '')
    return env


def run(args):
    cache = args.cache.resolve()
    prefix = args.prefix.resolve()
    expected, record = cached(cache, args.stage, '04-clip-0')
    commands = record['command']
    if len(commands) != 1 or commands[0][0] != 'clip-vg':
        raise RuntimeError('Expected the saved, single clip-vg command')
    if args.stage == 'full':
        source, _ = cached(cache, 'full', '03-unchop-0')
    else:
        source, full_record = cached(cache, 'full', '04-clip-1')
        if full_record['command'][0][:3] != ['vg', 'clip', '--cactus-full']:
            raise RuntimeError('Expected the r3 fused Full output before vg ids -j')
    # Create a fresh stage directory so an interrupted trial cannot be overwritten.
    out = args.out.resolve() / args.stage
    out.mkdir(parents=True, exist_ok=False)
    env = environment(prefix)
    vg = prefix / 'candidate/bin/vg'
    if args.stage == 'clip':
        # vg ids -j rewrites its input. Never hard-link the persistent r3 cache.
        target = out / 'clip.input.vg'
        print('Copy Full graph, then run the original single-chromosome vg ids -j', flush=True)
        subprocess.run(['cp', '--reflink=auto', '--', str(source), str(target)], check=True)
        with (out / 'prepare.log').open('w', encoding='utf-8') as log:
            subprocess.run(['/usr/bin/time', '-v', '-o', str(out / 'prepare.time.log'),
                            str(vg), 'ids', '-j', str(target)], env=env, stdout=log, stderr=log, check=True)
        source = target
    command = [str(prefix / 'candidate/bin/clip-vg'), str(source), *commands[0][2:]]
    identity = dict(stage=args.stage, cache=str(cache), reference_output=str(expected),
                    reference_command=commands[0], command=command, prefix=str(prefix))
    (out / 'command.json').write_text(json.dumps(identity, indent=2) + '\n', encoding='utf-8')
    (out / 'inputs.log').write_text(str(source) + '\n' + str(expected) + '\n', encoding='utf-8')
    monitor = Path(__file__).resolve().parents[1] / 'cactus_unchop/monitor.py'
    print('Run:', ' '.join(command), flush=True)
    subprocess.run([sys.executable, str(monitor), str(out), '/usr/bin/time', '-v',
                    '-o', str(out / 'time.log'), *command], env=env, check=True)
    print('Saved graph, CPU/RSS samples and GNU time:', out, flush=True)


def verify(args):
    out = args.out.resolve()
    prefix = args.prefix.resolve()
    directory = out / 'verify'
    directory.mkdir(exist_ok=False)
    env = environment(prefix)
    env['OMP_NUM_THREADS'] = str(args.threads)
    vg = prefix / 'candidate/bin/vg'
    report = dict(pass_=False, status='incomplete', threads=args.threads, stages=[])
    report_path = directory / 'report.json'

    def save():
        payload = {('pass' if key == 'pass_' else key): value for key, value in report.items()}
        report_path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')

    save()
    for phase in ('full', 'clip'):
        stage = out / phase
        summary = json.loads((stage / 'summary.json').read_text(encoding='utf-8'))
        if summary['exit_code'] != 0:
            raise RuntimeError('Stage did not finish: ' + phase)
        identity = json.loads((stage / 'command.json').read_text(encoding='utf-8'))
        values = []
        # One loaded graph at a time; each traversal/fingerprint uses all threads.
        for label, source in (('r3', identity['reference_output']), ('r4', str(stage / 'result.vg'))):
            output = directory / (phase + '.' + label + '.json')
            with output.open('wb') as stream, (directory / (phase + '.' + label + '.log')).open('wb') as log:
                subprocess.run(['/usr/bin/time', '-v', '-o', str(directory / (phase + '.' + label + '.time.log')),
                                str(vg), 'unchop-fingerprint', '--threads', str(args.threads), source],
                               env=env, stdout=stream, stderr=log, check=True)
            values.append(json.loads(output.read_text(encoding='utf-8')))
        equal = values[0] == values[1]
        report['stages'].append(dict(stage=phase, **{'pass': equal}, resources=summary,
                                     reference=identity['reference_output'], candidate=str(stage / 'result.vg'),
                                     fingerprints=values))
        save()
        print(('PASS ' if equal else 'FAIL ') + phase + ': exact nodes/edges/paths, including IDs and ordered steps', flush=True)
    report['pass_'] = all(item['pass'] for item in report['stages'])
    report['status'] = 'complete'
    save()
    print('Report:', report_path, flush=True)
    if not report['pass_']:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='action', required=True)
    run_parser = subparsers.add_parser('run')
    run_parser.add_argument('--stage', choices=['full', 'clip'], required=True)
    run_parser.add_argument('--cache', type=Path, required=True)
    run_parser.add_argument('--prefix', type=Path, required=True)
    run_parser.add_argument('--out', type=Path, required=True)
    verify_parser = subparsers.add_parser('verify')
    verify_parser.add_argument('--prefix', type=Path, required=True)
    verify_parser.add_argument('--out', type=Path, required=True)
    verify_parser.add_argument('--threads', type=int, default=16)
    args = parser.parse_args()
    if args.action == 'verify' and args.threads < 2:
        parser.error('Verification requires at least two threads')
    if args.action == 'run':
        run(args)
    else:
        verify(args)


if __name__ == '__main__':
    main()
