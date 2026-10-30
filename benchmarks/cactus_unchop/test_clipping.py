#!/usr/bin/env python3
"""Compare the exact three-stage vg clip order with the fused CLI on small graphs."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[2]
control = Path(os.environ.get("VG_CONTROL", repo/"bin/vg.control"))
experiment = Path(os.environ.get("VG_EXPERIMENT", repo/"bin/vg.experiment"))

def environment(binary):
    env = dict(os.environ, OMP_NUM_THREADS="1")
    for key in list(env):
        if key.startswith("VG_BENCH_"):
            env.pop(key)
    env["LD_LIBRARY_PATH"] = str(binary.resolve().parent.parent/"lib") + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    return env

with tempfile.TemporaryDirectory(prefix="vg-clip-cli-") as temp:
    root = Path(temp)
    for seed in range(8):
        source = root/"input.gfa"
        source.write_text("S\t1\tAA\nS\t2\t" + "C"*(10+seed) + "\nS\t3\tTT\nS\t4\tG\nS\t5\tA\nS\t6\tC\n"
            "L\t1\t+\t2\t+\t0M\nL\t2\t+\t3\t+\t0M\nL\t1\t+\t3\t+\t0M\n"
            "L\t2\t+\t4\t+\t0M\nL\t5\t+\t6\t-\t0M\n"
            "P\tGRCh38#0#chr21\t1+,2+,3+\t*\nP\tsample#1#chr21\t1+,3+\t*\n"
            "P\tsample#2#chr21\t3-,2-,1-\t*\nP\tstub#1#chr21\t2+,4+\t*\n"
            "P\tCHM13v2#0#chr21\t2+,4+\t*\n")
        raw = root/"input.vg"
        with raw.open("wb") as output:
            subprocess.run([str(control), "convert", "-g", "-p", str(source)],
                           stdout=output, env=environment(control), check=True)
        for fragment in [0, 3]:
            previous = raw
            for index, args in enumerate([["-d", "1"], ["-sS"], ["-D", "5", "-c", "1", "-m", str(fragment)]]):
                target = root/f"control.{index}.vg"
                with target.open("wb") as output:
                    subprocess.run([str(control), "clip", str(previous), "-P", "GRCh38"] + args,
                                   stdout=output, env=environment(control), check=True)
                previous = target
            fused = root/"fused.vg"
            with fused.open("wb") as output:
                subprocess.run([str(experiment), "clip", "--cactus-clip", str(raw), "-P", "GRCh38",
                                "-D", "5", "-c", "1", "-m", str(fragment)],
                               stdout=output, env=environment(experiment), check=True)
            fingerprints = [json.loads(subprocess.check_output([str(experiment), "unchop-fingerprint",
                            "--threads", "4", str(path)], text=True, env=environment(experiment)))
                            for path in [previous, fused]]
            if fingerprints[0] != fingerprints[1]:
                raise RuntimeError(f"fused clipping differs: seed={seed}, min_fragment={fragment}")
            previous = raw
            for index, args in enumerate([["-d", "2", "-P", "GRCh38", "-P", "CHM13v2", "-m", str(fragment)],
                                          ["-d", "1", "-P", "GRCh38", "-P", "CHM13v2"],
                                          ["-sS", "-P", "GRCh38"]]):
                target = root/f"filter.{index}.vg"
                with target.open("wb") as output:
                    subprocess.run([str(control), "clip", str(previous)] + args,
                                   stdout=output, env=environment(control), check=True)
                previous = target
            with fused.open("wb") as output:
                subprocess.run([str(experiment), "clip", "--cactus-filter", str(raw), "-d", "2",
                                "-P", "GRCh38", "-P", "CHM13v2", "-m", str(fragment)],
                               stdout=output, env=environment(experiment), check=True)
            fingerprints = [json.loads(subprocess.check_output([str(experiment), "unchop-fingerprint",
                            "--threads", "4", str(path)], text=True, env=environment(experiment)))
                            for path in [previous, fused]]
            if fingerprints[0] != fingerprints[1]:
                raise RuntimeError(f"fused filtering differs: seed={seed}, min_fragment={fragment}")
print("PASS: 16 clip and 16 filter pipeline comparisons, including reference protection and uncovered topology")
