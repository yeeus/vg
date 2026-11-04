#!/usr/bin/env python3
"""Recheck only complete VCF content; never replace the full verifier report."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from verify import compare_streams


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('report',type=Path,help='completed verify_original/report.json')
    parser.add_argument('--threads',type=int,default=16)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    previous=json.loads(args.report.read_text(encoding='utf-8'))
    if previous.get('status')!='complete' or len(previous.get('directories',[]))!=2:
        parser.error('Need a complete verifier report containing two final directories')
    if args.threads<2: parser.error('Use at least two threads')
    names=[row['file'] for row in previous['files'] if row['file'].endswith(('.vcf','.vcf.gz'))]
    if not names: parser.error('No VCF files in this report')
    old,new=map(Path,previous['directories'])
    def compare(name):
        detail={}
        equal=compare_streams(old/name,new/name,name.endswith('.gz'),True,detail)
        row={'file':name,'pass':equal}
        if detail: row['first_difference']=detail
        return row
    with args.output.open('x',encoding='utf-8') as output:
        with ThreadPoolExecutor(max_workers=args.threads) as pool:
            rows=list(pool.map(compare,names))
        passed=all(row['pass'] for row in rows)
        result={'scope':'VCF_only','vcf_pass':passed,'threads':args.threads,'files':rows,
                'source_report':str(args.report.resolve()),
                'timestamp_policy':'ignore fileDate and only trailing bcftools_*Command Date; all other content exact',
                'previous_non_vcf_failures':[row['file'] for row in previous['files']
                    if not row['pass'] and row['file'] not in names]}
        json.dump(result,output,indent=2)
        output.write('\n')
    for row in rows: print(('PASS' if row['pass'] else 'FAIL')+' '+row['file'])
    print('VCF_ONLY: '+('PASS' if passed else 'FAIL')+'; binary/index failures remain unresolved')
    raise SystemExit(0 if passed else 1)


if __name__=='__main__': main()
