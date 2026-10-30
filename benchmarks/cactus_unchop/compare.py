#!/usr/bin/env python3
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
modes = sys.argv[2:] or ["control", "v1", "v2", "v3"]
summaries = {mode: json.loads((root/mode/"summary.json").read_text()) for mode in modes}
for mode, summary in summaries.items():
    if summary["exit_code"] != 0:
        raise SystemExit(f"FAIL {mode}: run exited {summary['exit_code']}")
fingerprints = {mode: json.loads((root/mode/"fingerprint.json").read_text()) for mode in modes}
control = fingerprints[modes[0]]
for mode in modes[1:]:
    if fingerprints[mode] != control:
        different = [key for key in control if fingerprints[mode].get(key) != control[key]]
        raise SystemExit(f"FAIL {mode}: " + ", ".join(different))
print(f"PASS: all {len(modes)} graphs match in node IDs/sequences, complete topology, path metadata and ordered steps.")
print("mode\twall_h\tcpu_h\tmean_cores\tlargest_process_RSS_GiB\tsampled_tree_RSS_GiB")
for mode in modes:
    s = summaries[mode]
    print(f"{mode}\t{s['wall_seconds']/3600:.3f}\t{s['cpu_seconds']/3600:.3f}\t"
          f"{s['mean_cores']:.3f}\t{s['largest_process_maxrss_gib']:.3f}\t"
          f"{s['sampled_peak_sum_process_rss_gib']:.3f}")
