#!/usr/bin/env python3
"""Exercise format-aware verification with real vg, ODGI, bgzip and tabix."""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vg', required=True)
    parser.add_argument('--odgi', default='odgi')
    parser.add_argument('--bgzip', default='bgzip')
    parser.add_argument('--tabix', default='tabix')
    args = parser.parse_args()
    verifier = Path(__file__).with_name('verify.py')

    with tempfile.TemporaryDirectory(prefix='verify-formats-') as temporary:
        root = Path(temporary)
        prefix = 'H\tVN:Z:1.1\tRS:Z:GRCh38\nS\t1\tA\nS\t2\tC\nS\t3\tG\n'
        prefix += 'L\t1\t+\t2\t+\t0M\nL\t2\t+\t3\t+\t0M\n'
        paths = ['P\tGRCh38#0#chr1\t1+,2+,3+\t*\n',
                 'P\tsample#1#chr1\t1+,2+,3+\t*\n',
                 'P\tsample#2#chr1\t1+,2+,3+\t*\n']
        headers = ('##fileformat=VCFv4.2\n##fileDate=DATE\n'
                   '##contig=<ID=chr1,length=1000000>\n'
                   '##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n'
                   '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tsample\n')
        records = ('chr1\t2\t.\tC\tG\t.\tPASS\t.\tGT\t0|1\n'
                   'chr1\t16384\t.\tA\tT\t.\tPASS\t.\tGT\t0|1\n'
                   'chr1\t16385\t.\tA\tC\t.\tPASS\t.\tGT\t0|1\n')

        def write_vcf(mode, text):
            plain = root/(mode+'.vcf')
            plain.write_text(text, encoding='utf-8')
            target = root/mode/'final/graph.vcf.gz'
            with target.open('wb') as output:
                subprocess.run([args.bgzip, '-c', str(plain)], stdout=output, check=True)
            subprocess.run([args.tabix, '-f', '-p', 'vcf', str(target)], check=True)

        for mode in ('control', 'candidate'):
            final = root/mode/'final'
            final.mkdir(parents=True)
            (root/mode/'summary.json').write_text('{"exit_code":0}\n', encoding='utf-8')
            (root/mode/'inputs.log').write_text('same chromosome and references\n', encoding='utf-8')
            source = root/(mode+'.gfa')
            source.write_text(prefix+''.join(paths if mode == 'control' else reversed(paths)), encoding='utf-8')
            subprocess.run([args.vg, 'gbwt', '-G', str(source), '--gbz-format', '-g', str(final/'graph.gbz')],
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            subprocess.run([args.odgi, 'build', '-g', str(source), '-o', str(final/'graph.og'), '-t', '2'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            with gzip.open(final/'graph.gfa.gz', 'wb') as output:
                output.write((prefix+''.join(paths)).encode())
            (final/'ordinary.bin').write_bytes(bytes(range(256)))
            date = '20261104' if mode == 'control' else '20261109T010203+0800'
            write_vcf(mode, headers.replace('DATE', date)+records)

        actual_index = root/'candidate/final/graph.vcf.gz.tbi'
        # Older TBI files may omit the optional n_no_coor trailer.
        payload = gzip.decompress(actual_index.read_bytes())
        assert payload[-8:] == bytes(8)
        actual_index.write_bytes(gzip.compress(payload[:-8]))
        baseline = {mode:{path.name:path.read_bytes() for path in (root/mode/'final').iterdir()}
                    for mode in ('control', 'candidate')}

        def restore():
            for mode in ('control', 'candidate'):
                for name, data in baseline[mode].items():
                    (root/mode/'final'/name).write_bytes(data)

        def check(name, expected, legacy=False):
            command = [sys.executable, str(verifier),
                       str(root/'control/final' if legacy else root/'control'),
                       str(root/'candidate'), '--vg', args.vg, '--odgi', args.odgi,
                       '--tabix', args.tabix, '--threads', '4', '--tmp', str(root),
                       '--output', str(root/name)]
            if legacy:
                command += ['--legacy-control', '--allow-control-extra', 'old.full.hal']
            completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            report = json.loads((root/name/'report.json').read_text(encoding='utf-8'))
            assert (completed.returncode == 0) == expected, (name, completed.stdout, completed.stderr, report)
            assert report['status'] == 'complete', report
            return {row['file']:row for row in report['files']}

        rows = check('valid-different-storage', True)
        assert rows['graph.og']['binary_bytes_equal'] is False
        assert rows['graph.og']['gfa_records_equal'] is True
        assert rows['graph.gbz']['binary_bytes_equal'] is False
        assert rows['graph.gbz']['gbwt_metadata_and_tags_equal'] is True
        assert rows['graph.vcf.gz.tbi']['binary_bytes_equal'] is False
        assert rows['graph.vcf.gz.tbi']['candidate']['tiled_queries_equal'] is True

        write_vcf('candidate', headers.replace('DATE', '20261109')+records.replace('0|1', '1|0'))
        rows = check('changed-phase', False)
        assert rows['graph.vcf.gz']['pass'] is False
        assert rows['graph.vcf.gz.tbi']['pass'] is True
        restore()

        (root/'candidate/final/ordinary.bin').write_bytes(b'changed')
        rows = check('changed-ordinary-binary', False)
        assert rows['ordinary.bin']['pass'] is False
        restore()

        tagged = root/'tagged.gbz'
        subprocess.run([args.vg, 'gbwt', '-Z', str(root/'candidate/final/graph.gbz'),
                        '--set-tag', 'verify_probe=changed', '--gbz-format', '-g', str(tagged)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        shutil.copyfile(tagged, root/'candidate/final/graph.gbz')
        rows = check('changed-gbwt-tag', False)
        assert rows['graph.gbz']['gfa_records_equal'] is True
        assert rows['graph.gbz']['gbwt_metadata_and_tags_equal'] is False
        restore()

        changed_gfa = root/'changed.gfa'
        changed_gfa.write_text(prefix+''.join(paths).replace('sample#1#chr1','renamed#1#chr1'), encoding='utf-8')
        subprocess.run([args.odgi, 'build', '-g', str(changed_gfa),
                        '-o', str(root/'candidate/final/graph.og'), '-t', '2'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        rows = check('changed-og-path', False)
        assert rows['graph.og']['gfa_records_equal'] is False
        assert rows['graph.og']['first_difference']['byte_offset'] >= 0
        restore()

        for mode in ('control', 'candidate'):
            (root/mode/'final/graph.vcf.gz.tbi').write_bytes(gzip.compress(b'TBI\x01invalid'))
        rows = check('identical-corrupt-indexes', False)
        assert rows['graph.vcf.gz.tbi']['binary_bytes_equal'] is True
        assert rows['graph.vcf.gz.tbi']['pass'] is False
        restore()

        (root/'candidate/final/graph.gbz').write_bytes(b'truncated GBZ')
        rows = check('broken-gbz', False)
        assert rows['graph.gbz']['status'] == 'ERROR'
        assert len(rows) == 6
        restore()

        (root/'control/final/old.full.hal').write_bytes(b'historical-only')
        rows = check('legacy-valid', True, legacy=True)
        assert len(rows) == 6
        print('PASS real format checks: storage changes, tiled TBI queries, VCF phase, GBWT tags, ODGI paths, corrupt indexes, decoder errors and legacy mode')


if __name__ == '__main__':
    main()
