"""Hashes and seeds that make every run reproducible and auditable."""

from __future__ import annotations

import hashlib
import json

from canon.schema import Case


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def case_hash(case: Case) -> str:
    payload = json.dumps(case.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return sha256_text(payload)


def derive_seed(*parts: object) -> int:
    """Stable 64-bit seed from arbitrary parts (independent of PYTHONHASHSEED)."""
    digest = hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")
