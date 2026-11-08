"""Location of Proof's working data (cache, runs, private sets, PDF browser)."""

from __future__ import annotations

import os
from pathlib import Path

ENV_HOME = "PROOF_HOME"
DEFAULT_HOME = ".proof"


def proof_home() -> Path:
    """``$PROOF_HOME`` if set and not empty, otherwise ``.proof`` in the current working directory; always absolute."""
    configured = os.environ.get(ENV_HOME, "").strip()
    return Path(configured or DEFAULT_HOME).resolve()
