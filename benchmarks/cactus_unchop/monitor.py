#!/usr/bin/env python3
"""Linux: sample process-tree CPU and summed RSS every 5 s; keep GNU time too."""
import csv
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import threading
import time
import psutil

out = Path(sys.argv[1])
command = sys.argv[2:]
output_name = "result.vg"
if command[:1] == ["--output-name"]:
    output_name, command = command[1], command[2:]
    if Path(output_name).name != output_name:
        raise SystemExit("output-name must be a filename within the results directory")
initial = resource.getrusage(resource.RUSAGE_CHILDREN)
cpu_before = initial.ru_utime + initial.ru_stime
started = time.monotonic()
done = threading.Event()
final = {}
previous_process_cpu = {}
with (out / output_name).open("xb") as graph, (out / "run.log").open("x") as log, \
        (out / "process_cpu_memory.tsv").open("x", newline="") as process_stream:
    process_writer = csv.writer(process_stream, delimiter="\t", lineterminator="\n")
    process_writer.writerow(["elapsed_s", "pid", "command", "used_cores", "rss_gib"])
    child = subprocess.Popen(command, stdout=graph, stderr=log, start_new_session=True)
    root = psutil.Process(child.pid)

    def wait():
        code = child.wait()
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        final.update(code=code, ended=time.monotonic(), cpu=usage.ru_utime + usage.ru_stime - cpu_before,
                     maxrss_gib=usage.ru_maxrss / 1024**2)
        done.set()

    def interrupt(signum, frame):
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    threading.Thread(target=wait, daemon=True).start()
    previous_time, previous_cpu = started, 0.0
    peak_cores = peak_rss = 0.0
    with (out / "cpu_memory.tsv").open("x", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["elapsed_s", "interval_s", "used_cores", "sum_process_rss_gib", "processes"])
        while True:
            done.wait(5)
            now = time.monotonic()
            cpu = rss = count = 0
            if not done.is_set():
                try:
                    processes = [root] + root.children(recursive=True)
                except psutil.Error:
                    processes = []
                for process in processes:
                    try:
                        t = process.cpu_times()
                        cpu += t.user + t.system + t.children_user + t.children_system
                        process_rss = process.memory_info().rss
                        rss += process_rss
                        count += 1
                        key = (process.pid, process.create_time())
                        own_cpu = t.user + t.system
                        old_cpu = previous_process_cpu.get(key, 0.0)
                        process_writer.writerow([f"{now-started:.3f}", process.pid,
                            " ".join(process.cmdline()), f"{max(0, own_cpu-old_cpu)/(now-previous_time):.3f}",
                            f"{process_rss/1024**3:.3f}"])
                        previous_process_cpu[key] = own_cpu
                    except psutil.Error:
                        pass
            else:
                cpu = final["cpu"]
            cpu = max(previous_cpu, cpu)
            interval = now - previous_time
            cores = (cpu - previous_cpu) / interval
            peak_cores = max(peak_cores, cores)
            peak_rss = max(peak_rss, rss / 1024**3)
            writer.writerow([f"{now-started:.3f}", f"{interval:.3f}", f"{cores:.3f}",
                             f"{rss/1024**3:.3f}", count])
            stream.flush()
            process_stream.flush()
            previous_time, previous_cpu = now, cpu
            if done.is_set():
                break
elapsed = final["ended"] - started
code = final["code"] if final["code"] >= 0 else 128 - final["code"]
summary = dict(exit_code=code, wall_seconds=elapsed, cpu_seconds=final["cpu"],
               mean_cores=final["cpu"]/elapsed, sampled_peak_cores=peak_cores,
               largest_process_maxrss_gib=final["maxrss_gib"],
               sampled_peak_sum_process_rss_gib=peak_rss,
               cpu_accounting="normal" if code == 0 else "lower_bound")
(out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary))
sys.exit(code)
