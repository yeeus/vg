"""Keep completed join stages outside Toil's disposable worker directories."""
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil


class JoinStages:
    def __init__(self, call, work_dir, identity):
        self.call = call
        self.work_dir = str(work_dir)
        identity['toolchain'] = os.environ['CACTUS_JOIN_STAGE_TAG']
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        self.directory = Path(os.environ['CACTUS_JOIN_STAGE_CACHE']) / key
        self.directory.mkdir(parents=True, exist_ok=True)
        self.identity = identity

    def run(self, label, parameters, artifact, **kwargs):
        artifact = Path(artifact)
        data = self.directory / (label + artifact.suffix)
        marker = self.directory / (label + '.json')
        commands = parameters if isinstance(parameters[0], list) else [parameters]
        command = [[str(argument).replace(self.work_dir, '<work>') for argument in part]
                   for part in commands]
        if marker.exists() and data.exists():
            saved = json.loads(marker.read_text(encoding='utf-8'))
            if (saved['identity'] == self.identity and saved['command'] == command
                    and saved['size'] == data.stat().st_size):
                # Copies prevent later in-place graph edits from changing the cache.
                shutil.copyfile(data, artifact)
                logging.getLogger(__name__).info('JOIN_STAGE reuse %s: %s', label, data)
                return saved['stderr'] if kwargs.get('returnStdErr') else None
        logging.getLogger(__name__).info('JOIN_STAGE run %s', label)
        capture = dict(kwargs, returnStdErr=True)
        stderr = self.call(parameters=parameters, **capture) or ''
        if not artifact.exists() or artifact.stat().st_size == 0:
            raise RuntimeError('Stage produced no nonempty output: ' + label)
        pending = data.with_name(data.name + '.pending')
        shutil.copyfile(artifact, pending)
        os.replace(pending, data)
        record = dict(identity=self.identity, command=command,
                      size=data.stat().st_size, stderr=stderr)
        temporary_marker = marker.with_suffix('.pending')
        temporary_marker.write_text(json.dumps(record, sort_keys=True) + '\n', encoding='utf-8')
        os.replace(temporary_marker, marker)
        logging.getLogger(__name__).info('JOIN_STAGE saved %s: %s', label, data)
        return stderr if kwargs.get('returnStdErr') else None

    def pipeline(self, label, parameters, outfile, **kwargs):
        """Finish and save each graph before starting its downstream reader."""
        commands = parameters if isinstance(parameters[0], list) else [parameters]
        previous = None
        stderr = []
        for number, command in enumerate(commands):
            command = [previous if argument == '-' and previous else argument
                       for argument in command]
            target = str(outfile) if number == len(commands) - 1 else str(outfile) + '.stage' + str(number)
            stage_kwargs = dict(kwargs, outfile=target, returnStdErr=True)
            stderr.append(self.run(label + '-' + str(number), command, target, **stage_kwargs))
            previous = target
        return '\n'.join(stderr) if kwargs.get('returnStdErr') else None
