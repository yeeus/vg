#!/usr/bin/env python3
"""Create a private, narrowly scoped Cactus 7f34bb7 join override."""
from pathlib import Path
import argparse

CACTUS = '7f34bb7a65af5816835ef79b7ae5e2f3c277b305'

def replace_once(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError(f'Cactus source differs at {old[:100]!r}; shared installation was not changed')
    return source.replace(old,new,1)

def patch(source):
    # Full GFA export now checks the same split-at-# sample criterion while
    # the graph is already loaded. Clip and non-GFAffix paths keep the old check.
    source = replace_once(source,
        "    # everything below selects on --reference[0]",
        "    join_xml_node = findRequiredNode(config.xmlRoot, \"graphmap_join\")\n"
        "    checking_at_export = phase == 'full' and getOptionalAttrib(join_xml_node, \"gfaffix\", typeFn=bool, default=True)\n\n"
        "    # everything below selects on --reference[0]")
    source = replace_once(source,
        "    if options.reference:\n        graph_samples = sorted(set(",
        "    if options.reference and not checking_at_export:\n        graph_samples = sorted(set(")
    source = replace_once(source,
        '    join_xml_node = findRequiredNode(config.xmlRoot, "graphmap_join")\n    graph_event =',
        '    graph_event =')
    source = replace_once(source,
        "        cactus_call(parameters=['vg', 'convert', '-f', vg_path], outfile=gfa_in_path, job_memory=job.memory)",
        "        export_cmd = ['vg', 'convert', '-f', vg_path]\n"
        "        if options.reference:\n            export_cmd += ['--require-sample', options.reference[0]]\n"
        "        cactus_call(parameters=export_cmd, outfile=gfa_in_path, job_memory=job.memory)")
    source = replace_once(source,
        "        conv_cmd = [['vg', 'convert', '-g', '-p', gfa_out_path]]\n"
        "        # GFAFfix doesn't unchop, so we do that in vg after\n"
        "        conv_cmd.append(['vg', 'mod', '-u', '-'])",
        "        conv_cmd = ['vg', 'convert', '-g', '-p', '--unchop', gfa_out_path]")
    source = replace_once(source,
        "    clip_stderr = cactus_call(parameters=cmd, outfile=clipped_path, job_memory=job.memory,",
        "    # Fuse only the exact stages enabled by this chromosome workflow.\n"
        "    if phase == 'full' and options.reference and cmd[1:] == [\n"
        "            ['vg', 'mod', '-X', '1024', '-'],\n"
        "            ['vg', 'paths', '-x', '-', '-n', '-Q', options.reference[0], '-t', '1'],\n"
        "            ['vg', 'clip', '-d', '1', '-', '-P', options.reference[0]],\n"
        "            ['vg', 'ids', '-s', '-']]:\n"
        "        cmd = [cmd[0], ['vg', 'clip', '--cactus-full', '-', '-P', options.reference[0]]]\n"
        "    elif phase == 'clip' and options.reference and len(cmd) == 4 and cmd[1:3] == [\n"
        "            ['vg', 'clip', '-d', '1', '-', '-P', options.reference[0]],\n"
        "            ['vg', 'clip', '-sS', '-', '-P', options.reference[0]]]:\n"
        "        cmd = [cmd[0], cmd[3][:2] + ['--cactus-clip'] + cmd[3][2:]]\n"
        "    clip_stderr = cactus_call(parameters=cmd, outfile=clipped_path, job_memory=job.memory,")
    source = replace_once(source,
        "    cactus_call(parameters=clip_cmd, outfile=clipped_path, job_memory=job.memory)",
        "    if min_fragment and options.reference and isinstance(clip_cmd[0], list) and len(clip_cmd) == 3:\n"
        "        expected_clean = ['vg', 'clip', '-d', '1', '-']\n"
        "        for ref in options.reference:\n            expected_clean += ['-P', ref]\n"
        "        if clip_cmd[1:] == [expected_clean, ['vg', 'clip', '-sS', '-', '-P', options.reference[0]]]:\n"
        "            clip_cmd = clip_cmd[0][:2] + ['--cactus-filter'] + clip_cmd[0][2:]\n"
        "    cactus_call(parameters=clip_cmd, outfile=clipped_path, job_memory=job.memory)")
    compile(source,'cactus_graphmap_join.py','exec')
    return source

def checkpoint_patch(source):
    source = 'from cactus.refmap.join_checkpoint import JoinStages\nimport xml.etree.ElementTree as join_ET\n' + source
    anchor = "    clipped_path = vg_path + '.clip'\n"
    # clip_vg and vg_clip_vg each have this anchor; their input IDs distinguish them.
    if source.count(anchor) != 2:
        raise RuntimeError('Expected exactly two clipping functions')
    setup = ("    stages = JoinStages(cactus_call, work_dir, dict(input_id=str(vg_id),\n"
             "        phase=JOIN_PHASE, reference=options.reference, clip=options.clip, filter=options.filter,\n"
             "        cores=job.cores, config=join_ET.tostring(config.xmlRoot, encoding='unicode')))\n")
    start = source.index('def vg_clip_vg(')
    before, after = source[:start], source[start:]
    before = replace_once(before, anchor, anchor + setup.replace('JOIN_PHASE', 'phase'))
    after = replace_once(after, anchor, anchor + setup.replace('JOIN_PHASE', "'filter'"))
    source = before + after
    for expression in (
            "cactus_call(parameters=['vg', 'convert', '-f', vg_path], outfile=gfa_in_path, job_memory=job.memory)",
            "cactus_call(parameters=export_cmd, outfile=gfa_in_path, job_memory=job.memory)"):
        if expression in source:
            source = replace_once(source, expression, expression.replace('cactus_call(', "stages.run('01-export', ").replace('parameters=', 'artifact=gfa_in_path, parameters=', 1))
    source = replace_once(source,
        'cactus_call(parameters=fix_cmd, job_memory=job.memory)',
        "stages.run('02-gfaffix', fix_cmd, gfa_out_path, job_memory=job.memory)")
    source = replace_once(source,
        'cactus_call(parameters=conv_cmd, outfile=normalized_path)',
        "stages.pipeline('03-unchop', conv_cmd, normalized_path)")
    source = replace_once(source,
        'clip_stderr = cactus_call(parameters=cmd, outfile=clipped_path, job_memory=job.memory,',
        "clip_stderr = stages.pipeline('04-clip', parameters=cmd, outfile=clipped_path, job_memory=job.memory,")
    source = replace_once(source,
        'cactus_call(parameters=clip_cmd, outfile=clipped_path, job_memory=job.memory)',
        "stages.pipeline('05-filter', parameters=clip_cmd, outfile=clipped_path, job_memory=job.memory)")
    compile(source, 'cactus_graphmap_join.py', 'exec')
    return source

def main():
    p=argparse.ArgumentParser()
    p.add_argument('directory',type=Path)
    p.add_argument('--mode', choices=['control', 'candidate'], default='candidate')
    args=p.parse_args()
    from cactus.shared.version import cactus_commit
    from cactus.refmap import cactus_graphmap_join
    if cactus_commit!=CACTUS:
        raise RuntimeError(f'Expected Cactus {CACTUS}; found {cactus_commit}')
    original=Path(cactus_graphmap_join.__file__)
    directory=args.directory.resolve()
    target=directory/'cactus/refmap/cactus_graphmap_join.py'
    target.parent.mkdir(parents=True,exist_ok=True)
    source = original.read_text(encoding='utf-8')
    if args.mode == 'candidate':
        source = patch(source)
    target.write_text(checkpoint_patch(source),encoding='utf-8')
    target.with_name('join_checkpoint.py').write_text(
        Path(__file__).with_name('checkpoint.py').read_text(encoding='utf-8'), encoding='utf-8')
    (directory/'sitecustomize.py').write_text(
        'from pathlib import Path\nimport cactus.refmap\n'
        'cactus.refmap.__path__.insert(0, str(Path(__file__).resolve().parent / "cactus/refmap"))\n',encoding='utf-8')
    print(f'Private override: {target}; original preserved: {original}')

if __name__=='__main__': main()
