"""Map this relocated Cactus jobStore when Python leaders/workers resolve promises."""

import os
import sys


_old = os.environ.get("CACTUS_RESTART_OLD_JOBSTORE")
_new = os.environ.get("CACTUS_RESTART_NEW_JOBSTORE")

if _old and _new:
    from toil.job import Promise

    _saved_resolve = Promise._resolve.__func__
    _reported = False

    def _resolve_relocated(cls, locator, file_id):
        global _reported
        if locator in (_old, "file:" + _old):
            locator = "file:" + _new
            if not _reported:
                print(
                    f"[cactus-restart] jobStore mapping: {_old} -> {_new}",
                    file=sys.stderr,
                    flush=True,
                )
                _reported = True
        return _saved_resolve(cls, locator, file_id)

    Promise._resolve = classmethod(_resolve_relocated)
