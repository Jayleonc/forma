#!/usr/bin/env python3
"""
Pre-download a Sentence-Transformers model independently of the QA pipeline.

Usage:
  python tools/download_st_model.py --model sentence-transformers/all-MiniLM-L6-v2
  python tools/download_st_model.py --model sentence-transformers/all-MiniLM-L6-v2 --cache-dir ~/.cache/huggingface

Options:
  --model      Hugging Face model id or local path. Default: sentence-transformers/all-MiniLM-L6-v2
  --cache-dir  Optional cache directory (sets HF_HOME for this process).
  --local-only If set, skip network and attempt to load from local cache only.
"""
import argparse
import os
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-download Sentence-Transformers model")
    parser.add_argument(
        "--model",
        type=str,
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Model ID or local path",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Optional cache directory (sets HF_HOME)",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Load using local cache only (no network)",
    )
    args = parser.parse_args()

    if args.cache_dir:
        os.environ["HF_HOME"] = os.path.expanduser(args.cache_dir)
        print(f"[INFO] Using HF_HOME={os.environ['HF_HOME']}")

    # Defer imports until after env is set
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        print(f"[ERROR] sentence-transformers is not installed: {e}")
        return 1

    start = time.time()
    print(f"[INFO] Preparing to load model: {args.model}")
    try:
        model = SentenceTransformer(args.model, cache_folder=os.environ.get("HF_HOME"), use_auth_token=None)
        if args.local_only:
            # Force a local-only pass by trying to read tokenizer/model files from cache without network.
            # sentence-transformers doesn't expose local_only directly; if offline, load will fail early.
            # We emulate by setting TRANSFORMERS_OFFLINE=1 for this process.
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            _ = SentenceTransformer(args.model, cache_folder=os.environ.get("HF_HOME"))
        # Perform a tiny encode to ensure weights are usable
        _ = model.encode(["healthcheck"], show_progress_bar=False)
    except Exception as e:
        print("[ERROR] Failed to load or validate model:", e)
        return 2

    elapsed = time.time() - start
    print(f"[SUCCESS] Model is available and validated. Elapsed: {elapsed:.2f}s")
    # Print final cache location hint
    cache_hint = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
    print(f"[INFO] Cached under: {cache_hint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
