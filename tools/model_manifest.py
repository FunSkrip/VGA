"""Inspect and verify the trusted YOLO weight manifest.

Examples:
    python tools/model_manifest.py --check
    python tools/model_manifest.py --hash models/yolov8n.pt
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import Config
from app.model_integrity import (
    ModelIntegrityError,
    ModelManifestError,
    load_manifest,
    sha256_file,
    verify_model_file,
)


def check_manifest() -> int:
    manifest = load_manifest(Config.MODEL_MANIFEST_PATH)
    failures = 0
    for filename, entry in manifest.items():
        path = os.path.join(Config.YOLO_MODELS_DIR, filename)
        if not os.path.isfile(path):
            print(f"MISSING  {filename}")
            failures += 1
            continue
        try:
            digest = verify_model_file(
                path, entry["sha256"], entry["size"], use_cache=False
            )
        except ModelIntegrityError as exc:
            print(f"FAILED   {filename}: {exc}")
            failures += 1
        else:
            print(f"OK       {filename}  {digest}")
    return 1 if failures else 0


def hash_file(path: str) -> int:
    if not os.path.isfile(path):
        print(f"File not found: {path}", file=sys.stderr)
        return 2
    print(f"path:   {os.path.abspath(path)}")
    print(f"size:   {os.path.getsize(path)}")
    print(f"sha256: {sha256_file(path)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="verify every manifest model")
    group.add_argument("--hash", metavar="FILE", help="print size and SHA-256 of a file")
    arguments = parser.parse_args()

    try:
        if arguments.check:
            return check_manifest()
        return hash_file(arguments.hash)
    except ModelManifestError as exc:
        print(f"Manifest error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
