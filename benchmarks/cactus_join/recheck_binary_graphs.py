#!/usr/bin/env python3
"""Compare the decoded content of GBZ and ODGI files that failed byte checks."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from verify import compare_streams


def sorted_export(command, output, threads, scratch, env):
    # Sort complete records to retain multiplicity and the order within walks.
    # Stream the export into sort so only the sorted files and sort runs use disk.
    with output.open('wb') as target:
        with subprocess.Popen(command, stdout=subprocess.PIPE, env=env) as exporter:
            with exporter.stdout:
                subprocess.run(['sort', f'--parallel={threads}', '-S', '512M', '-T', str(scratch)],
                               stdin=exporter.stdout, stdout=target, env=env, check=True)
            status = exporter.wait()
            if status:
                raise subprocess.CalledProcessError(status, command)
    # Some ODGI builds return success and only a header for unreadable input.
    with output.open('rb') as graph:
        first_record = graph.readline(4096)
        if not first_record or (first_record.startswith(b'H\t') and not graph.read(1)):
            raise ValueError(f'No graph records exported from {command[-1]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path, help='completed verify_original/report.json')
    parser.add_argument('--vg', type=Path, required=True, help='candidate/bin/vg')
    parser.add_argument('--odgi', default='odgi')
    parser.add_argument('--threads', type=int, default=16)
    parser.add_argument('--tmp', type=Path, required=True, help='scratch directory for external sorting')
    parser.add_argument('--output', type=Path, required=True, help='new JSON report')
    args = parser.parse_args()
    previous = json.loads(args.report.read_text(encoding='utf-8'))
    if previous.get('status') != 'complete' or len(previous.get('directories', [])) != 2:
        parser.error('Need a complete verifier report containing two final directories')
    if args.threads < 1:
        parser.error('Use at least one thread')
    names = [row['file'] for row in previous['files']
             if not row['pass'] and row['file'].endswith(('.gbz', '.og'))]
    if not names:
        parser.error('No failed GBZ or ODGI files in this report')
    directories = list(map(Path, previous['directories']))
    vg = args.vg.resolve()
    env = dict(os.environ, LC_ALL='C', OMP_NUM_THREADS=str(args.threads))
    env['LD_LIBRARY_PATH'] = str(vg.parent.parent / 'lib') + ':' + env.get('LD_LIBRARY_PATH', '')
    rows = []
    with args.output.open('x', encoding='utf-8') as report:
        for name in names:
            print(f'Checking {name}', flush=True)
            is_gbz = name.endswith('.gbz')
            row = {'file': name, 'format': 'GBZ' if is_gbz else 'ODGI',
                   'original_byte_check': 'FAIL'}
            try:
                with tempfile.TemporaryDirectory(dir=args.tmp, prefix='binary-graph-') as scratch:
                    scratch = Path(scratch)
                    sorted_gfas = [scratch / 'old.gfa', scratch / 'candidate.gfa']
                    metadata = []
                    for directory, output in zip(directories, sorted_gfas):
                        source = str(directory / name)
                        if is_gbz:
                            command = [str(vg), 'convert', '-f', '--gbwtgraph-algorithm',
                                       '--no-translation', '-t', str(args.threads), source]
                        else:
                            command = [args.odgi, 'view', '-g', '-t', str(args.threads), '-i', source]
                        sorted_export(command, output, args.threads, scratch, env)
                        if is_gbz:
                            metadata.append(sorted(subprocess.check_output(
                                [str(vg), 'gbwt', '-Z', '-M', '--tags', source],
                                env=env, text=True, encoding='utf-8').splitlines()))
                    row['gfa_records_equal'] = compare_streams(*sorted_gfas)
                    if is_gbz:
                        row['gbwt_metadata_and_tags_equal'] = metadata[0] == metadata[1]
                        if metadata[0] != metadata[1]:
                            row['gbwt_metadata_and_tags'] = dict(zip(('old', 'candidate'), metadata))
                    row['status'] = ('PASS' if row['gfa_records_equal']
                                     and row.get('gbwt_metadata_and_tags_equal', True) else 'FAIL')
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                row.update(status='ERROR', error=str(error))
            rows.append(row)
            print(f"{row['status']} {name}", flush=True)
        passed = all(row['status'] == 'PASS' for row in rows)
        json.dump({'scope': 'decoded_GFA_records_and_GBWT_metadata_and_tags',
                   'decoded_content_pass': passed, 'files': rows,
                   'source_report': str(args.report.resolve()), 'threads': args.threads}, report, indent=2)
        report.write('\n')
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
