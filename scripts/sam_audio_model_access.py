"""Check/download official SAM weights using the existing local HF login.

Never prints a credential, accepts terms, or substitutes an unofficial mirror.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MODEL = "facebook/sam-audio-small"
REVISION = "20b65f56888142eebe7c37448c6f6b3b32600e9b"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.download and args.destination is None:
        parser.error("--download requires --destination")
    from huggingface_hub import get_hf_file_metadata, get_token, hf_hub_url, snapshot_download
    from huggingface_hub.errors import GatedRepoError, HfHubHTTPError

    token = get_token()
    report = {"model": MODEL, "revision": REVISION, "local_login": bool(token)}
    try:
        get_hf_file_metadata(
            hf_hub_url(MODEL, "config.json", revision=REVISION), token=token or False
        )
    except GatedRepoError:
        report["status"] = "access_pending"
        print(json.dumps(report))
        return 2
    except HfHubHTTPError as error:
        report.update(
            status="http_error",
            http_status=error.response.status_code if error.response is not None else None,
        )
        print(json.dumps(report))
        return 1
    report["status"] = "accessible"
    if args.download:
        target = args.destination.resolve()
        snapshot_download(
            MODEL,
            revision=REVISION,
            local_dir=target,
            token=token or False,
            allow_patterns=["config.json", "checkpoint.pt", "LICENSE", "README.md"],
        )
        report.update(status="downloaded", directory=str(target))
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
