from __future__ import annotations

from enum import Enum, auto
from typing import Optional


class OrchestrationState(Enum):
    """Explicit states for the verification pipeline."""

    CREATED = auto()
    INPUT_VALIDATED = auto()
    PATCH_INSPECTED = auto()
    BASELINE_RUNNING = auto()
    PATCHED_RUNNING = auto()
    EVIDENCE_ANALYZED = auto()
    REPORT_READY = auto()

    BLOCKED = auto()
    FAILED = auto()
    INCONCLUSIVE = auto()

    def __next__(self) -> "OrchestrationState":
        """Return the next state in the default forward path."""
        transitions: dict[OrchestrationState, OrchestrationState] = {
            OrchestrationState.CREATED: OrchestrationState.INPUT_VALIDATED,
            OrchestrationState.INPUT_VALIDATED: OrchestrationState.PATCH_INSPECTED,
            OrchestrationState.PATCH_INSPECTED: OrchestrationState.BASELINE_RUNNING,
            OrchestrationState.BASELINE_RUNNING: OrchestrationState.PATCHED_RUNNING,
            OrchestrationState.PATCHED_RUNNING: OrchestrationState.EVIDENCE_ANALYZED,
            OrchestrationState.EVIDENCE_ANALYZED: OrchestrationState.REPORT_READY,
        }
        return transitions.get(self, OrchestrationState.INCONCLUSIVE)

    def can_transition_to(self, target: "OrchestrationState") -> bool:
        """Check if a transition to the target state is valid."""
        # All states can transition to BLOCKED, FAILED, or INCONCLUSIVE
        if target in (OrchestrationState.BLOCKED, OrchestrationState.FAILED, OrchestrationState.INCONCLUSIVE):
            return True
        # Forward path transitions
        return self.__next__() == target if not target == OrchestrationState.CREATED else False

    def __str__(self) -> str:
        return self.name


class Transition(Enum):
    """Transition reasons between states."""

    SUCCESS = auto()
    POLICY_VIOLATION = auto()
    INFRASTRUCTURE_ERROR = auto()
    PATCH_APPLICATION_FAILED = auto()
    MODEL_ANALYSIS_BLOCKED = auto()
    VERDICT_INCONCLUSIVE = auto()


class StateMachine:
    """Manages the verification pipeline state transitions."""

    def __init__(self):
        self._state = OrchestrationState.CREATED
        self._transition_history: list[tuple[OrchestrationState, Transition, Optional[str]]] = []
        self._metadata: dict = {}

    @property
    def state(self) -> OrchestrationState:
        """Current orchestration state."""
        return self._state

    def transition(self, target: OrchestrationState, reason: Transition, detail: Optional[str] = None) -> bool:
        """Attempt a state transition.

        Returns True if the transition was allowed, False otherwise.
        """
        if not self._state.can_transition_to(target):
            return False

        self._transition_history.append((self._state, reason, detail))
        self._state = target
        self._metadata[f"transitioned_from_{self._state.name}"] = True
        return True

    def block(self, reason: Transition, detail: Optional[str] = None) -> None:
        """Transition to BLOCKED state (e.g., policy violation)."""
        self.transition(OrchestrationState.BLOCKED, reason, detail)

    def fail(self, reason: Transition, detail: Optional[str] = None) -> None:
        """Transition to FAILED state (e.g., infrastructure error)."""
        self.transition(OrchestrationState.FAILED, reason, detail)

    def inconclusive(self, reason: Transition, detail: Optional[str] = None) -> None:
        """Transition to INCONCLUSIVE state (e.g., unreproducible issue)."""
        self.transition(OrchestrationState.INCONCLUSIVE, reason, detail)

    def metadata(self, key: str, value: object) -> None:
        """Set metadata key-value pair."""
        self._metadata[key] = value

    def get_metadata(self, key: str, default: object = None) -> object:
        """Get metadata value."""
        return self._metadata.get(key, default)

    def reset(self) -> None:
        """Reset the state machine to the initial state."""
        self._state = OrchestrationState.CREATED
        self._transition_history.clear()
        self._metadata.clear()