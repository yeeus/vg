#!/usr/bin/env python3
"""Validate TBI files against their own VCFs and combine the chr21 checks."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import gzip
from itertools import zip_longest
import json
from pathlib import Path
import subprocess
import tempfile


@contextmanager
def tabix_output(command):
    with subprocess.Popen(command, stdout=subprocess.PIPE) as process:
        with process.stdout as output:
            yield output
        status = process.wait()
        if status:
            raise subprocess.CalledProcessError(status, command)


def compare_records(expected, observed):
    count = 0
    for count, (left, right) in enumerate(zip_longest(expected, observed), 1):
        if left is None or right is None or left.rstrip(b'\r\n') != right.rstrip(b'\r\n'):
            raise ValueError(f'Query output differs at line {count}')
    return count


def check_index(vcf, index, tabix, tmp):
    # Give each VCF alias only its intended TBI, so a CSI cannot take precedence.
    with tempfile.TemporaryDirectory(prefix='tbi-check-', dir=tmp) as directory:
        scratch = Path(directory)
        actual = scratch / 'actual.vcf.gz'
        rebuilt = scratch / 'rebuilt.vcf.gz'
        actual.symlink_to(vcf.resolve(strict=True))
        rebuilt.symlink_to(vcf.resolve(strict=True))
        Path(str(actual) + '.tbi').symlink_to(index.resolve(strict=True))
        subprocess.run([tabix, '-p', 'vcf', str(rebuilt)], check=True)
        with gzip.open(index, 'rb') as left, gzip.open(str(rebuilt) + '.tbi', 'rb') as right:
            same_index = left.read() == right.read()
        contigs = subprocess.check_output([tabix, '-l', str(rebuilt)], text=True).splitlines()
        actual_contigs = subprocess.check_output([tabix, '-l', str(actual)], text=True).splitlines()
        if contigs != actual_contigs:
            raise ValueError('Indexed contig names differ from the rebuilt index')

        with gzip.open(vcf, 'rb') as data:
            records = (line for line in data if not line.startswith(b'#'))
            if contigs:
                with tabix_output([tabix, str(actual), *contigs]) as queried:
                    record_count = compare_records(records, queried)
            else:
                record_count = compare_records(records, ())

        result = {'records_queried': record_count, 'contigs': contigs,
                  'rebuilt_tbi_payload_equal': same_index}
        if not same_index and contigs:
            # Cover the TBI coordinate space using its 16 kb linear-index grid.
            # Separate-region markers retain which window returned each record.
            regions = scratch / 'windows.tsv'
            step = 1 << 14
            limit = 1 << 29
            with regions.open('w', encoding='utf-8') as stream:
                for contig in contigs:
                    for start in range(0, limit, step):
                        stream.write(f'{contig}\t{start + 1}\t{start + step}\n')
            command = [tabix, '--separate-regions', '--cache', '32', '-R', str(regions)]
            with tabix_output([*command, str(rebuilt)]) as expected:
                with tabix_output([*command, str(actual)]) as observed:
                    compare_records(expected, observed)
            result['tiled_queries_equal'] = True
        return result


def read_recheck(path, source, scope, expected):
    report = json.loads(path.read_text(encoding='utf-8'))
    if Path(report['source_report']).resolve() != source or report.get('scope') != scope:
        raise ValueError(f'Recheck scope or source report mismatch: {path}')
    rows = {row['file']: row for row in report['files']}
    if len(rows) != len(report['files']) or rows.keys() != expected:
        raise ValueError(f'Recheck file list differs from the expected scope: {path}')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--vcf-report', type=Path, required=True)
    parser.add_argument('--graph-report', type=Path, required=True)
    parser.add_argument('--tmp', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tabix', default='tabix')
    parser.add_argument('--threads', type=int, default=16)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error('Use at least one thread')
    if args.output.exists():
        parser.error(f'Output already exists: {args.output}')
    original = json.loads(args.report.read_text(encoding='utf-8'))
    if original.get('status') != 'complete' or len(original.get('directories', [])) != 2:
        parser.error('Need a complete original verifier report')
    source = args.report.resolve()
    old, candidate = map(Path, original['directories'])
    rows = {row['file']: row for row in original['files']}
    if not rows or len(rows) != len(original['files']):
        parser.error('Expected a nonempty list of unique files')
    excluded = set(original.get('ignored_control_outputs', []))
    for directory, expected in ((old, set(rows) | excluded), (candidate, set(rows))):
        actual = {path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file()}
        if actual != expected:
            parser.error(f'Inventory changed since original check in {directory}: '
                         f'missing={sorted(expected - actual)} extra={sorted(actual - expected)}')
    vcf_rows = read_recheck(args.vcf_report, source, 'VCF_only',
                           {name for name in rows if name.endswith(('.vcf', '.vcf.gz'))})
    graph_rows = read_recheck(args.graph_report, source, 'decoded_GFA_records_and_GBWT_metadata_and_tags',
                             {name for name, row in rows.items()
                              if not row['pass'] and name.endswith(('.gbz', '.og'))})
    indexes = [name for name in rows if name.endswith('.tbi')]
    if not indexes or any(name[:-4] not in vcf_rows for name in indexes):
        parser.error('Expected TBI files with corresponding VCFs in the recheck report')

    def check_pair(name):
        result = {'file': name, 'check': 'TBI_queries_against_own_VCF', 'pass': True}
        for label, directory in (('old', old), ('candidate', candidate)):
            try:
                result[label] = check_index(directory / name[:-4], directory / name,
                                            args.tabix, args.tmp)
            except (OSError, EOFError, ValueError, subprocess.SubprocessError) as error:
                result['pass'] = False
                result[label] = {'error': str(error)}
        print(f"{'PASS' if result['pass'] else 'FAIL'} {name}", flush=True)
        return result

    # Each active comparison may have two simultaneous tabix subprocesses.
    with ThreadPoolExecutor(max_workers=max(1, args.threads // 2)) as pool:
        tbi_rows = {row['file']: row for row in pool.map(check_pair, indexes)}

    combined = []
    for name, original_row in rows.items():
        if name in tbi_rows:
            row = tbi_rows[name]
        elif name in vcf_rows:
            row = {**vcf_rows[name], 'check': 'VCF_all_fields_except_run_dates'}
        elif name in graph_rows:
            graph = graph_rows[name]
            passed = graph['status'] == 'PASS' and graph['gfa_records_equal'] is True
            if name.endswith('.gbz'):
                passed = passed and graph['gbwt_metadata_and_tags_equal'] is True
            row = {**graph, 'check': 'decoded_GFA_and_reported_metadata', 'pass': passed}
        else:
            row = dict(original_row)
        combined.append({**row, 'original_pass': original_row['pass']})

    passed = sum(row['pass'] is True for row in combined)
    result = {'scope': 'original_inventory_with_VCF_graph_and_TBI_rechecks',
              'pass': passed == len(combined), 'passed': passed, 'total': len(combined),
              'files': combined, 'ignored_control_outputs': sorted(excluded),
              'directories': original['directories'],
              'input_metadata_check': original.get('input_metadata_check'),
              'source_reports': [str(path.resolve()) for path in
                                 (args.report, args.vcf_report, args.graph_report)]}
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(f"{'PASS' if result['pass'] else 'FAIL'} {passed}/{len(combined)}")
    raise SystemExit(0 if result['pass'] else 1)


if __name__ == '__main__':
    main()
