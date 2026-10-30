#!/usr/bin/env python3
"""Run an unchanged user join script with isolated outputs and runtime overlay."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

def render(source, prefix, mode, out, threads):
    replacements={
        './js.join':str(out/'js.join'),
        './logs':str(out/'logs'),
        '$PWD/toil_work':str(out/'toil_work'),
        './toil_work':str(out/'toil_work'),
        '--outDir ./final':'--outDir '+shlex.quote(str(out/'final')),
    }
    # These are actual paths in a shell script, so reject paths that would
    # require changing its existing quoting style.
    if any(c in str(out) for c in " \t\n\r'\"$`\\"):
        raise ValueError('Use an output path without shell metacharacters or spaces')
    for old,new in replacements.items():
        if old not in source: raise ValueError(f'Expected original 04.join.sh anchor: {old}')
        source=source.replace(old,new)
    runtime=prefix/mode
    envlines=[
        'unset VG_BENCH_NUMERIC_IDS VG_BENCH_FAST_SERIALIZE VG_BENCH_PATH_THREADS VG_BENCH_XG_MODE VG_BENCH_COMPACT_MEMBERSHIP',
        'export PATH='+shlex.quote(str(runtime/'bin'))+':"$PATH"',
        'export LD_LIBRARY_PATH='+shlex.quote(str(runtime/'lib'))+':"${LD_LIBRARY_PATH:-}"',
        'export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:?}"',
    ]
    extra=['--retryCount=0','--stopOnFirstFailure=True','--setEnv','OMP_NUM_THREADS']
    if mode=='candidate':
        envlines.append('export PYTHONPATH='+shlex.quote(str(runtime/'override'))+':"${PYTHONPATH:-}"')
        envlines += ['export VG_BENCH_NUMERIC_IDS=1 VG_BENCH_FAST_SERIALIZE=1 VG_BENCH_XG_MODE=compact VG_BENCH_COMPACT_MEMBERSHIP=1',
                     f'export VG_BENCH_PATH_THREADS={min(4,threads)}', 'export VG_BENCH_PHASES=1']
        for name in ['PYTHONPATH','VG_BENCH_NUMERIC_IDS','VG_BENCH_FAST_SERIALIZE','VG_BENCH_XG_MODE','VG_BENCH_COMPACT_MEMBERSHIP','VG_BENCH_PATH_THREADS','VG_BENCH_PHASES']:
            extra += ['--setEnv',name]
    envlines += ['command -v vg clip-vg gfaffix > '+shlex.quote(str(out/'tools.log')),
                 'declare -p CHROM REFERENCES GFA > '+shlex.quote(str(out/'inputs.log')),
                 'stat --printf \'%n\\t%s\\t%Y\\n\' "./align/${CHROM}.vg" "./align/${CHROM}.hal" "$GFA" >> '+shlex.quote(str(out/'inputs.log')),
                 'vg version >> '+shlex.quote(str(out/'tools.log'))+' 2>&1',
                 'ldd "$(command -v vg)" >> '+shlex.quote(str(out/'tools.log'))+' 2>&1 || true']
    expected=repr(str(runtime/'override/cactus/refmap/cactus_graphmap_join.py')) if mode=='candidate' else 'str(Path(cactus.__file__).resolve().parent / "refmap/cactus_graphmap_join.py")'
    check=('from pathlib import Path; import cactus; from cactus.refmap import cactus_graphmap_join as j; '
           'from cactus.shared.version import cactus_commit; '
           'assert cactus_commit == "7f34bb7a65af5816835ef79b7ae5e2f3c277b305", cactus_commit; '
           f'assert Path(j.__file__).resolve() == Path({expected}).resolve(), j.__file__; '
           'print("PASS join module:", j.__file__)')
    envlines.append('python3 -c '+shlex.quote(check)+' >> '+shlex.quote(str(out/'tools.log')))
    anchor='source ./cactus.config.sh'
    if source.count(anchor)!=1: raise ValueError('Expected one source ./cactus.config.sh')
    source=source.replace(anchor,anchor+'\n'+'\n'.join(envlines),1)
    # The original script passes $@ to Toil, after all scientific parameters.
    return source,extra

def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['control','candidate'])
    p.add_argument('prefix',type=Path)
    p.add_argument('out',type=Path)
    p.add_argument('script',type=Path)
    args=p.parse_args()
    threads=int(os.environ['SLURM_CPUS_PER_TASK'])
    if threads<1 or int(os.environ['SLURM_MEM_PER_NODE'])<1: raise ValueError('Need positive Slurm CPU/memory allocation')
    out=args.out.resolve()
    source,extra=render(args.script.read_text(encoding='utf-8'),args.prefix.resolve(),args.mode,out,threads)
    out.mkdir(parents=True,exist_ok=False)
    target=out/'run.join.sh'
    target.write_text(source,encoding='utf-8')
    # Monitor the entire workflow, including the unchanged GNU time command.
    monitor=Path(__file__).resolve().parents[1]/'cactus_unchop/monitor.py'
    result=subprocess.run([sys.executable,str(monitor),str(out),'--output-name','stdout.log','bash',str(target),*extra])
    (out/'run.json').write_text(json.dumps({'mode':args.mode,'cwd':str(Path.cwd()),'script':str(args.script.resolve()),
                                         'prefix':str(args.prefix.resolve()),'exit_code':result.returncode},indent=2)+'\n',encoding='utf-8')
    raise SystemExit(result.returncode)

if __name__=='__main__': main()
