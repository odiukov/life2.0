import hashlib

import pytest
from household.domain.errors import InviteInvalid
from household.domain.invite import ALPHABET, InviteCode


def test_generate_uses_crockford_alphabet_and_eight_chars() -> None:
    picks = iter(range(8))
    code = InviteCode.generate(randbelow=lambda n: next(picks))
    assert code.value == ALPHABET[:8] == "01234567"
    assert code.display == "0123-4567"


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ("abcd-ef12", "ABCDEF12"),
        (" ABCD EF12 ", "ABCDEF12"),
        ("oIlL-0000", "0111" + "0000"),
    ],
)
def test_parse_normalizes_case_separators_and_lookalikes(raw: str, value: str) -> None:
    assert InviteCode.parse(raw).value == value


@pytest.mark.parametrize("raw", ["", "ABC", "ABCDEFGHJ", "ABCD-EF1U", "ABCD-EF1!"])
def test_parse_rejects_wrong_length_or_letters(raw: str) -> None:
    with pytest.raises(InviteInvalid):
        InviteCode.parse(raw)


def test_digest_is_sha256_of_the_normalized_value() -> None:
    assert InviteCode.parse("abcd-ef12").digest() == hashlib.sha256(b"ABCDEF12").digest()
