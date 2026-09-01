import pytest

from app.models import State
from app.state_labels import STATE_ALIASES, UnknownState, label, parse_state


@pytest.mark.parametrize("alias,expected", sorted(STATE_ALIASES.items()))
def test_parse_state_accepts_all_known_aliases(alias, expected):
    assert parse_state(alias) is expected


@pytest.mark.parametrize(
    "value",
    ["", "unknown", "INBOX", "done ", "終了", "next-action", "todo"],
)
def test_parse_state_raises_unknown_state_for_unrecognized_values(value):
    with pytest.raises(UnknownState):
        parse_state(value)


def test_parse_state_error_message_mentions_both_scripts():
    with pytest.raises(UnknownState) as exc_info:
        parse_state("bogus")
    message = str(exc_info.value)
    assert "受信" in message
    assert "inbox" in message


@pytest.mark.parametrize("state", list(State))
def test_label_covers_all_states(state):
    assert isinstance(label(state), str)
    assert label(state) != ""
