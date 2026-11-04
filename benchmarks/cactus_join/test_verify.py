#!/usr/bin/env python3
"""Call the real verifier: record ordering passes; genotype/path/index corruption fails."""
import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil

def main():
    p=argparse.ArgumentParser()
    p.add_argument('vg',type=Path)
    args=p.parse_args()
    verify=Path(__file__).with_name('verify.py')
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)
        gfa=b'H\tVN:Z:1.1\nS\t1\tA\nS\t2\tC\nL\t1\t+\t2\t+\t0M\nP\ts#1#c\t1+,2+\t*\n'
        vcf=b'##fileformat=VCFv4.2\n##fileDate=20261030\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\ts\nc\t1\t.\tA\tC\t.\t.\t.\tGT\t0|1\n'
        for mode in ('control','candidate'):
            out=root/mode
            (out/'final').mkdir(parents=True)
            (out/'summary.json').write_text(json.dumps({'exit_code':0}),encoding='utf-8')
            (out/'inputs.log').write_text('same chromosome, references and input',encoding='utf-8')
            (out/'final/index.bin').write_bytes(bytes(range(256))*100)
            with gzip.open(out/'final/graph.gfa.gz','wb') as stream:
                stream.write(gfa if mode=='control' else b'\n'.join(reversed(gfa.rstrip().splitlines()))+b'\n')
            with gzip.open(out/'final/graph.vcf.gz','wb') as stream:
                stream.write(vcf if mode=='control' else vcf.replace(b'20261030',b'20261101'))
        graph_source=root/'input.gfa'
        graph_source.write_bytes(gfa)
        env=dict(os.environ)
        env['LD_LIBRARY_PATH']=str(args.vg.resolve().parent.parent/'lib')+':'+env.get('LD_LIBRARY_PATH','')
        with (root/'control/final/graph.vg').open('wb') as stream:
            subprocess.run([str(args.vg.resolve()),'convert','-g','-p',str(graph_source)],
                           env=env,stdout=stream,stderr=subprocess.PIPE,check=True)
        shutil.copyfile(root/'control/final/graph.vg',root/'candidate/final/graph.vg')
        def check(name,expected,legacy=False,extra=()):
            result=subprocess.run([sys.executable,str(verify),str(root/'control/final' if legacy else root/'control'),str(root/'candidate'),
                                   '--vg',str(args.vg.resolve()),'--threads','4','--output',str(root/name),
                                   *(['--legacy-control'] if legacy else []),*extra],
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            assert (result.returncode==0)==expected,(name,result.stdout,result.stderr)
        check('pass-reordered-gfa-and-date',True)
        if shutil.which('h5cc') and shutil.which('h5diff') and shutil.which('h5repack'):
            source=root/'fixture.c'
            source.write_text('''#include <hdf5.h>
#include <stdlib.h>
int main(int argc, char** argv) {
    hid_t file=H5Fcreate(argv[1],H5F_ACC_TRUNC,H5P_DEFAULT,H5P_DEFAULT);
    hsize_t n=3; int values[3]={1,2,atoi(argv[2])};
    hid_t space=H5Screate_simple(1,&n,0);
    hid_t data=H5Dcreate2(file,"alignment",H5T_NATIVE_INT,space,H5P_DEFAULT,H5P_DEFAULT,H5P_DEFAULT);
    H5Dwrite(data,H5T_NATIVE_INT,H5S_ALL,H5S_ALL,H5P_DEFAULT,values);
    H5Dclose(data); H5Sclose(space); H5Fclose(file); return 0;
}
''',encoding='utf-8')
            subprocess.run(['h5cc',str(source),'-o',str(root/'fixture')],cwd=root,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            a=root/'control/final/alignment.hal'
            b=root/'candidate/final/alignment.hal'
            subprocess.run([str(root/'fixture'),str(a),'3'],check=True)
            subprocess.run(['h5repack','-f','GZIP=1',str(a),str(b)],check=True,stdout=subprocess.DEVNULL)
            check('pass-hdf5-layout-change',True)
            subprocess.run([str(root/'fixture'),str(b),'4'],check=True)
            check('fail-hdf5-data-change',False)
            a.unlink(); b.unlink()
        with gzip.open(root/'candidate/final/graph.vcf.gz','wb') as stream: stream.write(vcf.replace(b'0|1',b'1|0'))
        check('fail-phase-change',False)
        with gzip.open(root/'candidate/final/graph.vcf.gz','wb') as stream: stream.write(vcf)
        with gzip.open(root/'candidate/final/graph.gfa.gz','wb') as stream: stream.write(gfa.replace(b'1+,2+',b'2+,1+'))
        check('fail-path-step-change',False)
        with gzip.open(root/'candidate/final/graph.gfa.gz','wb') as stream: stream.write(gfa)
        (root/'candidate/final/index.bin').write_bytes(b'corrupt')
        check('fail-index-change',False)
        (root/'candidate/final/index.bin').unlink()
        check('fail-missing-output',False)
        (root/'candidate/final/index.bin').write_bytes((root/'control/final/index.bin').read_bytes())
        # A historical final directory has no wrapper metadata, and contains
        # explicitly out-of-scope outputs. Never fabricate successful metadata.
        (root/'control/summary.json').unlink()
        (root/'control/inputs.log').unlink()
        (root/'control/final/old.full.hal').write_bytes(b'out-of-scope old output')
        with gzip.open(root/'control/final/derived.vcf.gz','wb') as stream: stream.write(vcf)
        allowed=['--allow-control-extra','old.full.hal','--allow-control-extra','derived.*']
        check('fail-unapproved-legacy-extras',False,legacy=True)
        check('pass-legacy-without-wrapper-metadata',True,legacy=True,extra=allowed)
        report=json.loads((root/'pass-legacy-without-wrapper-metadata/report.json').read_text(encoding='utf-8'))
        assert report['workflow_resources']['control'] is None
        assert report['input_metadata_check']=='unavailable_for_legacy_control'
        assert report['ignored_control_outputs']==['derived.vcf.gz','old.full.hal']
        assert any(row['check']=='strict_graph_identity' for row in report['files'])
        (root/'control/final/required.gbz').write_bytes(b'required')
        check('fail-unapproved-legacy-output',False,legacy=True,extra=allowed)
        (root/'control/final/required.gbz').unlink()
        (root/'candidate/final/new.gbz').write_bytes(b'new output has no historical counterpart')
        check('fail-legacy-missing-baseline-counterpart',False,legacy=True,extra=allowed)
        (root/'candidate/final/new.gbz').unlink()
        (root/'candidate/final/index.bin').unlink()
        check('fail-legacy-missing-candidate-output',False,legacy=True,extra=allowed)
        (root/'candidate/final/index.bin').write_bytes((root/'control/final/index.bin').read_bytes())
        with gzip.open(root/'candidate/final/graph.vcf.gz','wb') as stream: stream.write(vcf.replace(b'0|1',b'1|0'))
        check('fail-legacy-shared-file-cannot-be-excluded',False,legacy=True,extra=['--allow-control-extra','*'])
        with gzip.open(root/'candidate/final/graph.vcf.gz','wb') as stream: stream.write(vcf)
        (root/'candidate/summary.json').write_text(json.dumps({'exit_code':1}),encoding='utf-8')
        check('fail-legacy-candidate-not-successful',False,legacy=True,extra=allowed)
    print('PASS real verifier: paired/legacy modes, parallel graph checks, VCF phase/path/index corruption, explicit extras and missing-output detection')

if __name__=='__main__': main()
