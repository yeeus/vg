#!/usr/bin/env python3
"""Small end-to-end checks of GFA import, pipeline/fused modes and graph fingerprints."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[2]
control = repo / "bin/vg.control"
experiment = repo / "bin/vg.experiment"
fixtures = {
    "linear": "S\t1\tA\nS\t2\tC\nS\t3\tG\nL\t1\t+\t2\t+\t0M\nL\t2\t+\t3\t+\t0M\nP\ta#1#chr21\t1+,2+,3+\t*\nP\tb#2#chr21\t3-,2-,1-\t*\n",
    "branch": "S\t1\tA\nS\t2\tC\nS\t3\tT\nS\t4\tG\nL\t1\t+\t2\t+\t0M\nL\t1\t+\t3\t+\t0M\nL\t2\t+\t4\t+\t0M\nL\t3\t+\t4\t+\t0M\nP\ta\t1+,2+,4+\t*\nP\tb\t1+,3+,4+\t*\n",
    "inversion": "S\t1\tAC\nS\t2\tG\nS\t3\tTTA\nL\t1\t+\t2\t-\t0M\nL\t2\t-\t3\t+\t0M\nP\ta\t1+,2-,3+\t*\nP\tb\t3-,2+,1-\t*\n",
    "repeat": "S\t1\tA\nS\t2\tC\nS\t3\tG\nL\t1\t+\t2\t+\t0M\nL\t2\t+\t1\t+\t0M\nL\t2\t+\t3\t+\t0M\nP\ta\t1+,2+,1+,2+,3+\t*\n",
    "uncovered_edge": "S\t1\tA\nS\t2\tC\nS\t3\tG\nS\t4\tT\nL\t1\t+\t2\t+\t0M\nL\t3\t+\t4\t+\t0M\nP\ta\t1+,2+\t*\n",
    "w_lines": "H\tVN:Z:1.1\tRS:Z:GRCh38\nS\t1\tAC\nS\t2\tG\nS\t3\tTTA\nL\t1\t+\t2\t+\t0M\nL\t2\t+\t3\t+\t0M\nW\tGRCh38\t0\tchr21\t0\t6\t>1>2>3\nW\tsample\t1\tchr21\t0\t6\t<3<2<1\n",
}
with tempfile.TemporaryDirectory(prefix="vg-unchop-cli-") as temp:
    root = Path(temp)
    for name, text in fixtures.items():
        source = root / (name + ".gfa")
        source.write_text(text)
        reference = None
        for mode in ["control", "v1", "v2", "v3-2", "v3-4"]:
            output = root / (name + "." + mode + ".vg")
            with output.open("wb") as stream:
                if mode in ["control", "v1"]:
                    binary = control if mode == "control" else experiment
                    convert = subprocess.Popen([str(binary), "convert", "-g", "-p", str(source)],
                                               stdout=subprocess.PIPE)
                    try:
                        subprocess.run([str(binary), "mod", "-u", "-"], stdin=convert.stdout,
                                       stdout=stream, check=True)
                    finally:
                        convert.stdout.close()
                        if convert.wait():
                            raise RuntimeError(f"{name}: converter failed")
                else:
                    command = [str(experiment), "convert", "-g", "-p", "--unchop"]
                    if mode.startswith("v3-"):
                        command += ["--unchop-threads", mode.split("-")[1]]
                    subprocess.run(command + [str(source)], stdout=stream, check=True)
            fingerprint = json.loads(subprocess.check_output(
                [str(experiment), "unchop-fingerprint", str(output)], text=True))
            if reference is None:
                reference = fingerprint
            elif fingerprint != reference:
                raise RuntimeError(f"{name}: {mode} differs from control")
print("PASS: 6 GFA fixtures x 5 control/pipeline/fused/thread configurations")
