"""Generate synthetic data with Augmentoolkit CLI, outputs ./data/train.jsonl"""
import os
import subprocess

def main():
    os.makedirs("data", exist_ok=True)
    cmd = [
        "python",
        "libs/augmentoolkit/augmentoolkit/cli.py",
        "--config", "config/at_config.yaml",
        "--output", "data/train.jsonl"
    ]
    print("Would run:", " ".join(cmd))
    # subprocess.run(cmd)  # Uncomment when augmentoolkit is installed

if __name__ == "__main__":
    main()
