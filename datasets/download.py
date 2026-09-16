#!/usr/bin/env python3
"""Fetch pinned raw sources; reruns preserve revisions and completed files."""

import concurrent.futures as cf
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
MANIFEST = BASE / "manifest.json"
LOCK = threading.Lock()
SOURCES = [
    ("hiersva", "hf", "AnonymousHierSVA/HierSVA"),
    ("opentitan", "git", "lowRISC/opentitan"),
    ("hwsec-unc", "git", "HWSec-UNC/verification-benchmarks"),
    ("riscv-formal", "git", "SymbioticEDA/riscv-formal"),
    ("vert", "git", "AnandMenon12/VERT"),
    ("verixa", "hf", "vyomaalabs/verixa-dataset"),
    ("nvidia-cvdp", "hf", "nvidia/cvdp-benchmark-dataset"),
    ("verilog-eval", "git", "NVlabs/verilog-eval"),
    ("large-lemma-miners", "git", "TechnionFV/large_lemma_miners"),
]


def run(args, cwd=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    if args[0] == "git":
        args = [
            "git",
            "-c",
            "http.version=HTTP/1.1",
            "-c",
            "http.lowSpeedLimit=1024",
            "-c",
            "http.lowSpeedTime=60",
        ] + args[1:]
    p = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=1800,
        check=False,
    )
    if p.returncode:
        raise RuntimeError(f"{args}: {p.stdout[-6000:]}")
    return p.stdout.strip()


def retry(fn):
    for attempt in range(3):
        try:
            return fn()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2**attempt)


def api(url):
    def get():
        with urllib.request.urlopen(url, timeout=120) as response:
            return json.load(response)

    return retry(get)


def save():
    with LOCK:
        tmp = MANIFEST.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, indent=2) + "\n")
        tmp.replace(MANIFEST)


def git_revision(url, ref="HEAD"):
    lines = retry(lambda: run(["git", "ls-remote", url, ref, ref + "^{}"])).splitlines()
    if not lines:
        raise RuntimeError(f"Cannot resolve {url} {ref}")
    return lines[-1].split()[0]


def git_snapshot(url, revision, dest):
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        run(["git", "init", str(dest)])
        run(["git", "remote", "add", "origin", url], dest)
    retry(lambda: run(["git", "fetch", "--depth=1", "origin", revision], dest))
    run(["git", "checkout", "--detach", revision], dest)
    retry(
        lambda: run(
            [
                "git",
                "submodule",
                "update",
                "--init",
                "--recursive",
                "--depth=1",
                "--jobs=4",
            ],
            dest,
        )
    )
    retry(lambda: run(["git", "lfs", "pull"], dest))
    retry(
        lambda: run(
            ["git", "submodule", "foreach", "--recursive", "git lfs pull"], dest
        )
    )
    modules = run(["git", "submodule", "status", "--recursive"], dest)
    if any(line[0] in "-+U" for line in modules.splitlines() if line):
        raise RuntimeError("Incomplete submodules: " + modules)
    run(["git", "fsck", "--no-dangling"], dest)
    run(["git", "lfs", "fsck"], dest)
    run(
        [
            "git",
            "submodule",
            "foreach",
            "--recursive",
            "git fsck --no-dangling && git lfs fsck",
        ],
        dest,
    )
    return modules.splitlines()


def hf_snapshot(entry, dest):
    info = api(
        f"https://huggingface.co/api/datasets/{entry['repo']}/revision/{entry['revision']}?blobs=true"
    )
    files = info["siblings"]
    entry["upstream_files"] = files
    save()
    errors = []

    def fetch(item):
        rel = item["rfilename"]
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        lfs = item.get("lfs")

        def matches():
            if not target.is_file() or target.stat().st_size != item["size"]:
                return False
            h = hashlib.sha256() if lfs else hashlib.sha1()
            if not lfs:
                h.update(f"blob {item['size']}\0".encode())
            with target.open("rb") as f:
                for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
                    h.update(block)
            return h.hexdigest() == (lfs["sha256"] if lfs else item["blobId"])

        if matches():
            return
        url = f"https://huggingface.co/datasets/{entry['repo']}/resolve/{entry['revision']}/{urllib.parse.quote(rel)}?download=true"
        part = target.with_name(target.name + ".part")
        run(
            [
                "curl",
                "-fL",
                "--retry",
                "5",
                "--retry-all-errors",
                "--connect-timeout",
                "30",
                "--max-time",
                "300",
                "--speed-limit",
                "1024",
                "--speed-time",
                "60",
                "-C",
                "-",
                "-o",
                str(part),
                url,
            ]
        )
        part.replace(target)
        if not matches():
            raise RuntimeError(f"Checksum or size mismatch: {rel}")

    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch, f): f["rfilename"] for f in files}
        for future in cf.as_completed(jobs):
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001
                errors.append({"file": jobs[future], "error": str(exc)})
    entry["inaccessible_files"] = errors
    if errors:
        raise RuntimeError(f"{len(errors)} files failed; see inaccessible_files")
    entry["integrity"] = (
        "Every file size and SHA-256 (LFS) or Git blob SHA-1 verified against pinned upstream metadata."
    )


def inventory(dest):
    count = size = 0
    pointers = []
    for root, dirs, files in os.walk(dest):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            p = Path(root) / name
            if name == ".git" or p.is_symlink():
                continue
            count += 1
            size += p.stat().st_size
            if p.stat().st_size < 1024:
                with p.open("rb") as f:
                    if f.read(80).startswith(
                        b"version https://git-lfs.github.com/spec/v1"
                    ):
                        pointers.append(str(p.relative_to(dest)))
    return count, size, pointers


def download(entry):
    if "revision" not in entry:
        return
    dest = BASE.parent / entry["local_directory"]
    entry["download_status"] = "downloading"
    save()
    print(f"START {entry['name']}", flush=True)
    try:
        if entry["kind"] == "hf":
            hf_snapshot(entry, dest)
        else:
            entry["submodules"] = git_snapshot(
                entry["source_url"],
                entry["revision"],
                dest / "current" if entry["name"] == "verilog-eval" else dest,
            )
            if entry["name"] == "verilog-eval":
                release = entry["release_1_0_0"]
                release["submodules"] = git_snapshot(
                    entry["source_url"],
                    release["revision"],
                    BASE.parent / release["local_directory"],
                )
            entry["integrity"] = (
                "Git object and LFS fsck passed, recursively; submodules match recorded commits."
            )
        entry["file_count"], entry["total_size_bytes"], pointers = inventory(dest)
        entry["unresolved_lfs_pointers"] = pointers
        if pointers:
            raise RuntimeError(f"{len(pointers)} unresolved LFS pointers")
        entry["download_status"] = "complete"
        entry.pop("error", None)
    except Exception as exc:  # noqa: BLE001
        entry["download_status"] = "incomplete"
        entry["error"] = str(exc)
        entry["file_count"], entry["total_size_bytes"], _ = inventory(dest)
    save()
    print(
        f"{entry['download_status'].upper()} {entry['name']}: {entry.get('total_size_bytes', 0):,} bytes {entry.get('error', '')}",
        flush=True,
    )


if __name__ == "__main__":
    manifest = (
        json.loads(MANIFEST.read_text())
        if MANIFEST.exists()
        else {
            "schema_version": 1,
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "size_definition": "Regular working-tree file bytes, excluding .git metadata and symlinks.",
            "sources": [],
        }
    )
    for name, kind, repo in SOURCES:
        entry = next((e for e in manifest["sources"] if e["name"] == name), None)
        if entry is None:
            entry = {
                "name": name,
                "kind": kind,
                "repo": repo,
                "source_url": f"https://huggingface.co/datasets/{repo}"
                if kind == "hf"
                else f"https://github.com/{repo}.git",
                "local_directory": f"datasets/raw/{name}",
                "download_status": "resolving",
            }
            manifest["sources"].append(entry)
        try:
            if "revision" not in entry:
                entry["revision"] = (
                    api(f"https://huggingface.co/api/datasets/{repo}")["sha"]
                    if kind == "hf"
                    else git_revision(entry["source_url"])
                )
            if name == "verilog-eval" and "release_1_0_0" not in entry:
                entry["release_1_0_0"] = {
                    "ref": "refs/heads/release/1.0.0",
                    "revision": git_revision(
                        entry["source_url"], "refs/heads/release/1.0.0"
                    ),
                    "local_directory": "datasets/raw/verilog-eval/release-1.0.0",
                }
            entry["download_status"] = "resolved"
            print(f"PINNED {name} {entry['revision']}", flush=True)
        except Exception as exc:  # noqa: BLE001
            entry.update(download_status="inaccessible", error=str(exc))
        save()
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(download, manifest["sources"]))
    sys.exit(
        0 if all(e["download_status"] == "complete" for e in manifest["sources"]) else 1
    )
