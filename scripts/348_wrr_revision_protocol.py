#!/usr/bin/env python3
"""Lock the scientific protocol before acquiring or scoring new evidence."""

from __future__ import annotations

import json
from pathlib import Path

import wrr_r3_common as C

ATTACHMENT = Path(
    "/home/lzq/.codex/attachments/fdae9de4-eb48-48d2-97a6-3ac57db73bdb/pasted-text-1.txt"
)


def main() -> int:
    inputs = {"protocol": C.DOCS / "PROTOCOL.md", "config": C.CONFIG}
    if ATTACHMENT.exists():
        inputs["user_review"] = ATTACHMENT
    if C.LOCK.exists():
        C.protocol()
        print(f"[348] existing immutable protocol verified: {C.LOCK}")
        return 0
    payload = C.fingerprint(Path(__file__), inputs, status="protocol_locked_before_new_experiments")
    C.write_json(C.LOCK, payload)
    print(json.dumps({"lock": str(C.LOCK), "sha256": C.digest(C.LOCK)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
