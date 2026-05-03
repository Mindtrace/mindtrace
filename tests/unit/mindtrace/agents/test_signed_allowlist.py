"""Unit tests for allowlist signing and signed registry."""
from __future__ import annotations

import json
import pytest

from mindtrace.agents.allowlist.registry import AllowlistEntry, MindtraceAllowlistRegistry
from mindtrace.agents.allowlist.signing import sign_entry, verify_entry


def _make_entry(dotted_path: str = "myapp.agents:MyAgent", entry_type: str = "agent_class") -> AllowlistEntry:
    return AllowlistEntry(
        dotted_path=dotted_path,
        entry_type=entry_type,  # type: ignore[arg-type]
        registered_by="test",
    )


# ---------------------------------------------------------------------------
# signing.py tests
# ---------------------------------------------------------------------------

def test_sign_and_verify_roundtrip():
    entry = _make_entry()
    sig = sign_entry(entry, "my_secret")
    assert verify_entry(entry, sig, "my_secret") is True


def test_tampered_dotted_path_fails():
    entry = _make_entry(dotted_path="original.path:Agent")
    sig = sign_entry(entry, "my_secret")
    tampered = entry.model_copy(update={"dotted_path": "tampered.path:Agent"})
    assert verify_entry(tampered, sig, "my_secret") is False


def test_different_secret_fails():
    entry = _make_entry()
    sig = sign_entry(entry, "secret_a")
    assert verify_entry(entry, sig, "secret_b") is False


# ---------------------------------------------------------------------------
# registry.py integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_without_secret_no_signature():
    reg = MindtraceAllowlistRegistry(signing_secret=None)
    entry = _make_entry("myapp.TestAgent", "agent_class")
    await reg.register(entry)
    bucket = reg._mem.get("mindtrace:allowlist:agent_class", {})
    stored = AllowlistEntry.model_validate_json(bucket["myapp.TestAgent"])
    assert stored.signature is None


@pytest.mark.asyncio
async def test_register_with_secret_sets_signature():
    reg = MindtraceAllowlistRegistry(signing_secret="test_secret")
    entry = _make_entry("myapp.SignedAgent", "agent_class")
    await reg.register(entry)
    bucket = reg._mem.get("mindtrace:allowlist:agent_class", {})
    stored = AllowlistEntry.model_validate_json(bucket["myapp.SignedAgent"])
    assert stored.signature is not None
    assert len(stored.signature) > 0


@pytest.mark.asyncio
async def test_is_permitted_rejects_tampered_entry():
    reg = MindtraceAllowlistRegistry(signing_secret="test_secret")
    entry = _make_entry("myapp.TamperedAgent", "agent_class")
    await reg.register(entry)
    # Manually corrupt the signature in _mem
    bucket = reg._mem["mindtrace:allowlist:agent_class"]
    stored = AllowlistEntry.model_validate_json(bucket["myapp.TamperedAgent"])
    corrupted = stored.model_copy(update={"signature": "deadbeef" * 8})
    bucket["myapp.TamperedAgent"] = corrupted.model_dump_json()
    result = await reg.is_permitted("myapp.TamperedAgent", "agent_class")
    assert result is False


@pytest.mark.asyncio
async def test_is_permitted_accepts_valid_signed_entry():
    reg = MindtraceAllowlistRegistry(signing_secret="test_secret")
    entry = _make_entry("myapp.ValidAgent", "agent_class")
    await reg.register(entry)
    result = await reg.is_permitted("myapp.ValidAgent", "agent_class")
    assert result is True


@pytest.mark.asyncio
async def test_unsigned_entry_rejected_when_secret_set():
    reg = MindtraceAllowlistRegistry(signing_secret="test_secret")
    # Mark as seeded so _ensure_seeded won't override our manual insert
    reg._seeded = True
    # Manually insert entry with signature=None
    entry = _make_entry("myapp.UnsignedAgent", "agent_class")
    bucket = reg._mem.setdefault("mindtrace:allowlist:agent_class", {})
    bucket["myapp.UnsignedAgent"] = entry.model_dump_json()  # signature=None
    result = await reg.is_permitted("myapp.UnsignedAgent", "agent_class")
    assert result is False
