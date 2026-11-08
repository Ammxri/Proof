"""PR-N04 / NZ-04: keys come from the rule set; the rules code loads no HTTP or model client and needs no network.

The static import check for ``src/proof_rules`` is in test_repository.py. These tests check the running process.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys

import pytest

from proof_rules import loader
from proof_rules.explain import explain
from proof_rules.keys import compute_key, compute_variant_key

MODULES = [
    "proof_rules.model",
    "proof_rules.logic",
    "proof_rules.engine",
    "proof_rules.ablation",
    "proof_rules.keys",
    "proof_rules.loader",
    "proof_rules.explain",
]
CLIENTS = {"httpx", "requests", "urllib3", "aiohttp", "http.client", "openai", "anthropic", "ollama", "proof.harness"}


def test_rules_modules_load_no_http_or_model_client():
    script = (
        "import importlib, json, sys\n"
        f"for name in {MODULES!r}: importlib.import_module(name)\n"
        "print(json.dumps(sorted(sys.modules)))\n"
    )
    command = [sys.executable, "-I", "-c", script]
    result = subprocess.run(command, capture_output=True, check=True, text=True)  # noqa: S603 - own interpreter, fixed script
    loaded = set(json.loads(result.stdout))
    assert not {name for name in loaded if name in CLIENTS or name.split(".")[0] in CLIENTS}


class _NoNetwork(socket.socket):
    def __init__(self, *args, **kwargs):
        raise AssertionError("the rules code must not open sockets")


def test_keys_need_no_network(monkeypatch, fixture_packs, prd_facts):
    monkeypatch.setattr(socket, "socket", _NoNetwork)
    monkeypatch.setattr(socket, "create_connection", _NoNetwork)
    with pytest.raises(AssertionError):
        socket.socket()
    assert loader.check(fixture_packs).ok
    domain = loader.load_domain("demo", fixture_packs)
    assert compute_key(domain, prd_facts).determinability == "refer_urgent"
    variant = {code: value for code, value in prd_facts.items() if code != "lab.crp_mg_l"}
    assert compute_variant_key(domain, variant, prd_facts).required_questions == ("lab.crp_mg_l",)
    assert explain(domain, prd_facts)
