"""
Status tracking for the organization of events

Apps can register phases (e.g., basic configuration, submission, plan creation, ...) and steps belonging to these
phases (e.g., create rooms, transfer AK list to wiki) with the singleton :data:`status_tracker`,
usually in the ``ready()`` method of their app config::

    from AKModel.status_tracking import status_tracker

    status_tracker.register_phase("submission", _("Submission"), order=20)
    status_tracker.register_step("submission", "wiki_export", _("Transfer AK list to wiki"), order=10)

Phases and steps can be registered in any order and by any app; a step may belong to a phase registered by another
app. Steps of phases that are never registered are ignored.

The progress of a step for a given event is tracked in the database using
:class:`AKModel.models.StatusTrackingEntry`. There may be multiple entries per step, the most recent one
determines the current progress. Steps without any entries are considered as not started, hence there is no need to
create entries for all steps upfront. Steps that can be skipped for a specific event can be marked as not needed.
A phase is complete once all of its steps are either done or not needed.
"""
import re
from dataclasses import dataclass
from datetime import datetime

from django.db.models import OuterRef, Subquery

from AKModel.models import Event, StatusTrackingEntry

Progress = StatusTrackingEntry.Progress

_KEY_PATTERN = re.compile(r'^[-a-zA-Z0-9_]{1,64}$')


def _validate_key(key: str, kind: str):
    if not isinstance(key, str) or not _KEY_PATTERN.match(key):
        raise ValueError(f"Invalid {kind} key '{key}': Only letters, numbers, dashes and underscores "
                         f"(at most 64 characters) are allowed")


@dataclass(frozen=True)
class Phase:
    """
    A phase in the organization of an event (e.g., basic_configuration)
    """
    key: str
    name: str
    order: int = 0
    description: str = ""


@dataclass(frozen=True)
class Step:
    """
    A step belonging to a phase (e.g., create categories)

    Mandatory steps have to be done for the phase to be complete, optional ones may be skipped.
    """
    phase: str
    key: str
    name: str
    order: int = 0
    description: str = ""
    mandatory: bool = False


@dataclass(frozen=True)
class StepStatus:
    """
    Current status of a step for an event

    ``entry`` is the most recent :class:`AKModel.models.StatusTrackingEntry` for this step
    or ``None`` if no progress was recorded yet (step not started).
    """
    step: Step
    entry: StatusTrackingEntry | None = None

    @property
    def progress(self) -> str:
        """
        Current progress of this step (one of :class:`AKModel.models.StatusTrackingEntry.Progress`)
        """
        return Progress(self.entry.progress) if self.entry is not None else Progress.NOT_STARTED

    @property
    def detail(self) -> str:
        """
        Detail text of the most recent progress entry (empty if there is none)
        """
        return self.entry.detail if self.entry is not None else ""

    @property
    def timestamp(self) -> datetime | None:
        """
        Time the most recent progress was recorded (None if there is none)
        """
        return self.entry.timestamp if self.entry is not None else None

    @property
    def completed(self) -> bool:
        """
        Is this step completed, i.e., done or not needed for this event?
        """
        return self.progress in Progress.completed_states()

    @property
    def missing(self) -> bool:
        """
        Is this a mandatory step that is not completed (done or not needed) yet?
        """
        return self.step.mandatory and not self.completed


class ProgressReport(list):
    """
    List of :class:`StepStatus` objects, additionally reporting missing mandatory steps and completion
    """

    @property
    def missing_mandatory_steps(self) -> list[StepStatus]:
        """
        :return: status of all mandatory steps in this report that are not completed (done or not needed) yet
        """
        return [status for status in self if status.missing]

    @property
    def missing_mandatory(self) -> int:
        """
        :return: number of mandatory steps in this report that are not completed (done or not needed) yet
        """
        return len(self.missing_mandatory_steps)

    @property
    def open_steps(self) -> list[StepStatus]:
        """
        :return: status of all steps (mandatory or not) in this report that are neither done nor not needed
        """
        return [status for status in self if not status.completed]

    @property
    def complete(self) -> bool:
        """
        :return: are all steps in this report either done or not needed? (True if there are no steps at all)
        """
        return all(status.completed for status in self)


class FractionReport(dict):
    """
    Dict mapping every progress state to the fraction of steps in that state,
    additionally reporting the number of missing mandatory steps and whether all steps are completed
    """

    def __init__(self, fractions: dict[str, float], missing_mandatory: int, complete: bool):
        super().__init__(fractions)
        self.missing_mandatory = missing_mandatory
        self.complete = complete

    @property
    def completed(self) -> float:
        """
        :return: fraction of steps that are completed, i.e., either done or not needed
        """
        return sum(self[p] for p in Progress.completed_states())


class StatusTracker:
    """
    Registry for phases and steps of the event organization and helpers to query their progress
    """

    def __init__(self):
        self._phases: dict[str, Phase] = {}
        self._steps: dict[str, dict[str, Step]] = {}

    # Registration

    def register_phase(self, key: str, name: str, *, order: int = 0, description: str = "") -> Phase:
        """
        Register a new phase

        :param key: unique key of the phase (stored in the database)
        :param name: human-readable (translatable) name of the phase
        :param order: phases are sorted by this value (and then by key)
        :param description: optional description
        :return: the registered phase
        :raises ValueError: if the key is invalid or already used by another phase
        """
        _validate_key(key, "phase")
        if key in self._phases:
            raise ValueError(f"Phase '{key}' is already registered")
        phase = Phase(key=key, name=name, order=order, description=description)
        self._phases[key] = phase
        return phase

    def register_step(self, phase: str, key: str, name: str, *, order: int = 0, description: str = "",
                      mandatory: bool = False) -> Step:
        """
        Register a new step for a phase

        The phase does not need to be registered yet (to keep apps independent of loading order).

        :param phase: key of the phase this step belongs to
        :param key: key of the step (unique within the phase, stored in the database)
        :param name: human-readable (translatable) name of the step
        :param order: steps are sorted by this value (and then by key) within their phase
        :param description: optional description
        :param mandatory: does this step have to be done for the phase to be complete?
        :return: the registered step
        :raises ValueError: if a key is invalid or the step is already registered for this phase
        """
        _validate_key(phase, "phase")
        _validate_key(key, "step")
        steps = self._steps.setdefault(phase, {})
        if key in steps:
            raise ValueError(f"Step '{key}' is already registered for phase '{phase}'")
        step = Step(phase=phase, key=key, name=name, order=order, description=description, mandatory=mandatory)
        steps[key] = step
        return step

    # Access to registered phases and steps

    def get_phases(self) -> list[Phase]:
        """
        :return: all registered phases, ordered
        """
        return sorted(self._phases.values(), key=lambda p: (p.order, p.key))

    def get_phase(self, phase: str) -> Phase:
        """
        :param phase: key of the phase
        :return: the phase with this key
        :raises KeyError: if there is no such phase
        """
        try:
            return self._phases[phase]
        except KeyError as e:
            raise KeyError(f"Unknown phase '{phase}'") from e

    def get_steps(self, phase: str | None = None) -> list[Step]:
        """
        :param phase: key of a phase to restrict the result to (or None for steps of all registered phases)
        :return: steps (of the given phase or all registered phases), ordered by phase and step order
        :raises KeyError: if the given phase is not registered
        """
        phases = [self.get_phase(phase)] if phase is not None else self.get_phases()
        return [step
                for p in phases
                for step in sorted(self._steps.get(p.key, {}).values(), key=lambda s: (s.order, s.key))]

    def get_step(self, phase: str, step: str) -> Step:
        """
        :param phase: key of the phase
        :param step: key of the step
        :return: the step identified by these keys
        :raises KeyError: if phase or step are not registered
        """
        self.get_phase(phase)
        try:
            return self._steps[phase][step]
        except KeyError as e:
            raise KeyError(f"Unknown step '{step}' for phase '{phase}'") from e

    # Recording progress

    def record(self, event: Event, phase: str, step: str, progress: str, *,
               detail: str = "") -> StatusTrackingEntry:
        """
        Record a new progress increment for a step

        :param event: event the progress belongs to
        :param phase: key of the phase
        :param step: key of the step
        :param progress: new progress (one of :class:`AKModel.models.StatusTrackingEntry.Progress`)
        :param detail: optional detail text
        :return: the created entry
        :raises KeyError: if phase or step are not registered
        :raises ValueError: if the progress value is invalid
        """
        self.get_step(phase, step)
        return StatusTrackingEntry.objects.create(event=event, phase=phase, step=step,
                                                  progress=Progress(progress), detail=detail)

    def record_if_registered(self, event: Event, phase: str, step: str, progress: str, *,
                             detail: str = "") -> StatusTrackingEntry | None:
        """
        Record a new progress increment for a step if this step is registered

        Use this for steps registered by other (optional) apps, e.g., when a view in one app performs
        a step that is registered by another app which might not be installed.
        Parameters are the same as for :meth:`record`.

        :return: the created entry or None if phase or step are not registered
        :raises ValueError: if the progress value is invalid
        """
        try:
            self.get_step(phase, step)
        except KeyError:
            return None
        return self.record(event, phase, step, progress, detail=detail)

    # Querying progress

    def get_history(self, event: Event, phase: str, step: str):
        """
        :return: queryset of all progress entries of the given step, most recent first
        """
        return StatusTrackingEntry.objects.filter(event=event, phase=phase, step=step).order_by('-timestamp', '-pk')

    @staticmethod
    def _latest_entries(event: Event, phase: str | None = None) -> dict[tuple[str, str], StatusTrackingEntry]:
        """
        Retrieve the most recent entry per step with a single query

        :return: dict mapping (phase key, step key) to the most recent entry
        """
        latest_pk = (StatusTrackingEntry.objects
                     .filter(event=OuterRef('event'), phase=OuterRef('phase'), step=OuterRef('step'))
                     .order_by('-timestamp', '-pk')
                     .values('pk')[:1])
        entries = StatusTrackingEntry.objects.filter(event=event, pk=Subquery(latest_pk))
        if phase is not None:
            entries = entries.filter(phase=phase)
        return {(e.phase, e.step): e for e in entries}

    def get_progress(self, event: Event, phase: str | None = None) -> ProgressReport:
        """
        Get the current status of all steps (of all phases or of one phase)

        :param event: event to get the progress for
        :param phase: optional key of a phase to restrict the result to
        :return: list of :class:`StepStatus`, ordered by phase and step.
                 Its attribute ``missing_mandatory`` holds the number of mandatory steps that are not completed yet,
                 ``complete`` tells whether all steps are either done or not needed.
        """
        steps = self.get_steps(phase)
        latest = self._latest_entries(event, phase)
        return ProgressReport(StepStatus(step=s, entry=latest.get((s.phase, s.key))) for s in steps)

    def get_phase_progress(self, event: Event, phase: str) -> ProgressReport:
        """
        Get the current status of all steps of the given phase

        :param event: event to get the progress for
        :param phase: key of the phase
        :return: list of :class:`StepStatus`, ordered by step.
                 Its attribute ``missing_mandatory`` holds the number of mandatory steps that are not completed yet,
                 ``complete`` tells whether the phase is complete (all steps are either done or not needed).
        """
        return self.get_progress(event, phase)

    def is_phase_complete(self, event: Event, phase: str) -> bool:
        """
        Check whether a phase is complete, i.e., whether all of its steps are either done or not needed

        :param event: event to check the progress for
        :param phase: key of the phase
        :return: True if the phase is complete (also for phases without steps)
        """
        return self.get_phase_progress(event, phase).complete

    def get_phase_completion(self, event: Event) -> dict[str, bool]:
        """
        Check for all registered phases whether they are complete (with a single query)

        :param event: event to check the progress for
        :return: dict mapping the key of every registered phase (ordered) to its completion state
        """
        completion = {phase.key: True for phase in self.get_phases()}
        for status in self.get_progress(event):
            if not status.completed:
                completion[status.step.phase] = False
        return completion

    def get_phase_fractions(self, event: Event, phase: str) -> FractionReport:
        """
        Get the fractions of steps of the given phase per progress state

        :param event: event to get the progress for
        :param phase: key of the phase
        :return: dict mapping every progress state to the fraction (0.0 to 1.0) of steps in that state.
                 For phases without steps, all fractions are 0.0.
                 Its attribute ``missing_mandatory`` holds the number of mandatory steps that are not completed yet,
                 ``complete`` tells whether the phase is complete (all steps are either done or not needed)
                 and ``completed`` holds the fraction of steps that are done or not needed.
        """
        statuses = self.get_phase_progress(event, phase)
        counts = {p: 0 for p in Progress}
        for status in statuses:
            counts[status.progress] += 1
        total = len(statuses)
        return FractionReport({p: (c / total if total > 0 else 0.0) for p, c in counts.items()},
                              missing_mandatory=statuses.missing_mandatory, complete=statuses.complete)


# create one instance of the :class:`StatusTracker` that can be accessed everywhere (singleton pattern)
status_tracker = StatusTracker()
