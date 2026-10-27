"""Bounded, authenticated HF download with resumable verified HTTP ranges.

Used by the isolated SAM lab when a monolithic transfer stalls. URLs and tokens
are never logged. Only official HF metadata and its authorized redirects are used.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import time
from pathlib import Path


def download(model, filename, revision, destination, *, workers=4, chunk_mb=16):
    import requests
    from huggingface_hub import get_hf_file_metadata, get_token, hf_hub_url

    token = get_token()
    url = hf_hub_url(model, filename, revision=revision)
    metadata = get_hf_file_metadata(url, token=token or False)
    size = metadata.size
    digest = metadata.etag
    if size is None or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Require official size and SHA256 LFS metadata")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size == size:
        with destination.open("rb") as existing:
            verified = hashlib.file_digest(existing, "sha256").hexdigest() == digest
        if verified:
            print(
                json.dumps(
                    {
                        "model": model,
                        "file": filename,
                        "revision": revision,
                        "size": size,
                        "sha256": digest,
                        "status": "already_verified",
                        "destination": str(destination),
                    }
                ),
                flush=True,
            )
            return
    chunk_size = chunk_mb * 1024 * 1024
    parts = destination.with_name(destination.name + ".ranges")
    parts.mkdir(exist_ok=True)
    manifest = {
        "model": model,
        "file": filename,
        "revision": revision,
        "size": size,
        "sha256": digest,
        "chunk_size": chunk_size,
    }
    manifest_path = parts / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise ValueError("Existing download belongs to a different artifact or chunk size")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    headers = {"Authorization": "Bearer " + token} if token else {}

    def fetch(index):
        start = index * chunk_size
        end = min(size, start + chunk_size) - 1
        part = parts / f"{index:05d}.part"
        receipt = part.with_suffix(".sha256")
        if part.exists() and part.stat().st_size == end - start + 1 and receipt.exists():
            with part.open("rb") as existing:
                valid = hashlib.file_digest(existing, "sha256").hexdigest() == receipt.read_text()
            if valid:
                return index
        for attempt in range(4):
            try:
                with requests.get(
                    url + f"?download=true&n3lx_range={start}-{end}&attempt={attempt}",
                    headers={**headers, "Range": f"bytes={start}-{end}"},
                    timeout=(20, 45),
                    stream=True,
                ) as response:
                    if (
                        response.status_code != 206
                        or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}"
                    ):
                        raise RuntimeError(
                            f"Unexpected range response: HTTP {response.status_code}"
                        )
                    hasher = hashlib.sha256()
                    written = 0
                    with part.open("wb") as stream:
                        for block in response.iter_content(1024 * 1024):
                            stream.write(block)
                            hasher.update(block)
                            written += len(block)
                    if written != end - start + 1:
                        raise RuntimeError("Incomplete HTTP range")
                    receipt.write_text(hasher.hexdigest())
                    return index
            except (requests.RequestException, RuntimeError) as error:
                reason = str(error) if isinstance(error, RuntimeError) else type(error).__name__
                if attempt == 3:
                    # Requests errors can contain signed redirect URLs; do not print them.
                    raise RuntimeError(
                        f"Range {index} failed after four attempts: {reason}"
                    ) from None
                time.sleep(2**attempt)

    count = (size + chunk_size - 1) // chunk_size
    done = 0
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for future in concurrent.futures.as_completed(
            [pool.submit(fetch, i) for i in range(count)]
        ):
            index = future.result()
            done += min(chunk_size, size - index * chunk_size)
            print(
                json.dumps(
                    {
                        "file": filename,
                        "bytes": done,
                        "total": size,
                        "percent": round(done * 100 / size, 1),
                        "seconds": round(time.monotonic() - started, 1),
                    }
                ),
                flush=True,
            )
    temporary = destination.with_name(destination.name + ".verified-incomplete")
    hasher = hashlib.sha256()
    with temporary.open("wb") as stream:
        for index in range(count):
            with (parts / f"{index:05d}.part").open("rb") as fragment:
                while block := fragment.read(4 * 1024 * 1024):
                    stream.write(block)
                    hasher.update(block)
    if hasher.hexdigest() != digest:
        raise RuntimeError("Official SHA256 did not match; artifact was not installed")
    os.replace(temporary, destination)
    # Only remove the exact chunks this invocation verified, after full SHA validation.
    for index in range(count):
        part = parts / f"{index:05d}.part"
        part.unlink()
        part.with_suffix(".sha256").unlink()
    print(
        json.dumps({**manifest, "status": "verified", "destination": str(destination)}), flush=True
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    parser.add_argument("filename")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 5))
    parser.add_argument("--chunk-mb", type=int, default=16, choices=range(1, 33))
    args = parser.parse_args()
    download(
        args.model,
        args.filename,
        args.revision,
        args.destination,
        workers=args.workers,
        chunk_mb=args.chunk_mb,
    )


if __name__ == "__main__":
    main()
