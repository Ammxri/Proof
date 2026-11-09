"""Reply cache by request hash (A-19): a repeated request is answered from disk without HTTP.

Only successful replies are stored; an error is never cached, so ``--resume`` sends the unit again. The files live
under ``$PROOF_HOME/cache/`` (``.proof/`` by default), never in the repository, and hold no API key.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from proof.harness.client import Reply

_HASH = re.compile(r"^[0-9a-f]{64}$")


class Cache:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def path(self, request_hash: str) -> Path:
        if not _HASH.match(request_hash):
            raise ValueError(f"not a request hash: {request_hash!r}")
        return self.directory / request_hash[:2] / f"{request_hash}.json"

    def get(self, request_hash: str) -> Reply | None:
        path = self.path(request_hash)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("request_hash") != request_hash:
            return None
        reply = Reply.from_json(data.get("reply", {}))
        return reply if reply.status == "ok" else None

    def put(self, request_hash: str, reply: Reply) -> None:
        if reply.status != "ok":
            return
        path = self.path(request_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        text = json.dumps({"request_hash": request_hash, "reply": reply.to_json()}, ensure_ascii=False, sort_keys=True)
        temporary.write_bytes((text + "\n").encode("utf-8"))
        os.replace(temporary, path)
