"""Copy filly's web build into psychopy_filly/web, the files that PsychoJS experiments use.

Usage: python tools/vendor_web.py FILLY_WEB_BUILD

FILLY_WEB_BUILD is the output folder of filly's tools/build_filly_web.sh: filly.js,
filly-core.js, filly-core.wasm, and licenses/. The plugin ships these files, and the component
copies them into each experiment folder, so experiments load them from their own origin. A
same-origin copy also loads under cross-origin isolation (COOP and COEP headers), which a CDN
copy does only if the CDN sends a Cross-Origin-Resource-Policy header.

Writes psychopy_filly/web/VENDOR.json with the size and SHA-256 of each file.
"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

FILES = ["filly.js", "filly-core.js", "filly-core.wasm"]
TARGET = Path(__file__).resolve().parents[1] / "psychopy_filly" / "web"


def main():
    source = Path(sys.argv[1]).resolve()
    missing = [name for name in FILES if not (source / name).is_file()]
    if missing or not (source / "licenses").is_dir():
        sys.exit(f"{source} is not a filly web build: missing {missing or ['licenses/']}")
    shutil.rmtree(TARGET / "licenses", ignore_errors=True)
    shutil.copytree(source / "licenses", TARGET / "licenses")
    record = {}
    for name in FILES:
        shutil.copyfile(source / name, TARGET / name)
        data = (TARGET / name).read_bytes()
        record[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    (TARGET / "VENDOR.json").write_text(json.dumps(
        {"source": "filly tools/build_filly_web.sh", "files": record}, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
