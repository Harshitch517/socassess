"""Download the public datasets into data/raw/.

    python scripts/download_data.py ait      # AIT Alert Data Set (Zenodo 8263181, CC-BY-4.0)
    python scripts/download_data.py guide    # Microsoft GUIDE (Kaggle; needs ~/.kaggle/kaggle.json)

Each file is checked against the checksum published by Zenodo. Downloads are resumable:
a file that already exists with the right checksum is skipped.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
AIT_RECORD = "https://zenodo.org/api/records/8263181"
GUIDE_SLUG = "Microsoft/microsoft-security-incident-prediction"


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_ait() -> None:
    out = RAW / "ait"
    out.mkdir(parents=True, exist_ok=True)
    record = requests.get(AIT_RECORD, timeout=60).json()
    for f in record["files"]:
        dest = out / f["key"]
        want = f["checksum"].split(":", 1)[1]
        if dest.exists() and _md5(dest) == want:
            print(f"ok (cached) {dest.name}")
            continue
        print(f"downloading {dest.name} ({f['size'] / 1e6:.1f} MB)")
        with requests.get(f["links"]["self"], stream=True, timeout=120) as r:
            r.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
        got = _md5(dest)
        if got != want:
            dest.unlink()
            sys.exit(f"checksum mismatch for {dest.name}: {got} != {want}")
        print(f"ok {dest.name}")
    zpath = out / "ait_ads.zip"
    extract = out / "extracted"
    if not extract.exists():
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():  # refuse path traversal in untrusted archives
                if name.startswith(("/", "\\")) or ".." in Path(name).parts:
                    sys.exit(f"unsafe path in archive: {name}")
            z.extractall(extract)
    print(f"AIT extracted to {extract}")


def download_guide() -> None:
    token = Path.home() / ".kaggle" / "kaggle.json"
    if not token.exists():
        sys.exit(f"Kaggle token not found at {token}. Create one at "
                 "https://www.kaggle.com/settings -> API -> Create New Token.")
    out = RAW / "guide"
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "kaggle", "datasets", "download", "-d", GUIDE_SLUG,
                    "-p", str(out), "--unzip"], check=True)
    print(f"GUIDE downloaded to {out}")


if __name__ == "__main__":
    which = sys.argv[1:] or ["ait"]
    for name in which:
        {"ait": download_ait, "guide": download_guide}[name]()
