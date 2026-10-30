#!/usr/bin/env python3
"""Two configurations only: real original tools versus the integrated candidate."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import sys

FLAGS=dict(VG_BENCH_NUMERIC_IDS='1',VG_BENCH_FAST_SERIALIZE='1',VG_BENCH_PATH_THREADS='4',
           VG_BENCH_XG_MODE='compact',VG_BENCH_COMPACT_MEMBERSHIP='1')

def environment(prefix,mode):
    env={k:v for k,v in os.environ.items() if not k.startswith('VG_BENCH_')}
    env['LD_LIBRARY_PATH']=str(prefix/mode/'lib')+':'+env.get('LD_LIBRARY_PATH','')
    env['OMP_NUM_THREADS']='4'
    if mode=='candidate': env.update(FLAGS)
    return env

def pipeline(commands,output,env):
    command='set -eo pipefail; '+' | '.join(shlex.join([str(x) for x in c]) for c in commands)
    with output.open('wb') as stream:
        result=subprocess.run(['bash','-c',command],env=env,stdout=stream,stderr=subprocess.PIPE)
    if result.returncode: raise RuntimeError(command+'\n'+result.stderr.decode(errors='replace'))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('prefix',type=Path)
    args=p.parse_args()
    prefix=args.prefix.resolve()
    verify=prefix/'candidate/bin/vg'
    with tempfile.TemporaryDirectory(prefix='cactus-join-small-') as temporary:
        root=Path(temporary)
        fixture='H\tVN:Z:1.1\nS\t1\t'+('A'*1500)+'\nS\t2\tACGT\nS\t3\tACGA\nS\t4\t'+('C'*21000)+'\nS\t5\tT\n'
        fixture+='L\t1\t+\t2\t+\t0M\nL\t1\t+\t3\t+\t0M\nL\t2\t+\t5\t+\t0M\nL\t3\t+\t4\t+\t0M\nL\t4\t+\t5\t+\t0M\n'
        fixture+='P\tGRCh38#0#chr21\t1+,2+,5+\t*\nP\tCHM13v2#0#chr21\t1+,2+,5+\t*\nP\tCN1v1#0#chr21\t1+,3+,4+,5+\t*\nP\t_MINIGRAPH_#0#chr21\t1+,2+,5+\t*\nW\tsample\t1\tchr21\t0\t22505\t>1>3>4>5\n'
        cases={
            'branch':fixture,
            'inverted_reference':fixture.replace('1+,2+,5+','1+,2-,5+').replace('L\t1\t+\t2\t+', 'L\t1\t+\t2\t-').replace('L\t2\t+\t5\t+', 'L\t2\t-\t5\t+'),
            'repeat':fixture+'L\t5\t+\t1\t+\t0M\nW\trepeat\t1\tchr21\t0\t3010\t>1>2>5>1>2>5\n',
            'large_deletion':fixture.replace('S\t2\tACGT', 'S\t2\t'+'G'*10001000)+'L\t1\t+\t5\t+\t0M\nW\tdeletion\t1\tchr21\t0\t1501\t>1>5\n',
        }
        temporary_root=root
        for label,fixture in cases.items():
            root=temporary_root/label
            root.mkdir()
            source=root/'input.gfa'
            source.write_text(fixture,encoding='utf-8')
            graph=root/'input.vg'
            pipeline([[prefix/'control/bin/vg','convert','-g','-p',source]],graph,environment(prefix,'control'))
            for mode in ('control','candidate'):
                env=environment(prefix,mode)
                directory=root/mode
                directory.mkdir()
                vg=prefix/mode/'bin/vg'
                clip=prefix/mode/'bin/clip-vg'
                gf=prefix/mode/'bin/gfaffix'
                export=[vg,'convert','-f',graph]
                if mode=='candidate': export+=['--require-sample','GRCh38']
                pipeline([export],directory/'input.gfa',env)
                subprocess.run([str(gf),str(directory/'input.gfa'),'--output_refined',str(directory/'fixed.gfa'),
                                '--check_transformation','--threads','1','--dont_collapse','GRCh38#[.]*'],env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                unchop=[[vg,'convert','-g','-p',directory/'fixed.gfa'],[vg,'mod','-u','-']]
                if mode=='candidate': unchop=[[vg,'convert','-g','-p','--unchop',directory/'fixed.gfa']]
                pipeline(unchop,directory/'unchop.vg',env)
                full=[[clip,directory/'unchop.vg','-f','-e','GRCh38','-d','_MINIGRAPH_','-L','-F']]
                full += ([[vg,'clip','--cactus-full','-','-P','GRCh38']] if mode=='candidate' else [
                    [vg,'mod','-X','1024','-'],[vg,'paths','-x','-','-n','-Q','GRCh38','-t','1'],
                    [vg,'clip','-d','1','-','-P','GRCh38'],[vg,'ids','-s','-']])
                pipeline(full,directory/'full.vg',env)
                clip_pipeline=[[clip,directory/'full.vg','-f','-e','GRCh38','-d','_MINIGRAPH_',
                                '-u','10000','-a','_MINIGRAPH_','-I','100000','-k','50000','-T','-1.0']]
                final_clip=[vg,'clip','-','-D','10000000','-P','GRCh38','-c','1000','-m','1000']
                if mode=='candidate': final_clip.insert(2,'--cactus-clip')
                else: clip_pipeline += [[vg,'clip','-d','1','-','-P','GRCh38'],[vg,'clip','-sS','-','-P','GRCh38']]
                pipeline(clip_pipeline+[final_clip],directory/'clip.vg',env)
                filtering=[vg,'clip',directory/'clip.vg','-d','132','-P','GRCh38','-P','CHM13v2','-P','CN1v1','-m','1000']
                filters=[filtering]
                if mode=='candidate': filtering.insert(2,'--cactus-filter')
                else: filters += [[vg,'clip','-d','1','-','-P','GRCh38','-P','CHM13v2','-P','CN1v1'],[vg,'clip','-sS','-','-P','GRCh38']]
                pipeline(filters,directory/'filter.vg',env)
                pipeline([[vg,'convert','-f',directory/'clip.vg']],directory/'clip.gfa',env)
                # Match make_vg_indexes, then the actual GBZ -> XG input route.
                subprocess.run([str(vg),'gbwt','-G',str(directory/'clip.gfa'),'--gbz-format','-g',str(directory/'clip.gbz'),
                                '--translation',str(directory/'clip.trans')],env=env,check=True,
                               stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                pipeline([[vg,'convert','-x',directory/'clip.gbz','-t','4']],directory/'clip.xg',env)
            assert (root/'control/input.gfa').read_bytes()==(root/'candidate/input.gfa').read_bytes()
            assert (root/'control/clip.xg').read_bytes()==(root/'candidate/clip.xg').read_bytes()
            assert (root/'control/clip.gbz').read_bytes()==(root/'candidate/clip.gbz').read_bytes()
            for stage in ('unchop','full','clip','filter'):
                values=[]
                for mode in ('control','candidate'):
                    for threads in ('1','4'):
                        values.append(json.loads(subprocess.check_output([str(verify),'unchop-fingerprint','--threads',threads,
                                                                         str(root/mode/(stage+'.vg'))],env=environment(prefix,'candidate'))))
                assert all(v==values[0] for v in values),stage
            missing=subprocess.run([str(verify),'convert','-f',str(graph),'--require-sample','MISSING'],
                                   env=environment(prefix,'candidate'),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            assert missing.returncode and not missing.stdout,'Reference check must fail before emitting GFA'
            # Exercise the delivered verifier on the real component outputs,
            # including XG loading and full GBZ payload comparison.
            checker=Path(__file__).with_name('verify.py')
            for mode in ('control','candidate'):
                directory=root/mode
                (directory/'final').mkdir()
                for name in ('unchop.vg','full.vg','clip.vg','filter.vg','clip.xg','clip.gbz','clip.gfa'):
                    (directory/'final'/name).symlink_to(directory/name)
                (directory/'summary.json').write_text(json.dumps({'exit_code':0}),encoding='utf-8')
                (directory/'inputs.log').write_text(str(source),encoding='utf-8')
            checked=subprocess.run([sys.executable,str(checker),str(root/'control'),str(root/'candidate'),
                                    '--vg',str(verify),'--threads','4','--output',str(root/'verified')],
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            if checked.returncode: raise RuntimeError(checked.stdout.decode()+checked.stderr.decode())
    print('PASS four fixtures x two configurations: export/sample check, GFAffix, unchop, full, clip, filter, complete GBZ and XG; 1/4-thread fingerprints')

if __name__=='__main__': main()
