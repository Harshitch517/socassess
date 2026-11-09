"""Assemble a Hugging Face Space (Docker SDK) folder for the read-only demo backend.

    python scripts/prepare_hf_space.py <out_dir> --cors https://your-app.vercel.app

The folder holds only what the image build needs, plus the Space card (README with front matter)
and a Dockerfile switched to read-only demo mode. Push it to the Space's git repository.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ["backend", "scripts/generate_synthetic.py", "scripts/ingest.py", "scripts/run_analysis.py",
           "requirements-runtime.txt", "Dockerfile", ".dockerignore", "LICENSE"]
FRONTEND_SKIP = {"node_modules", "dist"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--cors", default="", help="comma-separated allowed origins (your Vercel URL)")
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists() and any(p.name != ".git" for p in out.iterdir()):
        raise SystemExit(f"{out} is not empty (only a .git folder is allowed)")
    out.mkdir(parents=True, exist_ok=True)
    for rel in INCLUDE:
        src = ROOT / rel
        if not src.exists():
            continue
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, dst)
    shutil.copytree(ROOT / "frontend", out / "frontend",
                    ignore=lambda d, names: [n for n in names if n in FRONTEND_SKIP or n.endswith(".tsbuildinfo")])
    shutil.copy2(ROOT / "deploy" / "huggingface" / "README.md", out / "README.md")
    docker = (out / "Dockerfile").read_text()
    demo_env = "ENV SOCASSESS_READ_ONLY=1"
    if args.cors:
        demo_env += f" SOCASSESS_CORS_ORIGINS={args.cors}"
    docker = docker.replace("USER socassess", f"{demo_env}\nUSER socassess")
    (out / "Dockerfile").write_text(docker)
    print(f"Space folder ready: {out}")


if __name__ == "__main__":
    main()
