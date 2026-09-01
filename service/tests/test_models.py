import pytest

from app.models import InvalidTransition, State, assert_transition, can_transition

ALL_STATES = list(State)

ALLOWED_PAIRS = {
    (State.inbox, State.next),
    (State.inbox, State.waiting),
    (State.inbox, State.someday),
    (State.inbox, State.done),
    (State.next, State.inbox),
    (State.next, State.waiting),
    (State.next, State.someday),
    (State.next, State.done),
    (State.waiting, State.inbox),
    (State.waiting, State.next),
    (State.waiting, State.someday),
    (State.waiting, State.done),
    (State.someday, State.inbox),
    (State.someday, State.next),
    (State.someday, State.waiting),
    (State.someday, State.done),
    (State.done, State.inbox),
    (State.done, State.next),
}


@pytest.mark.parametrize("src,dst", sorted(ALLOWED_PAIRS, key=lambda p: (p[0].value, p[1].value)))
def test_allowed_transitions(src, dst):
    assert can_transition(src, dst) is True
    assert_transition(src, dst)  # 例外にならない


@pytest.mark.parametrize(
    "src,dst",
    [(s, d) for s in ALL_STATES for d in ALL_STATES if (s, d) not in ALLOWED_PAIRS],
)
def test_disallowed_transitions(src, dst):
    assert can_transition(src, dst) is False
    with pytest.raises(InvalidTransition):
        assert_transition(src, dst)


def test_done_to_waiting_is_invalid():
    assert can_transition(State.done, State.waiting) is False
    with pytest.raises(InvalidTransition):
        assert_transition(State.done, State.waiting)


def test_done_to_someday_is_invalid():
    assert can_transition(State.done, State.someday) is False
    with pytest.raises(InvalidTransition):
        assert_transition(State.done, State.someday)


def test_same_state_transition_is_invalid():
    for s in ALL_STATES:
        assert can_transition(s, s) is False
        with pytest.raises(InvalidTransition):
            assert_transition(s, s)
