"""Verify the image contains the intended go2rtc backport and build provenance."""

import hashlib
import json
import subprocess
from pathlib import Path


binary = Path("/usr/local/go2rtc/bin/go2rtc")
metadata = json.loads(Path("/usr/local/share/go2rtc/build.json").read_text())
assert metadata["upstream_version"] == "1.9.14"
assert metadata["upstream_commit"] == "b5948cfb25404cc5cb37b166ecaa2dca20b11d4b"
assert metadata["fix_commit"] == "88024bf00912075b49d289573fa84cfda59c1682"
assert metadata["patch_sha256"] == (
    "442554a4024a2c3fff7b50ec9e33fa7a6b453b57631083137a610117846bde64"
)
assert hashlib.sha256(binary.read_bytes()).hexdigest() == metadata["binary_sha256"]
version = subprocess.check_output([str(binary), "-version"], text=True).strip()
assert version == (
    "go2rtc version 1.9.14+dev.b5948cf.dirty (b5948cf.dirty) "
    f"linux/{metadata['arch']}"
), version
print(json.dumps({"version": version, "build": metadata}, sort_keys=True))
