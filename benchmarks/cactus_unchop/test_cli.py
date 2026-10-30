#!/usr/bin/env python3
"""Small end-to-end checks of GFA import, pipeline/fused modes and graph fingerprints."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[2]
control = Path(os.environ.get("VG_CONTROL", repo / "bin/vg.control"))
experiment = Path(os.environ.get("VG_EXPERIMENT", repo / "bin/vg.experiment"))
fixtures = {
    "linear": "S\t1\tA\nS\t2\tC\nS\t3\tG\nL\t1\t+\t2\t+\t0M\nL\t2\t+\t3\t+\t0M\nP\ta#1#chr21\t1+,2+,3+\t*\nP\tb#2#chr21\t3-,2-,1-\t*\n",
    "branch": "S\t1\tA\nS\t2\tC\nS\t3\tT\nS\t4\tG\nL\t1\t+\t2\t+\t0M\nL\t1\t+\t3\t+\t0M\nL\t2\t+\t4\t+\t0M\nL\t3\t+\t4\t+\t0M\nP\ta\t1+,2+,4+\t*\nP\tb\t1+,3+,4+\t*\n",
    "inversion": "S\t1\tAC\nS\t2\tG\nS\t3\tTTA\nL\t1\t+\t2\t-\t0M\nL\t2\t-\t3\t+\t0M\nP\ta\t1+,2-,3+\t*\nP\tb\t3-,2+,1-\t*\n",
    "repeat": "S\t1\tA\nS\t2\tC\nS\t3\tG\nL\t1\t+\t2\t+\t0M\nL\t2\t+\t1\t+\t0M\nL\t2\t+\t3\t+\t0M\nP\ta\t1+,2+,1+,2+,3+\t*\n",
    "uncovered_edge": "S\t1\tA\nS\t2\tC\nS\t3\tG\nS\t4\tT\nL\t1\t+\t2\t+\t0M\nL\t3\t+\t4\t+\t0M\nP\ta\t1+,2+\t*\n",
    "w_lines": "H\tVN:Z:1.1\tRS:Z:GRCh38\nS\t1\tAC\nS\t2\tG\nS\t3\tTTA\nL\t1\t+\t2\t+\t0M\nL\t2\t+\t3\t+\t0M\nW\tGRCh38\t0\tchr21\t0\t6\t>1>2>3\nW\tsample\t1\tchr21\t0\t6\t<3<2<1\n",
}
fixtures.update({
    "sparse_ids": "S\t1\tA\nS\t3\tC\nL\t1\t+\t3\t+\t0M\nP\tp\t1+,3+\t*\n",
    "forward_reference": "H\tVN:Z:1.1\nW\tsample\t1\tchr21\t0\t2\t>1>3\nL\t1\t+\t3\t+\t0M\nS\t1\tA\nS\t3\tC\n",
    "mixed_names": "S\t1\tA\nS\tx\tC\nS\t7\tG\nL\t1\t+\tx\t+\t0M\nL\tx\t+\t7\t+\t0M\nP\tp\t1+,x+,7+\t*\n",
    "leading_zero": "S\t01\tA\nS\t3\tC\nL\t01\t+\t3\t+\t0M\nP\tp\t01+,3+\t*\n",
    "large_ids": "S\t536870913\tA\nS\t536870915\tC\nL\t536870913\t+\t536870915\t+\t0M\nP\tp\t536870913+,536870915+\t*\n",
})
def environment(binary, mode):
    env = dict(os.environ, OMP_NUM_THREADS="4")
    for key in ["VG_BENCH_NUMERIC_IDS", "VG_BENCH_FAST_SERIALIZE", "VG_BENCH_PATH_THREADS", "VG_BENCH_XG_MODE"]:
        env.pop(key, None)
    env["LD_LIBRARY_PATH"] = str(binary.resolve().parent.parent / "lib") + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    if mode in ["v4", "v5", "v6"]:
        env["VG_BENCH_NUMERIC_IDS"] = "1"
    if mode in ["v5", "v6"]:
        env["VG_BENCH_FAST_SERIALIZE"] = "1"
    if mode == "v6":
        env["VG_BENCH_PATH_THREADS"] = "4"
    return env
with tempfile.TemporaryDirectory(prefix="vg-unchop-cli-") as temp:
    root = Path(temp)
    for name, text in fixtures.items():
        source = root / (name + ".gfa")
        source.write_text(text)
        reference = None
        for mode in ["control", "v1", "v2", "v3-2", "v3-4", "v4", "v5", "v6"]:
            output = root / (name + "." + mode + ".vg")
            with output.open("wb") as stream:
                if mode in ["control", "v1"]:
                    binary = control if mode == "control" else experiment
                    convert = subprocess.Popen([str(binary), "convert", "-g", "-p", str(source)],
                                               stdout=subprocess.PIPE, env=environment(binary, mode))
                    try:
                        subprocess.run([str(binary), "mod", "-u", "-"], stdin=convert.stdout,
                                       stdout=stream, check=True, env=environment(binary, mode))
                    finally:
                        convert.stdout.close()
                        if convert.wait():
                            raise RuntimeError(f"{name}: converter failed")
                else:
                    command = [str(experiment), "convert", "-g", "-p", "--unchop"]
                    if mode.startswith("v3-"):
                        command += ["--unchop-threads", mode.split("-")[1]]
                    subprocess.run(command + [str(source)], stdout=stream, check=True,
                                   env=environment(experiment, mode))
            fingerprint = json.loads(subprocess.check_output(
                [str(experiment), "unchop-fingerprint", "--threads", "4", str(output)],
                text=True, env=environment(experiment, "v2")))
            if reference is None:
                reference = fingerprint
            elif fingerprint != reference:
                raise RuntimeError(f"{name}: {mode} differs from control")
    for name, text in {"missing_hole": "S\t1\tA\nS\t3\tC\nP\tp\t1+,2+\t*\n",
                       "duplicate": "S\t1\tA\nS\t1\tC\n",
                       "overflow": "S\t9223372036854775808\tA\n"}.items():
        source = root / (name + ".gfa")
        source.write_text(text)
        for binary, mode in [(control, "control"), (experiment, "v4")]:
            result = subprocess.run([str(binary), "convert", "-g", "-p", str(source)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                    env=environment(binary, mode))
            if result.returncode == 0:
                raise RuntimeError(f"{name}: {mode} accepted invalid input")
print("PASS: 11 GFA fixtures x 8 configurations; missing/duplicate/overflow rejection")
