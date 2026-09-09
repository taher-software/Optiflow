"""Unit tests for `generate_security_code`
(`src/app/core/security_code.py::generate_security_code`) — Work Unit
`feature/strong-security-code`, Change 1 (new code format).

Exercises the function directly against `FirestoreClient(client=FakeFirestore())`
(no HTTP, no router fixtures needed) — this is a pure allocation/format
concern shared by three call sites (`routers/user/services.py`,
`routers/registration/services.py`, `routers/auth/services.py`); those call
sites get their own thin pass-through checks in
`tests/api/test_security_code_hardening.py::TestSecurityCodeFormatAtCallSites`
rather than duplicating the format assertions here.

Written test-first, before the new format is implemented. Today
`generate_security_code` still produces a 4-DECIMAL-DIGIT code (`f"{secrets.
randbelow(10000):04d}"`) and scopes the uniqueness lookup by
`{"namespace_id": ..., "security_code": ...}`. So:
  - `test_generated_code_is_exactly_four_characters` (scenario 1) already
    passes today -- a 4-digit code is also 4 characters. Called out as a
    non-regression pin, not new behavior.
  - `test_every_character_is_in_the_unambiguous_alphabet` (scenario 2) also
    already passes today -- digits are a strict subset of the 32-symbol
    alphabet and never collide with I/L/O/U, so a digit-only generator
    trivially satisfies "every character is in the alphabet, none of
    I/L/O/U appear". It stays in this suite as the scenario the developer
    validated, and because it will start actually exercising letters once
    the real alphabet is wired in.
  - `test_generator_actually_draws_from_the_whole_alphabet` (added after the
    first hand-back to close the hole the previous two tests leave open)
    FAILS today: a digit-only generator can only ever produce 10 distinct
    symbols across any number of draws, hard-failing the `>= 30 of 32`
    bound -- see the test's own docstring for the probability argument.
  - `test_uniqueness_lookup_has_no_namespace_id_filter` (scenario 3) FAILS
    today: `namespace_id` is still a key in the recorded `find_document`
    params.
  - `test_clash_forces_a_retry_and_returns_a_different_code` and
    `test_exhausting_retries_raises_500` (scenarios 4-5) already pass today
    -- the retry loop's shape (retry-on-clash, 500-on-exhaustion) is
    untouched by the format change. Non-regression pins.

No real Firestore/network touched. No timestamps involved, so time is not
frozen in this file.
"""

import pytest
from fastapi import HTTPException

from src.app.core.security_code import _MAX_CODE_ATTEMPTS, generate_security_code
from src.app.gcp.firestore import FirestoreClient
from tests.fake_firestore import FakeFirestore

# The 32-symbol unambiguous base32 alphabet mandated by the contract: digits
# plus uppercase letters excluding I, L, O, U (confusable with 1/0 on a
# phone screen). Defined locally from the contract text, not imported from
# `src/` -- there is nothing to import yet, and even once there is, a test
# must not derive its expectation from the module under test.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
AMBIGUOUS_CHARS = set("ILOU")


class _RecordingClient:
    """Wraps a real `FirestoreClient` and records every `find_document` call
    (collection name + params), delegating the actual lookup to the wrapped
    client. Everything else is forwarded unchanged."""

    def __init__(self, wrapped: FirestoreClient):
        self._wrapped = wrapped
        self.calls: list[tuple[str, dict]] = []

    def find_document(self, collection_name, params):
        self.calls.append((collection_name, dict(params)))
        return self._wrapped.find_document(collection_name, params)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


class _ClashingClient:
    """Wraps a real `FirestoreClient`; the first `clash_count` calls to
    `find_document` report a fake clash (as if another document already used
    that code) regardless of the code drawn, then it falls through to the
    real (empty) store. Lets the retry loop be forced deterministically
    without knowing which `secrets` API the implementation uses to draw the
    candidate."""

    def __init__(self, wrapped: FirestoreClient, clash_count: int):
        self._wrapped = wrapped
        self._clash_remaining = clash_count
        self.calls: list[dict] = []

    def find_document(self, collection_name, params):
        self.calls.append(dict(params))
        if self._clash_remaining > 0:
            self._clash_remaining -= 1
            return {"id": "some-other-user", **params}
        return self._wrapped.find_document(collection_name, params)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


def _real_client() -> FirestoreClient:
    return FirestoreClient(client=FakeFirestore())


class TestGenerateSecurityCodeFormat:
    """Scenario 1 & 2 -- exactly 4 characters, drawn only from the
    unambiguous 32-symbol alphabet, never I/L/O/U. Exercised over many
    generations against an empty (never-clashing) store, since a single
    draw cannot prove the codomain."""

    def test_generated_code_is_exactly_four_characters(self):
        client = _real_client()

        code = generate_security_code(client, "ns-1")

        assert len(code) == 4

    def test_every_character_is_in_the_unambiguous_alphabet(self):
        client = _real_client()

        codes = [generate_security_code(client, "ns-1") for _ in range(300)]

        all_chars = set("".join(codes))
        assert all_chars <= set(ALPHABET)
        assert not (all_chars & AMBIGUOUS_CHARS)

    def test_generator_actually_draws_from_the_whole_alphabet(self):
        """Closes a hole in the two tests above: a digit-only generator
        (today's `f"{secrets.randbelow(10000):04d}"`) trivially satisfies
        both "every character is in the alphabet" and "namespace_id is
        dropped from the lookup" without ever widening the draw beyond 10
        symbols. This test forces the widening itself to be observed, and
        also catches the opposite mistake (a widened-but-wrong alphabet,
        e.g. one that still includes I/L/O/U or lowercase) in the same run.

        Probability reasoning (why this is deterministic in practice, not a
        flaky statistical test): 500 generations x 4 characters = 2000
        independent character draws. If the implementation is correct, each
        draw is uniform over the 32-symbol alphabet, so a *specific* symbol
        is missed by all 2000 draws with probability (31/32)**2000, which is
        approximately:

            (31/32)**2000 = exp(2000 * ln(31/32))
                           ~= exp(2000 * -0.03175)
                           ~= exp(-63.5)
                           ~= 3e-28

        Union-bounding over all 32 symbols (the chance ANY one of them is
        missed by chance): 32 * 3e-28 ~= 1e-26 -- negligible many orders of
        magnitude below any flakiness budget. The assertion below only
        requires >= 30 of 32 symbols observed (not all 32) for a little
        extra slack, while still being unreachable by a generator drawing
        from a strict subset (e.g. 10 digits, or 26 unfiltered letters):
        with a true alphabet of size k < 32, at most k symbols can ever be
        observed no matter how many draws are taken, so a 10-symbol digit
        generator caps out at 10 forever and a 26-letter (no digits)
        generator caps out at 26 -- both fail the `>= 30` bound hard, not by
        bad luck.
        """
        client = _real_client()

        codes = [generate_security_code(client, "ns-1") for _ in range(500)]

        observed = set("".join(codes))
        assert observed <= set(ALPHABET), (
            f"observed characters outside the 32-symbol alphabet: "
            f"{observed - set(ALPHABET)!r}"
        )
        assert len(observed) >= 30, (
            f"only {len(observed)} distinct symbols observed over 2000 draws "
            f"({sorted(observed)!r}) -- the generator is not drawing from "
            "the full 32-symbol alphabet"
        )


class TestGenerateSecurityCodeUniquenessIsGlobal:
    """Scenario 3 -- the uniqueness lookup passed to Firestore carries only
    `security_code`, never `namespace_id`: the pairing lookup in
    `auth/services.py` searches globally with no tenant context, so a
    per-namespace guarantee was never enough."""

    def test_uniqueness_lookup_has_no_namespace_id_filter(self):
        wrapped = _real_client()
        spy = _RecordingClient(wrapped)

        generate_security_code(spy, "ns-1")

        assert len(spy.calls) == 1
        collection_name, params = spy.calls[0]
        assert "namespace_id" not in params
        assert set(params.keys()) == {"security_code"}


class TestGenerateSecurityCodeRetriesOnClash:
    """Scenario 4 & 5 -- retry loop shape, already correct today and
    expected to keep passing unchanged (called out as a non-regression pin
    in the hand-back, not new behavior)."""

    def test_clash_forces_a_retry_and_returns_a_different_code(self):
        wrapped = _real_client()
        clashing = _ClashingClient(wrapped, clash_count=1)

        code = generate_security_code(clashing, "ns-1")

        assert len(clashing.calls) == 2
        first_attempt = clashing.calls[0]["security_code"]
        second_attempt = clashing.calls[1]["security_code"]
        assert first_attempt != second_attempt
        assert code == second_attempt

    def test_exhausting_retries_raises_500(self):
        wrapped = _real_client()
        always_clashing = _ClashingClient(wrapped, clash_count=_MAX_CODE_ATTEMPTS)

        with pytest.raises(HTTPException) as exc_info:
            generate_security_code(always_clashing, "ns-1")

        assert exc_info.value.status_code == 500
        assert len(always_clashing.calls) == _MAX_CODE_ATTEMPTS
