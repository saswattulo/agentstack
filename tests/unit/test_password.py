import pytest

from agentstack.services.password import hash_password, needs_rehash, verify_password


@pytest.mark.unit
def test_hash_then_verify_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True


@pytest.mark.unit
def test_verify_rejects_wrong_password():
    h = hash_password("good-pass-123")
    assert verify_password("bad-pass-456", h) is False


@pytest.mark.unit
def test_each_hash_is_unique_due_to_salt():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2


@pytest.mark.unit
def test_needs_rehash_false_for_fresh_hash():
    h = hash_password("anything")
    assert needs_rehash(h) is False
