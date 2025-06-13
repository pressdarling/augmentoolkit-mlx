#!/usr/bin/env python3
import subprocess
import yaml
import json
from pathlib import Path

def main():
    cfg = yaml.safe_load(Path("config/at_config.yaml").read_text())
    input_dir = cfg.get("INPUT_DIR", "./docs")
    raw_output = Path(cfg.get("OUTPUT_FILE", "data/raw.jsonl"))
    raw_output.parent.mkdir(parents=True, exist_ok=True)

    # Run Augmentoolkit CLI
    subprocess.run([
        "python", "-m", "augmentoolkit.cli.generate",
        "--config", "config/at_config.yaml",
        "--output", str(raw_output)
    ], check=True)

    # Convert to MLX chat JSONL
    train_file = raw_output.parent / "train.jsonl"
    with open(raw_output) as fin, open(train_file, "w") as fout:
        for line in fin:
            data = json.loads(line)
            messages = []
            if "system" in data:
                messages.append({"role": "system", "content": data["system"]})
            messages.append({"role": "user", "content": data.get("instruction", data.get("question", ""))})
            messages.append({"role": "assistant", "content": data.get("response", data.get("answer", ""))})
            fout.write(json.dumps({"messages": messages}) + "\n")
    print(f"Generated MLX dataset at {train_file}")

if __name__ == "__main__":
    main()
