#!/usr/bin/env python3
"""Exercise the patched real function bodies with a command-capture boundary."""
import argparse
import ast
import os
from pathlib import Path, PurePosixPath
import tempfile
from types import SimpleNamespace as NS
from prepare import patch, checkpoint_patch
from run import render

def main():
    p=argparse.ArgumentParser()
    p.add_argument('original_cactus_module',type=Path)
    p.add_argument('original_join_script',type=Path)
    args=p.parse_args()
    original=args.original_cactus_module.read_text(encoding='utf-8')
    changed=patch(original)
    old,new=ast.parse(original),ast.parse(changed)
    old_functions={f.name:ast.dump(f) for f in old.body if isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef))}
    new_functions={f.name:ast.dump(f) for f in new.body if isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef))}
    assert {k for k in old_functions if old_functions[k]!=new_functions[k]}=={'clip_vg','vg_clip_vg'}
    for source in (original,changed):
        staged=ast.parse(checkpoint_patch(source))
        functions={f.name:ast.dump(f) for f in staged.body if isinstance(f,ast.FunctionDef)}
        assert {k for k in old_functions if old_functions[k]!=functions[k]}=={'clip_vg','vg_clip_vg'}
    join=dict(gfaffix=True,maxNodeLength=1024,pathNormalize=True,removeStubs=True,clipNonMinigraph=True,
              clipInversionMin=100000,clipFlank=50000,clipFlankThreshold=-1.0,delEdgeFilter=10000000,
              clipContext=1000,minFilterFragment=1000)
    config=NS(xmlRoot={'graphmap_join':join,'graphmap':dict(assemblyName='_MINIGRAPH_',collapse='none')})
    options=NS(reference=['GRCh38','CHM13v2','CN1v1'],clip=10000,filter=132)
    captures=[]
    def call(**kwargs):
        captures.append(kwargs['parameters'])
        if kwargs.get('check_output'): return 'GRCh38#0#chr21\nsample#1#chr21\n'
    with tempfile.TemporaryDirectory() as temporary:
        functions={}
        for name,stop,return_name in [('clip_vg','clip_stderr','cmd'),('vg_clip_vg',None,'clip_cmd')]:
            f=next(f for f in new.body if isinstance(f,ast.FunctionDef) and f.name==name)
            body=[]
            for statement in f.body:
                if stop and isinstance(statement,ast.Assign) and isinstance(statement.targets[0],ast.Name) and statement.targets[0].id==stop: break
                if not stop and isinstance(statement,ast.Expr) and isinstance(statement.value,ast.Call) and isinstance(statement.value.func,ast.Name) and statement.value.func.id=='cactus_call': break
                body.append(statement)
            f.body=body+[ast.Return(ast.Name(return_name,ast.Load()))]
            module=ast.fix_missing_locations(ast.Module(body=[f],type_ignores=[]))
            namespace=dict(os=os,cactus_call=call,findRequiredNode=lambda root,name:root[name],
                           getOptionalAttrib=lambda node,name,typeFn=None,default=None:node.get(name,default))
            exec(compile(module,'real_patched_body','exec'),namespace)
            functions[name]=namespace[name]
        job=NS(memory=100,cores=1,fileStore=NS(getLocalTempDir=lambda:temporary,readGlobalFile=lambda *a:None))
        cmd=functions['clip_vg'](job,options,config,'chr21.vg',0,'full')
        assert cmd[1:]==[['vg','clip','--cactus-full','-','-P','GRCh38']],cmd
        assert ['--require-sample','GRCh38']==captures[0][-2:]
        assert not any(c[:2]==['vg','paths'] for c in captures)
        assert any(c[:5]==['vg','convert','-g','-p','--unchop'] for c in captures)
        captures.clear()
        cmd=functions['clip_vg'](job,options,config,'chr21.vg',0,'clip')
        assert captures[0][:2]==['vg','paths']
        assert cmd[1]==['vg','clip','--cactus-clip','-','-D','10000000','-P','GRCh38','-c','1000','-m','1000'],cmd
        cmd=functions['vg_clip_vg'](job,options,config,'chr21.vg',0)
        assert cmd==['vg','clip','--cactus-filter',os.path.join(temporary,'chr21.vg'),'-d','132',
                     '-P','GRCh38','-P','CHM13v2','-P','CN1v1','-m','1000'],cmd
        # A nonmatching thread/configuration keeps the upstream pipeline.
        job.cores=2
        cmd=functions['clip_vg'](job,options,config,'chr21.vg',0,'full')
        assert len(cmd)==5 and cmd[-1]==['vg','ids','-s','-']
    script=args.original_join_script.read_text(encoding='utf-8')
    for mode in ('control','candidate'):
        result,extra=render(script,PurePosixPath('/tools'),mode,PurePosixPath('/results')/mode,64)
        assert '--filter 132' in result and '--gfa clip full --gbz clip full filter --xg clip --odgi clip' in result
        assert './align/${CHROM}.vg' in result and './align/${CHROM}.hal' in result
        assert '--outDir /results/'+mode+'/final' in result
        assert '--retryCount=0' in extra
        assert 'CACTUS_JOIN_STAGE_CACHE' in extra and 'PYTHONPATH' in extra
    print('PASS source scope; exact full/clip/filter command order; fused reference/export check; fallback; original script preservation')

if __name__=='__main__': main()
