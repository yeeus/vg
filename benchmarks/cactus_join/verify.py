#!/usr/bin/env python3
"""Conservative complete-output comparison with parallel streaming and graph hashing.

PASS requires every delivered file. Graph fingerprints exclude storage layout;
other binary indexes require complete byte identity. A differing binary never
falls back to a weaker graph-only check. Large graphs are loaded ONE AT A TIME.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile

def compare_streams(left,right,compressed=False,vcf=False):
    opener=gzip.open if compressed else open
    with opener(left,'rb') as a,opener(right,'rb') as b:
        if vcf:
            def lines(stream):
                for line in stream:
                    # Date is explicitly non-biological. All other headers,
                    # reference definitions and full variant records stay exact.
                    if not line.startswith(b'##fileDate='): yield line
            return all(x==y for x,y in __import__('itertools').zip_longest(lines(a),lines(b)))
        while True:
            x,y=a.read(4*1024*1024),b.read(4*1024*1024)
            if x!=y: return False
            if not x: return True

def canonical_gfa(path,out,threads,tmp):
    # Sort whole records, never the ordered steps within P/W records. External
    # sort bounds memory and ignores only unspecified inter-record ordering.
    with out.open('wb') as target:
        command=['sort','--parallel='+str(threads),'-S','512M','-T',str(tmp)]
        proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=target,env=dict(os.environ,LC_ALL='C'))
        try:
            opener=gzip.open if path.name.endswith('.gz') else open
            with opener(path,'rb') as source:
                for block in iter(lambda:source.read(4*1024*1024),b''): proc.stdin.write(block)
            proc.stdin.close()
            if proc.wait(): raise RuntimeError(f'sort failed: {path}')
        except BaseException:
            proc.kill(); proc.wait(); raise

def main():
    p=argparse.ArgumentParser()
    p.add_argument('control',type=Path)
    p.add_argument('candidate',type=Path)
    p.add_argument('--vg',required=True,type=Path,help='candidate/bin/vg, also used on control graphs')
    p.add_argument('--threads',type=int,default=8)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--tmp',type=Path,help='large scratch disk for GFA record sorting')
    args=p.parse_args()
    if args.threads<2: p.error('Use at least two verify threads')
    resources={}
    for parent in (args.control,args.candidate):
        summary=json.loads((parent/'summary.json').read_text(encoding='utf-8'))
        if summary['exit_code']!=0: raise RuntimeError(f'Workflow did not finish: {parent}')
        resources['control' if parent==args.control else 'candidate']=summary
    if (args.control/'inputs.log').read_bytes()!=(args.candidate/'inputs.log').read_bytes():
        raise RuntimeError('Different chromosome/reference/SV-GFA configuration')
    directories=[args.control/'final',args.candidate/'final']
    inventories=[{str(p.relative_to(d)):p for p in d.rglob('*') if p.is_file()} for d in directories]
    if inventories[0].keys()!=inventories[1].keys() or not inventories[0]:
        raise RuntimeError('Missing outputs or differing output inventory')
    args.output.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,LC_ALL='C',OMP_NUM_THREADS=str(args.threads))
    env['LD_LIBRARY_PATH']=str(args.vg.resolve().parent.parent/'lib')+':'+env.get('LD_LIBRARY_PATH','')
    tasks=[]
    graphs=[]
    gfas=[]
    for name in sorted(inventories[0]):
        if name.endswith(('.vg','.xg')): graphs.append(name)
        elif name.endswith(('.gfa','.gfa.gz')): gfas.append(name)
        else: tasks.append(name)
    records=[]
    def compare_file(name):
        a,b=map(lambda inv:inv[name],inventories)
        if name.endswith('.hal'):
            # Compare every HDF5 dataset/attribute, ignoring physical storage
            # layout and object creation timestamps in the container.
            result=subprocess.run(['h5diff','-q',str(a),str(b)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            if result.returncode not in (0,1):
                raise RuntimeError(f'h5diff failed for {name}: {result.stderr.decode(errors="replace")}')
            return {'file':name,'check':'all_HDF5_datasets_and_attributes','pass':result.returncode==0}
        vcf=name.endswith(('.vcf','.vcf.gz'))
        equal=compare_streams(a,b,name.endswith('.gz'),vcf)
        return {'file':name,'check':'vcf_all_fields' if vcf else 'complete_bytes_or_decompressed_bytes','pass':equal}
    # These tasks stream small buffers; they do NOT load graph objects.
    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        records.extend(pool.map(compare_file,tasks))
    with tempfile.TemporaryDirectory(dir=args.tmp,prefix='join-verify-') as temporary:
        tmp=Path(temporary)
        for name in gfas:
            for i in range(2): canonical_gfa(inventories[i][name],tmp/str(i),args.threads,tmp)
            records.append({'file':name,'check':'all_GFA_records_sorted_without_altering_paths','pass':compare_streams(tmp/'0',tmp/'1')})
            (tmp/'0').unlink(); (tmp/'1').unlink()
    for name in graphs:
        values=[]
        for index,inventory in enumerate(inventories):
            log=args.output/(str(len(records))+f'.{index}.graph.json')
            with log.open('wb') as output:
                subprocess.run([str(args.vg.resolve()),'unchop-fingerprint','--threads',str(args.threads),str(inventory[name])],
                               stdout=output,env=env,check=True)
            values.append(json.loads(log.read_text(encoding='utf-8')))
        equal=values[0]==values[1]
        # XG includes coordinate/rank indexes beyond graph topology. Retain the
        # stronger complete index-byte requirement, even after graph checks.
        if name.endswith('.xg'): equal=equal and compare_streams(inventories[0][name],inventories[1][name])
        records.append({'file':name,'check':'strict_graph_identity'+('_and_complete_index_bytes' if name.endswith('.xg') else ''),'pass':equal})
    report={'pass':all(r['pass'] for r in records),'threads':args.threads,'files':records,'workflow_resources':resources,
            'binary_difference_policy':'FAIL; may require format-specific investigation, never silently waived'}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for row in records: print(('PASS' if row['pass'] else 'FAIL')+' '+row['file'])
    raise SystemExit(0 if report['pass'] else 1)

if __name__=='__main__': main()
