#!/usr/bin/env python3
"""Compare every output, including decoded binary graphs and functional TBI checks.

VCFs retain all fields except known run dates. GBZ and ODGI storage differences
are checked through full GFA records and GBWT metadata. TBI files are validated
against their own VCFs. XG retains complete index-byte equality. Large graph
objects are loaded one at a time.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from fnmatch import fnmatchcase
import gzip
import json
from itertools import zip_longest
import os
from pathlib import Path
import subprocess
import tempfile

def compare_streams(left,right,compressed=False,vcf=False,detail=None):
    opener=gzip.open if compressed else open
    with opener(left,'rb') as a,opener(right,'rb') as b:
        if vcf:
            def lines(stream):
                for line in stream:
                    if line.startswith(b'##fileDate='):
                        continue
                    # bcftools appends a run date to its command provenance.
                    # Retain the entire command and the separate Version line.
                    key=line.partition(b'=')[0]
                    if key.startswith(b'##bcftools_') and key.endswith(b'Command') and b'; Date=' in line:
                        line=line.rsplit(b'; Date=',1)[0]+b'\n'
                    yield line
            for number,(x,y) in enumerate(__import__('itertools').zip_longest(lines(a),lines(b)),1):
                if x==y: continue
                if detail is not None:
                    if x is None or y is None:
                        detail.update(compared_line=number,reason='different_line_counts')
                    else:
                        offset=next((i for i,(u,v) in enumerate(zip(x,y)) if u!=v),min(len(x),len(y)))
                        start=max(0,offset-60)
                        detail.update(compared_line=number,byte_column=offset+1,
                                      header_difference=x.startswith(b'#') or y.startswith(b'#'),
                                      field_number=x[:offset].count(b'\t')+1,
                                      old_context=x[start:offset+120].decode('utf-8','replace'),
                                      candidate_context=y[start:offset+120].decode('utf-8','replace'))
                return False
            return True
        position=0
        while True:
            x,y=a.read(4*1024*1024),b.read(4*1024*1024)
            if x!=y:
                if detail is not None:
                    offset=next((i for i,(u,v) in enumerate(zip(x,y)) if u!=v),min(len(x),len(y)))
                    start=max(0,offset-60)
                    detail.update(byte_offset=position+offset,
                                  old_context=x[start:offset+120].decode('utf-8','replace'),
                                  candidate_context=y[start:offset+120].decode('utf-8','replace'))
                return False
            if not x: return True
            position+=len(x)

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
        same_index = compare_streams(index, Path(str(rebuilt) + '.tbi'), compressed=True)
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


def main():
    p=argparse.ArgumentParser()
    p.add_argument('control',type=Path,help='benchmark root, or historical final/ directory with --legacy-control')
    p.add_argument('candidate',type=Path)
    p.add_argument('--vg',required=True,type=Path,help='candidate/bin/vg, also used on control graphs')
    p.add_argument('--threads',type=int,default=8)
    p.add_argument('--odgi',default='odgi',help='ODGI executable for decoding differing .og files')
    p.add_argument('--tabix',default='tabix',help='tabix executable for validating every VCF TBI')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--tmp',type=Path,help='large scratch disk for GFA record sorting')
    p.add_argument('--legacy-control',action='store_true',
                   help='control is a historical final directory without benchmark summary/inputs metadata')
    p.add_argument('--allow-control-extra',action='append',default=[],metavar='RELATIVE_GLOB',
                   help='allow matching historical-only files; shared files are always compared (legacy mode only)')
    args=p.parse_args()
    if args.threads<2: p.error('Use at least two verify threads')
    if args.allow_control_extra and not args.legacy_control:
        p.error('--allow-control-extra requires --legacy-control')
    resources={}
    for label,parent in (('control',args.control),('candidate',args.candidate)):
        if label=='control' and args.legacy_control:
            resources[label]=None
            continue
        summary=json.loads((parent/'summary.json').read_text(encoding='utf-8'))
        if summary['exit_code']!=0: raise RuntimeError(f'Workflow did not finish: {parent}')
        resources[label]=summary
    if not args.legacy_control and (args.control/'inputs.log').read_bytes()!=(args.candidate/'inputs.log').read_bytes():
        raise RuntimeError('Different chromosome/reference/SV-GFA configuration')
    directories=[args.control if args.legacy_control else args.control/'final',args.candidate/'final']
    for directory in directories:
        if not directory.is_dir(): raise RuntimeError(f'Final output directory does not exist: {directory}')
    inventories=[{p.relative_to(d).as_posix():p for p in d.rglob('*') if p.is_file()} for d in directories]
    control_only=sorted(inventories[0].keys()-inventories[1].keys())
    candidate_only=sorted(inventories[1].keys()-inventories[0].keys())
    ignored=[name for name in control_only if any(fnmatchcase(name,pattern) for pattern in args.allow_control_extra)]
    unmatched=[name for name in control_only if name not in ignored]
    args.output.mkdir(parents=True,exist_ok=False)
    report={'pass':False,'status':'incomplete','threads':args.threads,'files':[],
            'mode':'legacy_control_final' if args.legacy_control else 'paired_benchmark',
            'input_metadata_check':'unavailable_for_legacy_control' if args.legacy_control else 'matching_inputs.log',
            'directories':[str(directory.resolve()) for directory in directories],
            'workflow_resources':resources,'resource_scope':'latest_attempt_only; earlier attempts are not aggregated',
            'control_only':control_only,'candidate_only':candidate_only,
            'ignored_control_outputs':ignored,'allow_control_extra_patterns':args.allow_control_extra,
            'verification_version':'format_checks_v2',
            'binary_difference_policy':'GBZ/ODGI differences require decoded content checks; TBI requires queries against its own VCF; XG and other binary indexes require complete bytes',
            'vcf_timestamp_policy':'ignore fileDate and only trailing bcftools_*Command Date; retain commands, versions and every variant field'}
    report_path=args.output/'report.json'
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if unmatched or candidate_only or not inventories[1]:
        report['status']='inventory_mismatch'
        report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        raise RuntimeError(f'Output inventory mismatch: {len(unmatched)} unapproved control-only files, '
                           f'{len(candidate_only)} candidate-only files; see {report_path}')
    for name in ignored: del inventories[0][name]
    env=dict(os.environ,LC_ALL='C',OMP_NUM_THREADS=str(args.threads))
    env['LD_LIBRARY_PATH']=str(args.vg.resolve().parent.parent/'lib')+':'+env.get('LD_LIBRARY_PATH','')
    tasks=[]
    graphs=[]
    gfas=[]
    binary_graphs=[]
    indexes=[]
    for name in sorted(inventories[0]):
        if name.endswith(('.vg','.xg')): graphs.append(name)
        elif name.endswith(('.gbz','.og')): binary_graphs.append(name)
        elif name.endswith('.tbi'): indexes.append(name)
        elif name.endswith(('.gfa','.gfa.gz')): gfas.append(name)
        else: tasks.append(name)
    records=[]

    def save_record(record):
        records.append(record)
        report['files']=records
        report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        status='PASS' if record['pass'] else record.get('status','FAIL')
        print(status+' '+record['file'],flush=True)

    def error_record(name,check,error):
        result={'file':name,'check':check,'pass':False,'status':'ERROR','error':str(error)}
        if isinstance(error,subprocess.CalledProcessError) and error.stderr:
            stderr=error.stderr
            result['stderr']=stderr.decode(errors='replace') if isinstance(stderr,bytes) else stderr
        return result

    def compare_file(name):
        a,b=map(lambda inv:inv[name],inventories)
        try:
            if name.endswith('.hal'):
                result=subprocess.run(['h5diff','-q',str(a),str(b)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                if result.returncode not in (0,1):
                    raise RuntimeError(f'h5diff failed for {name}: {result.stderr.decode(errors="replace")}')
                return {'file':name,'check':'all_HDF5_datasets_and_attributes','pass':result.returncode==0}
            vcf=name.endswith(('.vcf','.vcf.gz'))
            detail={}
            equal=compare_streams(a,b,name.endswith('.gz'),vcf,detail)
            record={'file':name,'check':'vcf_all_fields_except_run_dates' if vcf else 'complete_bytes_or_decompressed_bytes','pass':equal}
            if detail: record['first_difference']=detail
            return record
        except (OSError,EOFError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            return error_record(name,'complete_content',error)

    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        futures=[pool.submit(compare_file,name) for name in tasks]
        for future in as_completed(futures):
            save_record(future.result())

    def compare_tbi(name):
        record={'file':name,'check':'TBI_queries_against_own_VCF','pass':True}
        if not name.endswith('.vcf.gz.tbi') or any(name[:-4] not in inventory for inventory in inventories):
            return {'file':name,'check':record['check'],'pass':False,
                    'error':'Expected a corresponding .vcf.gz in both output inventories'}
        record['binary_bytes_equal']=compare_streams(inventories[0][name],inventories[1][name])
        for label,inventory in zip(('control','candidate'),inventories):
            try:
                record[label]=check_index(inventory[name[:-4]],inventory[name],args.tabix,args.tmp)
            except (OSError,EOFError,ValueError,subprocess.SubprocessError) as error:
                record['pass']=False
                record[label]={'error':str(error)}
        return record

    # Each index task may run two tabix queries simultaneously.
    with ThreadPoolExecutor(max_workers=max(1,args.threads//2)) as pool:
        futures={pool.submit(compare_tbi,name):name for name in indexes}
        for future in as_completed(futures):
            try:
                record=future.result()
            except (OSError,EOFError,ValueError,subprocess.SubprocessError) as error:
                record=error_record(futures[future],'TBI_queries_against_own_VCF',error)
            save_record(record)

    with tempfile.TemporaryDirectory(dir=args.tmp,prefix='join-verify-') as temporary:
        tmp=Path(temporary)
        for name in gfas:
            print('Checking '+name,flush=True)
            try:
                for i in range(2): canonical_gfa(inventories[i][name],tmp/str(i),args.threads,tmp)
                detail={}
                equal=compare_streams(tmp/'0',tmp/'1',detail=detail)
                record={'file':name,'check':'all_GFA_records_sorted_without_altering_paths','pass':equal}
                if detail: record['first_difference']=detail
                save_record(record)
            except (OSError,EOFError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
                save_record(error_record(name,'all_GFA_records_sorted_without_altering_paths',error))
            finally:
                for i in range(2): (tmp/str(i)).unlink(missing_ok=True)

    # Keep graph loading sequential. The exporter and external sort split the
    # thread budget while streaming one decoded graph into its sorted records.
    export_threads=max(1,args.threads//2)
    sort_threads=max(1,args.threads-export_threads)
    for name in binary_graphs:
        print('Checking '+name,flush=True)
        record={'file':name,'check':'complete_binary_bytes','pass':False}
        try:
            record['binary_bytes_equal']=compare_streams(inventories[0][name],inventories[1][name])
            if record['binary_bytes_equal']:
                record['pass']=True
                save_record(record)
                continue
            is_gbz=name.endswith('.gbz')
            record['check']='decoded_GFA_and_GBWT_metadata_and_tags' if is_gbz else 'decoded_GFA_records'
            with tempfile.TemporaryDirectory(dir=args.tmp,prefix='binary-graph-') as directory:
                scratch=Path(directory)
                outputs=[scratch/'control.gfa',scratch/'candidate.gfa']
                metadata=[]
                for inventory,output in zip(inventories,outputs):
                    source=str(inventory[name].resolve())
                    if is_gbz:
                        command=[str(args.vg.resolve()),'convert','-f','--gbwtgraph-algorithm',
                                 '--no-translation','-t',str(export_threads),source]
                    else:
                        command=[args.odgi,'view','-g','-t',str(export_threads),'-i',source]
                    sorted_export(command,output,sort_threads,scratch,env)
                    if is_gbz:
                        metadata.append(sorted(subprocess.check_output(
                            [str(args.vg.resolve()),'gbwt','-Z','-M','--tags',source],
                            env=env,text=True,encoding='utf-8').splitlines()))
                detail={}
                record['gfa_records_equal']=compare_streams(*outputs,detail=detail)
                if detail: record['first_difference']=detail
                if is_gbz:
                    record['gbwt_metadata_and_tags_equal']=metadata[0]==metadata[1]
                    if metadata[0]!=metadata[1]:
                        record['gbwt_metadata_and_tags']=dict(zip(('control','candidate'),metadata))
                record['pass']=record['gfa_records_equal'] and record.get('gbwt_metadata_and_tags_equal',True)
        except (OSError,EOFError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            record.update({'pass':False,'status':'ERROR','error':str(error)})
        save_record(record)

    for name in graphs:
        print('Checking '+name,flush=True)
        try:
            values=[]
            for index,inventory in enumerate(inventories):
                log=args.output/(str(len(records))+f'.{index}.graph.json')
                with log.open('wb') as output:
                    subprocess.run([str(args.vg.resolve()),'unchop-fingerprint','--threads',str(args.threads),str(inventory[name])],
                                   stdout=output,env=env,check=True)
                values.append(json.loads(log.read_text(encoding='utf-8')))
            equal=values[0]==values[1]
            record={'file':name,'check':'strict_graph_identity','graph_fingerprints_equal':equal,'pass':equal}
            if name.endswith('.xg'):
                record['check']='strict_graph_identity_and_complete_index_bytes'
                record['binary_bytes_equal']=compare_streams(inventories[0][name],inventories[1][name])
                record['pass']=equal and record['binary_bytes_equal']
            save_record(record)
        except (OSError,EOFError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            save_record(error_record(name,'strict_graph_identity',error))
    records.sort(key=lambda row:row['file'])
    passed=sum(record['pass'] for record in records)
    report.update({'status':'complete','files':records,'pass':passed==len(records),
                   'passed':passed,'total':len(records)})
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(('PASS' if report['pass'] else 'FAIL')+f' {passed}/{len(records)}',flush=True)
    raise SystemExit(0 if report['pass'] else 1)

if __name__=='__main__': main()
