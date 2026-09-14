import json
import math
import subprocess
import os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

def run_chunk(chunk_idx):
    cmd = [
        "python3", "app.py",
        "--file", f"chunk_{chunk_idx}.json",
        "--out", f"chunk_out_{chunk_idx}.jsonl"
    ]
    env = os.environ.copy()
    env["N_GPU_LAYERS"] = "1"
    print(f"[Worker {chunk_idx}] Starting...", flush=True)
    subprocess.run(cmd, cwd="llm_hosting", env=env, check=True)
    print(f"[Worker {chunk_idx}] Finished!", flush=True)
    return f"llm_hosting/chunk_out_{chunk_idx}.jsonl"

def main():
    with open("cleaned_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    total = len(data)
    num_workers = 8
    chunk_size = math.ceil(total / num_workers)
    
    print(f"Splitting {total} records across {num_workers} parallel workers...", flush=True)
    for i in range(num_workers):
        chunk = data[i * chunk_size : (i + 1) * chunk_size]
        with open(f"llm_hosting/chunk_{i}.json", "w", encoding="utf-8") as f:
            json.dump(chunk, f)

    print("Launching parallel workers...", flush=True)
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        out_files = list(executor.map(run_chunk, range(num_workers)))

    print("Merging outputs into llm_hosting/full_standardized.jsonl...", flush=True)
    with open("llm_hosting/full_standardized.jsonl", "w", encoding="utf-8") as outfile:
        for fname in out_files:
            p = Path(fname)
            if p.exists():
                with open(p, "r", encoding="utf-8") as infile:
                    for line in infile:
                        outfile.write(line)
                p.unlink()
            chunk_in = Path(fname.replace("chunk_out_", "chunk_").replace(".jsonl", ".json"))
            if chunk_in.exists():
                chunk_in.unlink()

    print("All workers finished and merged successfully!", flush=True)

if __name__ == "__main__":
    main()
