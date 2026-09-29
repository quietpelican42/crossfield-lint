#!/usr/bin/env python3
"""Measure the false-positive rate against real code.

Downloads a fixed list of public repositories (real projects that use
pydantic v2 field validators), pinned to an exact commit and verified by
sha256, and runs `crossfield-lint` over each. Nothing here is committed to
the package: tarballs land in a gitignored cache directory, and the whole
run skips loudly (exit 2) if network access or a checksum doesn't check
out, rather than silently reporting nothing.

The repository list and results below are what was actually run to write
the README's "Measured" line -- see that section for the real, pasted
output of this exact script.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).parent / ".noise_floor_cache"

# (owner/repo, commit sha, sha256 of the codeload tarball at that commit)
REPOS = [
    ("adrienneyager/dbt-loom", "a9eca953b8c0dcbfc98695ad1209a12ebdedb292",
     "5ec6a83f07c4544b05fabae7bae7400410f99eba4a6a338421a3e81b7a336b2c"),
    ("BBC-Esq/VectorDB-Plugin", "1bfae2da6616c27b4fb7dc2afe750463b6597bee",
     "925c57651de4d14fb3b38b09d410a86ff32642e00c091811e0d6a77e3f7d783f"),
    ("compiler-explorer/explain", "a717ef2671fbe11aaca9baa226228fbc83438d2c",
     "1f4da83617c361cdb26f1d457e78c5e9604688acebb618f5b339be71fd9b6334"),
    ("developmentseed/tipg", "18ac43702cc1092eafb2e124fbef4f22f7a3ab85",
     "84687c94be71d6e7f190a22b562a882200ee4b9695835c8bcd4d59cef4d41151"),
    ("dnotitia/smoothie-qwen", "c005f0b9b0d7711be03120907c3f8176a1fe51c6",
     "2daf04b9c3e5aedf653e15606d916e8709ef9b322d4c7a29da38e6e5c0ce891d"),
    ("galaxyproject/gravity", "2042ad3248fe4b305c61fa99c657141a1dc8bafd",
     "ca09e2abf417d48d10d8d60f3a451f3b7e33e9a90a49e752c501f6a2e54ceb4e"),
    ("immortal71/openoncology", "8517a743daabb5cf626ce90293e6ef67e5f41bdb",
     "08aa5a8b239c467643e4d03f3a6266b005f97851086e0fe8ef7d224e681a8a7b"),
    ("lemonyte/wastebin", "ac09d3faafce1aa7ddbf10b9813b7bffae55dafa",
     "2d29ea80e8e1848b25988dbd77fc8da69d6225e8ba297bc8b7a9ebe8b6af5961"),
    ("plantcad/genecad", "edddabb6263f2608c42d72f49a67a82337f96320",
     "702575ec1efea9d192ba2f7abf21ed0a6f303bdc3796ec8cb6cc9c167c6bb086"),
    ("plexe-ai/plexe", "a1e05f6dc4c0875e0075f3b6f020fbecef57a699",
     "b10d4a009567c853a9494a2f785440e33a94112a8c13a3723573db709c0806f3"),
    ("serkanyasr/agentic_rag_project", "19582eb0db9ce94293ce8b609ca4eed1629cf86a",
     "54cb16ab40bf4f758fc8e8fa3644b73a6df9c9ada10452f11a558aacef758835"),
    ("the-momentum/fhir-mcp-server", "df048bc8d4e8a784f2dd3e690d43e535355ea7ef",
     "99ef726a8a855ca059c2944b576e021dd985fbf4acddbd25293fc21e6a6c75f8"),
    ("ton-studio/ton-labels", "9aa472348c88d766173eb50b9a040070e527599b",
     "0776018c3bda53c58d68a824bf78aa984855f6726152ba62de75f3330ab94af2"),
    ("zhai-lw/L3AC", "1cb03f5e037c9ecdfc15bbaf3046f67d9a77c347",
     "cf90515fe2f05c432025bbf90a0c11e86dc0b75d262b8636912bd881249559cf"),
    ("zornade/visura-api", "8ef1388ebb40b52048bb09254193fb6d9037e027",
     "0503a8727a604221acac517500bd87a08477a28c8f60be7f7d1d83f6aacd0827"),
]

TIMEOUT = 30


def fetch(repo: str, sha: str, expected_sha256: str) -> Path:
    name = repo.replace("/", "__")
    tarball = CACHE_DIR / f"{name}.tar.gz"
    extracted = CACHE_DIR / name
    if extracted.exists():
        return extracted

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{repo}/archive/{sha}.tar.gz"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            data = resp.read()
    except OSError as e:
        print(f"SKIP: could not download {repo}: {e}", file=sys.stderr)
        raise

    got = hashlib.sha256(data).hexdigest()
    if got != expected_sha256:
        print(
            f"SKIP: sha256 mismatch for {repo} -- expected {expected_sha256}, got {got}",
            file=sys.stderr,
        )
        raise ValueError("checksum mismatch")

    tarball.write_bytes(data)
    with tarfile.open(tarball) as tf:
        tf.extractall(CACHE_DIR)  # noqa: S202 -- trusted, sha256-pinned source
    tarball.unlink()
    # The tarball's top-level dir is "<repo>-<sha>"; normalize to our name.
    repo_name = repo.split("/")[1]
    top = CACHE_DIR / f"{repo_name}-{sha}"
    if top.exists():
        top.rename(extracted)
    return extracted


def main() -> int:
    total_models = 0
    total_findings = 0
    skipped = 0
    for repo, sha, digest in REPOS:
        try:
            path = fetch(repo, sha, digest)
        except (OSError, ValueError):
            skipped += 1
            continue
        result = subprocess.run(
            [sys.executable, "-m", "crossfield_lint.cli", str(path), "--format", "json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(result.stdout)
        models = payload["models_checked"]
        findings = len(payload["findings"])
        total_models += models
        total_findings += findings
        print(f"{repo:40s} models={models:3d} findings={findings}")
        for f in payload["findings"]:
            print(f"    {f['file']}:{f['line']}: {f['message']}")

    print()
    print(f"repos checked: {len(REPOS) - skipped}/{len(REPOS)} (skipped: {skipped})")
    print(f"total models checked: {total_models}")
    print(f"total findings: {total_findings}")
    return 0 if skipped == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
