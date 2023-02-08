from enum import Enum
from typing import TypeVar, Generic, NoReturn, Callable

Type = TypeVar("Type")


class ElemState(Enum):
    INITIALIZED = 0
    UNAVAILABLE = 1
    IN_PROGRESS = 2
    ERROR = 3
    DONE = 4


class SequenceElem(Generic[Type]):

    def __init__(self, index: int, value: Type, is_available_cb: Callable[[Type], bool], state: ElemState = ElemState.INITIALIZED, outcome: bool = None) -> None:
        self.value = value
        self.index = index
        self.is_available_cb = is_available_cb
        self.is_available = lambda: is_available_cb(value)
        if state == ElemState.DONE and outcome is None:
            raise AttributeError("Every sequence element that has been evaluated should have an outcome")
        self.state = state
        self.outcome = outcome

    def update_outcome(self, outcome: bool) -> NoReturn:
        if self.state == ElemState.DONE:
            raise AttributeError(f"Outcome was already set to DONE for {repr(self)}")
        if outcome is None:
            self.state = ElemState.ERROR
        self.state = ElemState.DONE
        self.outcome = outcome

    def get_deep_copy(self, index=None):
        if index is not None:
            return SequenceElem(index, self.value, self.is_available_cb, state=self.state, outcome=self.outcome)
        else:
            return SequenceElem(self.index, self.value, self.is_available_cb, state=self.state, outcome=self.outcome)

    def __repr__(self) -> str:
        return f"{str(self.value)}: {self.state}"
