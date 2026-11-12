"""Copy filly's web build into psychopy_filly/web, the files that PsychoJS experiments use.

Usage: python tools/vendor_web.py [VERSION | FOLDER]

With VERSION (X.Y.Z), the script downloads filly-web-X.Y.Z.zip from that filly release on GitHub
and checks its SHA-256 hash against the hash that GitHub reports for the file. Without an
argument, it uses the version of the installed filly package, so that the web build and the
Python package are the same release. FOLDER is a local build instead, the output folder of
filly's web/tools/build_filly_web.sh, for development.

The build is filly.js, filly-core.js, filly-core.wasm, and licenses/. The plugin ships these
files, and the component copies them into each experiment folder, so experiments load them from
their own origin. A same-origin copy also loads under cross-origin isolation (COOP and COEP
headers), which a CDN copy does only if the CDN sends a Cross-Origin-Resource-Policy header.

Writes psychopy_filly/web/VENDOR.json with the source and the size and SHA-256 of each file.
"""

import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from importlib import metadata
from pathlib import Path

FILES = ["filly.js", "filly-core.js", "filly-core.wasm"]
TARGET = Path(__file__).resolve().parents[1] / "psychopy_filly" / "web"
REPOSITORY = "aforren1/filly"
# GitHub's API refuses requests without a User-Agent.
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "psychopy-filly-vendor-web"}


def fetch(url, headers=HEADERS):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read()


def download_asset(version, name):
    """The bytes of one file of a filly release, checked against GitHub's SHA-256 digest."""
    url = f"https://api.github.com/repos/{REPOSITORY}/releases/tags/v{version}"
    try:
        release = json.loads(fetch(url))
    except urllib.error.HTTPError as error:
        sys.exit(f"Cannot read the release v{version} of {REPOSITORY}: HTTP {error.code}")
    asset = next((item for item in release["assets"] if item["name"] == name), None)
    if asset is None:
        names = ", ".join(item["name"] for item in release["assets"])
        sys.exit(f"The release v{version} has no {name}. It has: {names}")
    # GitHub computes the digest when the file is uploaded. Without it, nothing checks the bytes.
    digest = asset.get("digest")
    if not digest or not digest.startswith("sha256:"):
        sys.exit(f"GitHub reports no SHA-256 digest for {name}")
    data = fetch(asset["browser_download_url"], {"User-Agent": HEADERS["User-Agent"]})
    actual = hashlib.sha256(data).hexdigest()
    if digest != "sha256:" + actual:
        sys.exit(f"{name} has SHA-256 {actual}, but GitHub reports {digest}")
    return data, actual


def vendor(source, target, record_source):
    missing = [name for name in FILES if not (source / name).is_file()]
    if missing or not (source / "licenses").is_dir():
        sys.exit(f"{source} is not a filly web build: missing {missing or ['licenses/']}")
    shutil.rmtree(target / "licenses", ignore_errors=True)
    shutil.copytree(source / "licenses", target / "licenses")
    files = {}
    for name in FILES:
        shutil.copyfile(source / name, target / name)
        data = (target / name).read_bytes()
        files[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    record = {**record_source, "files": files}
    (target / "VENDOR.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=1))


def main(target=TARGET):
    if len(sys.argv) > 2:
        sys.exit(__doc__)
    if len(sys.argv) == 2 and Path(sys.argv[1]).is_dir():
        source = Path(sys.argv[1]).resolve()
        vendor(source, target, {"source": "a local build (filly web/tools/build_filly_web.sh)"})
        return
    if len(sys.argv) == 2:
        version = sys.argv[1].removeprefix("v")
    else:
        try:
            version = metadata.version("filly")
        except metadata.PackageNotFoundError:
            sys.exit("filly is not installed. Give a release version, such as 0.4.1, or a build folder.")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit(f"{version} is not a release version (X.Y.Z), and no folder has that name.")
    name = f"filly-web-{version}.zip"
    data, digest = download_asset(version, name)
    with tempfile.TemporaryDirectory() as folder:
        # extractall drops absolute paths and ".." from member names.
        zipfile.ZipFile(io.BytesIO(data)).extractall(folder)
        vendor(Path(folder), target, {"source": f"filly v{version} release, {name}", "zipSha256": digest})


if __name__ == "__main__":
    main()
