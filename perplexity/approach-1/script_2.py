# Create a simpler visualization
import pandas as pd

# Define the format conversion mapping
format_conversion = pd.DataFrame({
    "Augmentoolkit Format (ShareGPT)": ["{'from': 'system', 'value': '...'}", 
                                      "{'from': 'human', 'value': '...'}",
                                      "{'from': 'gpt', 'value': '...'}"],
    "MLX Format (Messages)": ["{'role': 'system', 'content': '...'}", 
                            "{'role': 'user', 'content': '...'}",
                            "{'role': 'assistant', 'content': '...'}"]
})

# Define the repository structure
repo_structure = pd.DataFrame({
    "Component": ["Root Directory", "Submodules", "Submodules", "Submodules", 
                 "Custom Directory", "Custom Directory", "Custom Directory", "Custom Directory"],
    "Path": ["augmentoolkit-mlx-pipeline/", 
            "augmentoolkit/", 
            "mlx-tuning-fork/", 
            "simple-guide-mlx/",
            "converters/", 
            "pipeline/", 
            "configs/", 
            "examples/"],
    "Description": ["Main project repository",
                   "Data generation with Augmentoolkit",
                   "Enhanced MLX training framework",
                   "Simple MLX fine-tuning examples",
                   "Format conversion utilities",
                   "End-to-end pipeline orchestration",
                   "Unified configuration templates",
                   "Working examples and tutorials"]
})

# Define the core files needed
core_files = pd.DataFrame({
    "File": ["pipeline.py", 
            "converters/augmentoolkit_to_mlx.py",
            "configs/pipeline.yaml",
            "configs/augmentoolkit.yaml",
            "configs/mlx_training.yaml"],
    "Purpose": ["Main orchestration script",
               "Format converter between Augmentoolkit and MLX",
               "Unified pipeline configuration",
               "Augmentoolkit-specific configuration",
               "MLX training configuration"]
})

print("=== FORMAT CONVERSION MAPPING ===")
print(format_conversion.to_string(index=False))

print("\n\n=== REPOSITORY STRUCTURE ===")
print(repo_structure.to_string(index=False))

print("\n\n=== CORE FILES NEEDED ===")
print(core_files.to_string(index=False))

# Create data flow diagram
data_flow = [
    "Raw text documents (.txt, .md, .pdf)",
    "↓ [Augmentoolkit]",
    "ShareGPT format (.jsonl)",
    "↓ [Format Converter]",
    "MLX messages format (.jsonl)",
    "↓ [MLX-tuning-fork]",
    "LoRA training",
    "↓ [Model Fusion]",
    "Deployable MLX model"
]

print("\n\n=== DATA FLOW ===")
for step in data_flow:
    print(step)