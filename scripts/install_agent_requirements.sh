#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <agent-dir>" >&2
  exit 1
fi

agent_dir="$1"
requirements_path="${agent_dir}/requirements.txt"

if [ -f "$requirements_path" ]; then
  python -m pip install -r "$requirements_path"
fi
