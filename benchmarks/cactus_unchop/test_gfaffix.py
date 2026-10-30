#!/usr/bin/env python3
"""Run real old/new GFAffix with transformation checks; compare all GFA fields."""
import argparse
import gzip
import subprocess
import tempfile
import random
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument('control')
    p.add_argument('candidate')
    p.add_argument('examples', type=Path)
    args = p.parse_args()
    fixtures = sorted(args.examples.glob('*.gfa'))
    with tempfile.TemporaryDirectory() as temporary:
        tmp = Path(temporary)
        extra = tmp/'mixed.gfa'
        extra.write_text('H\tVN:Z:1.1\nS\t1\tACGT\nS\t2\tACGA\nS\t3\tC\nL\t3\t+\t1\t+\t0M\nL\t3\t+\t2\t+\t0M\nP\tGRCh38#0#chr21\t3+,1+\t*\nW\tsample\t1\tchr21\t5\t10\t>3>2\n',encoding='utf-8')
        fixtures.append(extra)
        # gzip input exercises every streaming pass and retained W coordinates.
        compressed = tmp/'mixed.gfa.gz'
        with gzip.open(compressed,'wb') as out: out.write(extra.read_bytes())
        fixtures.append(compressed)
        for seed in range(12):
            rng=random.Random(seed)
            data=['H\tVN:Z:1.1']
            ids=[3*i+1 for i in range(24)]
            for node in ids:
                data.append(f'S\t{node}\tA'+''.join(rng.choice('ACGTacgtN') for _ in range(5)))
            for i,node in enumerate(ids[:-1]):
                data.append(f'L\t{node}\t+\t{ids[i+1]}\t+\t0M')
                if i+2<len(ids): data.append(f'L\t{node}\t+\t{ids[i+2]}\t+\t0M')
            data.append('P\tGRCh38#0#chr21\t'+','.join(f'{n}+' for n in ids)+'\t*')
            data.append('P\treverse#1#chr21\t'+','.join(f'{n}-' for n in reversed(ids))+'\t*')
            data.append('P\tskip#1#chr21\t'+','.join(f'{n}+' for n in ids[::2])+'\t*')
            generated=tmp/f'generated-{seed}.gfa'
            generated.write_text('\n'.join(data)+'\n',encoding='utf-8')
            fixtures.append(generated)
        runs = 0
        for fixture in fixtures:
            for protected in ('', 'GRCh38#[.]*'):
                values=[]
                for binary in (args.control,args.candidate):
                    command=[binary,str(fixture),'--threads','1','--check_transformation']
                    if protected: command+=['--dont_collapse',protected]
                    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                    if result.returncode:
                        raise RuntimeError(f'{command}: {result.stderr.decode()}')
                    # Line order is unspecified; every field and path step is compared.
                    values.append(sorted(result.stdout.splitlines()))
                assert values[0]==values[1],(fixture,protected)
                runs+=1
        print(f'PASS {runs} GFAffix old/new pairs, including protected paths, W records and gzip')

if __name__=='__main__': main()
