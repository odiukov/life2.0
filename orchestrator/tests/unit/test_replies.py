import pytest
from orchestrator.domain.replies import classify_reply


@pytest.mark.parametrize(
    "text",
    [
        "да",
        "Да!",
        "  ок ",
        "Окей.",
        "ага 👍",
        "давай",
        "конечно",
        "yes",
        "OK",
        "okay!",
        "sure",
        "yep",
    ],
)
def test_confirmations(text: str) -> None:
    assert classify_reply(text) == "confirm"


@pytest.mark.parametrize("text", ["нет", "Не надо.", "отмена", "отмени", "no", "Nope", "cancel!"])
def test_rejections(text: str) -> None:
    assert classify_reply(text) == "reject"


@pytest.mark.parametrize(
    "text",
    [
        "да, но в 19:00",
        "давай завтра",
        "ок, а что ещё?",
        "yes please move it",
        "",
        "😀",
        "нет света в спальне",
    ],
)
def test_anything_longer_goes_to_the_model(text: str) -> None:
    assert classify_reply(text) is None


@pytest.mark.parametrize("text", ["y👍es", "😀yes", "y$es"])
def test_symbols_inside_or_before_words_are_not_confirmation(text: str) -> None:
    assert classify_reply(text) is None


@pytest.mark.parametrize("text", ["yes ❤️", "да 👍🏽!", "ok ✅"])
def test_trailing_emoji_are_removed(text: str) -> None:
    assert classify_reply(text) == "confirm"
