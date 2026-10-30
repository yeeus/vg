#!/usr/bin/env python3
"""Require successful runs and byte-identical complete XG indexes; stream reads."""
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
modes = sys.argv[2:] or ["xg-control", "xg-stream", "xg-compact"]
summaries = {m: json.loads((root/m/"summary.json").read_text()) for m in modes}
for mode, summary in summaries.items():
    if summary["exit_code"] != 0:
        raise SystemExit(f"FAIL {mode}: exit {summary['exit_code']}")
reference = root/modes[0]/"result.xg"
if reference.stat().st_size == 0:
    raise SystemExit("FAIL: empty reference XG")
for mode in modes[1:]:
    candidate = root/mode/"result.xg"
    if candidate.stat().st_size != reference.stat().st_size:
        raise SystemExit(f"FAIL {mode}: XG byte length differs; keep files for investigation")
    with reference.open("rb") as left, candidate.open("rb") as right:
        while True:
            block = left.read(4 * 1024**2)
            if block != right.read(4 * 1024**2):
                raise SystemExit(f"FAIL {mode}: XG bytes differ; keep files for investigation")
            if not block:
                break
print(f"PASS: all {len(modes)} complete XG indexes are byte-identical")
print("mode\twall_h\tcpu_h\tmean_cores\tlargest_process_RSS_GiB\tsampled_tree_RSS_GiB")
for mode, s in summaries.items():
    print(f"{mode}\t{s['wall_seconds']/3600:.3f}\t{s['cpu_seconds']/3600:.3f}\t"
          f"{s['mean_cores']:.3f}\t{s['largest_process_maxrss_gib']:.3f}\t"
          f"{s['sampled_peak_sum_process_rss_gib']:.3f}")
