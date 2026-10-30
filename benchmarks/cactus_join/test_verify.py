#!/usr/bin/env python3
"""Call the real verifier: record ordering passes; genotype/path/index corruption fails."""
import argparse
import gzip
import json
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
        def check(name,expected):
            result=subprocess.run([sys.executable,str(verify),str(root/'control'),str(root/'candidate'),
                                   '--vg',str(args.vg.resolve()),'--threads','4','--output',str(root/name)],
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
    print('PASS real parallel verifier: harmless ordering/date; phase/path/index changes and missing output detection')

if __name__=='__main__': main()
