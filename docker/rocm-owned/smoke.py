"""Exercise the final Frigate image without network, GPU devices, or appdata."""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import urllib.request
from pathlib import Path


def pack_compile_request(value: str | bool | list | dict) -> bytes:
    """Encode the helper's four MessagePack value types without extra packages."""
    if isinstance(value, bool):
        return b"\xc3" if value else b"\xc2"
    if isinstance(value, str):
        encoded = value.encode()
        return b"\xdb" + len(encoded).to_bytes(4, "big") + encoded
    if isinstance(value, list):
        return (
            b"\xdd"
            + len(value).to_bytes(4, "big")
            + b"".join(map(pack_compile_request, value))
        )
    if isinstance(value, dict):
        return (
            b"\xdf"
            + len(value).to_bytes(4, "big")
            + b"".join(
                pack_compile_request(key) + pack_compile_request(item)
                for key, item in value.items()
            )
        )
    raise TypeError("Unsupported compile-request value")


def unpack_compile_reply(data: bytes) -> bytes:
    """Decode 2.18's single-key reply with one binary chunk for this tiny kernel."""
    # MIGraphX wraps binary data in an array of chunks, even below its 4 GiB
    # chunk limit. This probe is small enough to require exactly one chunk.
    prefix = b"\x81\xabcode_object\x91"
    if not data.startswith(prefix) or len(data) <= len(prefix):
        raise ValueError("Unexpected HIPRTC driver reply")
    offset = len(prefix)
    length_bytes = {0xC4: 1, 0xC5: 2, 0xC6: 4}.get(data[offset])
    if length_bytes is None or len(data) < offset + 1 + length_bytes:
        raise ValueError("Missing HIPRTC binary payload length")
    length = int.from_bytes(data[offset + 1 : offset + 1 + length_bytes], "big")
    offset += 1 + length_bytes
    if len(data) != offset + length:
        raise ValueError("Truncated or trailing HIPRTC binary payload")
    return data[offset:]


def linking():
    """Check the final image's library resolution and actual binding imports."""
    root = Path("/opt/rocm").resolve()
    binding = (root / "lib/migraphx.cpython-311-x86_64-linux-gnu.so").resolve()
    # Resolve every detector library and its transitive dependencies. Optional
    # SDK profiler plugins require their own loader and are not detector inputs.
    paths = {
        path.resolve()
        for path in (root / "lib/migraphx/lib").rglob("*.so*")
        if path.is_file()
    }
    paths.add(binding)
    paths |= {
        (root / "bin" / name).resolve()
        for name in ("migraphx-driver", "migraphx-hiprtc-driver", "rocminfo")
    }
    checked = 0
    for path in sorted(paths):
        with path.open("rb") as stream:
            header = stream.read(20)
        if header[:4] != b"\x7fELF" or header[18:20] != b">\x00":
            continue
        result = subprocess.run(
            ["ldd", *([] if path == binding else ["-r"]), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        details = result.stdout + result.stderr
        assert (
            result.returncode == 0
            and "not found" not in details
            and "undefined symbol:" not in details
        ), (path, details)
        checked += 1
    import migraphx
    import onnxruntime

    from frigate.app import FrigateApp
    from frigate.detectors.detector_types import api_types
    from frigate.version import VERSION

    assert Path(migraphx.__file__).resolve() == binding
    assert "migraphx" in api_types and FrigateApp is not None
    assert "CPUExecutionProvider" in onnxruntime.get_available_providers()
    assert not any(
        "MIGraphX" in value for value in onnxruntime.get_available_providers()
    )
    source_commit = os.environ["FRIGATE_SOURCE_COMMIT"]
    version_commit = VERSION.rsplit("-", 1)[-1]
    assert re.fullmatch(r"[0-9a-f]{40}", source_commit)
    assert re.fullmatch(r"[0-9a-f]{7,40}", version_commit)
    assert source_commit.startswith(version_commit), (VERSION, source_commit)
    return {
        "native_libraries_checked": checked,
        "binding_application_import": "passed",
        "frigate_version": VERSION,
        "frigate_source_commit": source_commit,
    }


def helper(manifest):
    """Compile an explicit kernel for every profile target without calling HSA."""
    results = []
    expected_flags = {
        row["arch"]: row["flags"] & 0xFF
        for row in manifest["verification"]["offline_mlir_objects"]
    }
    for arch in manifest["configuration"]["gpu_targets"]:
        request = {
            "srcs": [
                {
                    "path": "public-check.cpp",
                    "content": '#include <type_traits>\nstatic_assert(std::is_floating_point<float>::value, "float trait");\nextern "C" __global__ void check(float* x) { x[0] += 1.0f; }\n',
                }
            ],
            "params": [
                "-std=c++17",
                "-I/usr/include/c++/14",
                "-I/usr/include/x86_64-linux-gnu/c++/14",
                "-I/usr/include",
                "-I/usr/include/x86_64-linux-gnu",
            ],
            "arch": arch,
            "quiet": False,
        }
        stdout_protocol = manifest["configuration"]["rocm"] == "10.1.0"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "check.hsaco"
            result = subprocess.run(
                ["/opt/rocm/bin/migraphx-hiprtc-driver"]
                + ([] if stdout_protocol else [str(output)]),
                input=pack_compile_request(request),
                capture_output=True,
                timeout=90,
                check=False,
            )
            assert result.returncode == 0, result.stderr.decode(errors="replace")
            code = (
                unpack_compile_reply(result.stdout)
                if stdout_protocol
                else output.read_bytes()
            )
        assert (
            len(code) >= 64
            and code[:6] == b"\x7fELF\x02\x01"
            and code[18:20] == b"\xe0\x00"
        )
        assert int.from_bytes(code[48:52], "little") & 0xFF == expected_flags[arch]
        results.append(
            {
                "arch": arch,
                "bytes": len(code),
                "sha256": hashlib.sha256(code).hexdigest(),
            }
        )
    return {"offline_hiprtc_objects": results}


def migrations(source_root: Path = Path("/opt/frigate")):
    """Upgrade a synthetic Gary-era database twice and preserve its seeded rows."""
    from peewee import SqliteDatabase
    from peewee_migrate import Router

    # Gary's final migration is 035. All 35 shared files were byte-identical
    # to upstream 91e91c6 when this public upgrade fixture was established.
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        older = folder / "migrations"
        older.mkdir()
        sources = sorted((source_root / "migrations").glob("*.py"))
        previous = [path for path in sources if int(path.name[:3]) <= 35]
        assert len(previous) == 35
        for path in previous:
            (older / path.name).write_bytes(path.read_bytes())
        db = SqliteDatabase(folder / "frigate.db")
        Router(db, migrate_dir=str(older)).run()
        db.execute_sql(
            'INSERT INTO "user" (username, password_hash, notification_tokens) VALUES (?, ?, ?)',
            ("fixture-admin", "synthetic-hash-not-a-login", "[]"),
        )
        columns = [column.name for column in db.get_columns("recordings")]
        values = {
            "id": "fixture-recording",
            "path": "/tmp/no-media.mp4",
            "camera": "fixture",
            "start_time": 1000.0,
            "end_time": 1001.0,
            "duration": 1.0,
            "motion": 0,
            "objects": 0,
            "segment_size": 0,
        }
        names = [name for name in values if name in columns]
        sql_names = ", ".join('"' + name + '"' for name in names)
        db.execute_sql(
            f"INSERT INTO recordings ({sql_names}) VALUES ({','.join('?' for _ in names)})",
            [values[name] for name in names],
        )
        fields = ", ".join('"' + name + '"' for name in columns)
        before = db.execute_sql("SELECT " + fields + " FROM recordings").fetchall()
        users = db.execute_sql('SELECT * FROM "user"').fetchall()
        router = Router(db, migrate_dir=str(source_root / "migrations"))
        pending = list(router.diff)
        assert pending
        router.run()
        assert not Router(db, migrate_dir=str(source_root / "migrations")).diff
        assert (
            db.execute_sql("SELECT " + fields + " FROM recordings").fetchall() == before
        )
        assert db.execute_sql('SELECT * FROM "user"').fetchall() == users
        assert db.execute_sql("PRAGMA integrity_check").fetchone() == ("ok",)
        assert not db.execute_sql("PRAGMA foreign_key_check").fetchall()
        db.close()
        checksum = hashlib.sha256((folder / "frigate.db").read_bytes()).hexdigest()
        Router(db, migrate_dir=str(source_root / "migrations")).run()
        db.close()
        assert (
            hashlib.sha256((folder / "frigate.db").read_bytes()).hexdigest() == checksum
        )
    return {
        "synthetic_database_migrations": pending,
        "rows_and_credentials_preserved": True,
        "second_migration_unchanged": True,
    }


def main():
    """Require device-free checks before publishing an application image."""
    assert not Path("/dev/kfd").exists() and not Path("/dev/dri").exists()
    assert os.environ["FRIGATE_OFFLINE_CHECK"] == "1"
    assert os.environ["HSA_ENABLE_SDMA"] == "0"
    assert os.geteuid() != 0
    manifest = json.loads(Path("/usr/share/frigate-rocm/runtime.json").read_text())
    assert manifest["profile"] == os.environ["FRIGATE_ROCM_PROFILE"]
    assert manifest["gpu_tested"] is False
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot", action="store_true")
    args = parser.parse_args()
    if args.boot:
        from frigate.version import VERSION

        with urllib.request.urlopen(
            "http://127.0.0.1:5000/api/version", timeout=2
        ) as response:
            version = response.read().decode().strip('"')
        assert version == VERSION
        assert os.environ["FRIGATE_SOURCE_COMMIT"].startswith(
            VERSION.rsplit("-", 1)[-1]
        )
        database = sqlite3.connect(
            "file:/config/frigate.db?mode=ro", uri=True, timeout=2
        )
        try:
            assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        finally:
            database.close()
        print(
            json.dumps(
                {
                    "service_api_version": version,
                    "new_database_integrity": "passed",
                    "gpu_tested": False,
                }
            )
        )
        return
    result = {
        **linking(),
        **helper(manifest),
        **migrations(),
        "gpu_tested": False,
        "production_data_used": False,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
