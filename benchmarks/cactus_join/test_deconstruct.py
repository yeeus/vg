#!/usr/bin/env python3
"""Check complete tiny VCF outputs and an independently known phased SNP."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def environment(vg, candidate):
    env = {k: v for k, v in os.environ.items() if not k.startswith('VG_BENCH_')}
    env['LD_LIBRARY_PATH'] = str(vg.parent.parent/'lib') + ':' + env.get('LD_LIBRARY_PATH', '')
    if candidate:
        env.update(VG_BENCH_NUMERIC_IDS='1', VG_BENCH_FAST_SERIALIZE='1',
                   VG_BENCH_XG_MODE='compact', VG_BENCH_COMPACT_MEMBERSHIP='1',
                   VG_BENCH_PATH_THREADS='4')
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('control', type=Path)
    parser.add_argument('candidate', type=Path)
    args = parser.parse_args()
    tools = (args.control.resolve(), args.candidate.resolve())
    with tempfile.TemporaryDirectory(prefix='vg-vcf-header-') as temporary:
        root = Path(temporary)
        for reference in ('GRCh38', 'gref_GRCh38'):
            gfa = root/(reference+'.gfa')
            gfa.write_text(
                'H\tVN:Z:1.1\tRS:Z:'+reference+'\n'
                'S\t1\tA\nS\t2\tC\nS\t3\tG\nS\t4\tT\n'
                'L\t1\t+\t2\t+\t0M\nL\t2\t+\t4\t+\t0M\n'
                'L\t1\t+\t3\t+\t0M\nL\t3\t+\t4\t+\t0M\n'
                'W\t'+reference+'\t0\tchr21\t0\t3\t>1>2>4\n'
                'W\tsample\t1\tchr21\t0\t3\t>1>3>4\n'
                'W\tsample\t2\tchr21\t0\t3\t>1>2>4\n', encoding='utf-8')
            graph = root/(reference+'.vg')
            with graph.open('wb') as output:
                subprocess.run([str(tools[0]), 'convert', '-g', '-p', str(gfa)],
                               env=environment(tools[0], False), stdout=output, check=True)
            outputs = []
            for index, vg in enumerate(tools):
                for threads in ('1', '4'):
                    result = subprocess.run(
                        [str(vg), 'deconstruct', str(graph), '-C', '-a', '-t', threads, '-P', reference],
                        env=environment(vg, index == 1), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if result.returncode:
                        raise RuntimeError(str(vg)+' exited '+str(result.returncode)+'\n'+result.stderr.decode(errors='replace'))
                    lines = result.stdout.decode().splitlines()
                    assert lines[0] == '##fileformat=VCFv4.2', lines
                    assert '##contig=<ID=chr21,length=3>' in lines, lines
                    columns = next(line for line in lines if line.startswith('#CHROM')).split('\t')
                    assert columns[9:] == ['sample'], columns
                    records = [line.split('\t') for line in lines if line and not line.startswith('#')]
                    assert len(records) == 1, records
                    record = records[0]
                    assert record[0:2] == ['chr21', '2'] and record[3:5] == ['C', 'G'], record
                    gt = record[9].split(':')[record[8].split(':').index('GT')]
                    assert gt == '1|0', record
                    outputs.append(result.stdout)
            assert all(output == outputs[0] for output in outputs), 'Full VCF differs across tools or threads'
    print('PASS standard/gref VCF: complete headers/records, chr21:2 C>G, GT=1|0, control/candidate x 1/4 threads')


if __name__ == '__main__':
    main()
