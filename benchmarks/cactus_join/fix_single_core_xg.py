#!/usr/bin/env python3
"""Repair a stopped r3 workflow whose XG job exceeds a one-core budget."""
import argparse
import os
from pathlib import Path
import shutil

from toil.common import Toil

OLD = 'cores=max(options.indexCores, 4),'
NEW = 'cores=options.indexCores,  # Respect single-core index budgets.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path, help='r3 candidate or control runtime directory')
    parser.add_argument('jobstore', help='stopped single-core Toil jobStore')
    args = parser.parse_args()
    module = args.runtime.resolve() / 'override/cactus/refmap/cactus_graphmap_join.py'
    source = module.read_text(encoding='utf-8')
    if source.count(OLD) != 1 and not (OLD not in source and source.count(NEW) == 1):
        raise ValueError('Expected the r3 XG core assignment in ' + str(module))

    store = Toil.resumeJobStore(args.jobstore)
    if store.config.maxCores != 1:
        raise ValueError('This repair is for a saved --maxCores 1 workflow')
    pending = [job for job in store.jobs() if job.has_body() and job.cores > 1]
    unexpected = [job for job in pending if job.jobName != 'make_xg' or job.cores != 4]
    if unexpected:
        raise ValueError('Other oversized jobs require inspection: ' +
                         ', '.join(str(job) for job in unexpected))

    # Update the private source before saved jobs. Each write is atomic and a
    # repeated invocation completes any update interrupted between jobs.
    if OLD in source:
        backup = module.with_name(module.name + '.before-single-core')
        if backup.exists():
            if backup.read_text(encoding='utf-8') != source:
                raise ValueError('An earlier source backup differs: ' + str(backup))
        else:
            shutil.copy2(module, backup)
        changed = source.replace(OLD, NEW, 1)
        compile(changed, str(module), 'exec')
        temporary = module.with_name(module.name + '.single-core.tmp')
        temporary.write_text(changed, encoding='utf-8')
        os.replace(temporary, module)
        print('Updated private XG resource assignment:', module)
    for job in pending:
        identifier = str(job.jobStoreID)
        job.cores = 1
        store.update_job(job)
        saved = store.load_job(identifier)
        if saved.cores != 1:
            raise RuntimeError('XG core update did not persist: ' + identifier)
        print('Updated saved make_xg cores 4 -> 1:', identifier)
    print('PASS single-core XG repair; restart the same workflow with its original parameters')


if __name__ == '__main__':
    main()
