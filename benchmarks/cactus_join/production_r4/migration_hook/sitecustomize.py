"""Relocated promises and resource arguments for ready-to-run join jobs only."""
import argparse
import inspect
import json
import os
from pathlib import Path
import runpy

if os.environ.get('R4_JOIN_MIGRATION_CONFIG'):
    config = json.loads(Path(os.environ['R4_JOIN_MIGRATION_CONFIG']).read_text(encoding='utf-8'))
    if config.get('runtime'):
        runpy.run_path(str(Path(config['runtime']) / 'override/sitecustomize.py'))
    # Reuse the user's existing Promise relocation hook without changing it.
    runpy.run_path(config['path_hook'])
    from toil.job import JobFunctionWrappingJob

    def rehome(value):
        if isinstance(value, str):
            for scheme in ('', 'file:', 'file://'):
                old = scheme + config['old_root']
                if value == old or value.startswith(old + '/'):
                    return scheme + config['new_root'] + value[len(old):]
            return value
        if isinstance(value, argparse.Namespace):
            for key, item in vars(value).items():
                setattr(value, key, rehome(item))
            return value
        if type(value) is list:
            return [rehome(item) for item in value]
        if type(value) is tuple:
            return tuple(rehome(item) for item in value)
        if type(value) is dict:
            return {key: rehome(item) for key, item in value.items()}
        return value

    saved_run = JobFunctionWrappingJob.run

    def _run_migrated_join(self, file_store):
        function = self._getUserFunction()
        if function.__module__ != config['join_module']:
            return saved_run(self, file_store)
        bound = inspect.signature(function).bind(self, *self._args, **self._kwargs)
        for key, value in list(bound.arguments.items()):
            bound.arguments[key] = rehome(value)
        options = bound.arguments.get('options')
        if isinstance(options, argparse.Namespace):
            options.defaultCores = 1
            options.maxCores = config['cores']
            options.indexCores = config['index_cores']
            options.maxMemory = options.indexMemory = config['memory_bytes']
        for key in ('index_mem', 'max_mem'):
            if key in bound.arguments:
                bound.arguments[key] = config['memory_bytes']
        return function(*bound.args, **bound.kwargs)

    JobFunctionWrappingJob.run = _run_migrated_join
