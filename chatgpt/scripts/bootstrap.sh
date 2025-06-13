#!/usr/bin/env bash
set -e
echo "Initializing uv environment..."
uv init --name domain-expert-llm
echo "Updating submodules..."
git submodule update --init --recursive
echo "Installing project dependencies..."
uv pip install
echo "Installing Augmentoolkit in editable mode..."
uv pip install -e libs/augmentoolkit
echo "Bootstrap complete!"
