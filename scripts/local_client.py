#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path


def main() -> int:
    forwarded_args = sys.argv[1:]
    modules = {"serve", "get", "set", "update", "delete", "query", "version"}
    options_with_values = {
        "--target",
        "--entity-id",
        "--series",
        "--timestamp",
        "--value",
        "--start",
        "--end",
        "--limit",
    }
    module_provided = False
    skip_next = False
    for arg in forwarded_args:
        if skip_next:
            skip_next = False
        elif arg in options_with_values:
            skip_next = True
        elif arg in modules:
            module_provided = True
            break

    if not module_provided:
        forwarded_args = ["get", *forwarded_args]

    repo_root = Path(__file__).resolve().parents[1]
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "grpc-timeseries",
        "grpc-timeseries",
        *forwarded_args,
    ]
    return subprocess.call(command, cwd=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
