from .models import JobState


class TransitionError(ValueError):
    pass


_NEXT = {
    JobState.UPLOADED: {JobState.INSPECTING, JobState.FAILED},
    JobState.INSPECTING: {JobState.READY_TO_SLICE, JobState.FAILED},
    JobState.READY_TO_SLICE: {JobState.SLICING, JobState.CANCELLED, JobState.EXPIRED},
    JobState.SLICING: {JobState.SLICED, JobState.FAILED, JobState.FAILED_RECOVERABLE},
    JobState.FAILED_RECOVERABLE: {
        JobState.READY_TO_SLICE,
        JobState.CANCELLED,
        JobState.EXPIRED,
    },
    JobState.SLICED: {JobState.AWAITING_CONFIRMATION, JobState.READY_TO_SLICE},
    JobState.AWAITING_CONFIRMATION: {
        JobState.PREFLIGHT,
        JobState.READY_TO_SLICE,
        JobState.CANCELLED,
        JobState.EXPIRED,
    },
    JobState.PREFLIGHT: {
        JobState.AWAITING_CONFIRMATION,
        JobState.UPLOADING_TO_PRINTER,
        JobState.FAILED,
    },
    JobState.UPLOADING_TO_PRINTER: {
        JobState.UPLOADED_TO_PRINTER,
        JobState.FAILED,
        JobState.FAILED_RECOVERABLE,
    },
    JobState.UPLOADED_TO_PRINTER: {
        JobState.STARTING,
        JobState.FAILED,
        JobState.AWAITING_CONFIRMATION,
    },
    JobState.STARTING: {JobState.PRINT_ACCEPTED, JobState.START_UNKNOWN},
    JobState.START_UNKNOWN: {
        JobState.PRINT_ACCEPTED,
        JobState.MONITORING,
        JobState.START_REJECTED,
        JobState.CANCELLED,
        JobState.FAILED_RECOVERABLE,
    },
    JobState.PRINT_ACCEPTED: {
        JobState.MONITORING,
        JobState.PRINTING,
        JobState.PAUSED,
        JobState.COMPLETED,
        JobState.CANCELLED,
        JobState.FAILED,
    },
    JobState.MONITORING: {
        JobState.PRINTING,
        JobState.PAUSED,
        JobState.COMPLETED,
        JobState.CANCELLED,
        JobState.FAILED,
    },
    JobState.PRINTING: {
        JobState.PAUSED,
        JobState.COMPLETED,
        JobState.CANCELLED,
        JobState.FAILED,
    },
    JobState.PAUSED: {JobState.PRINTING, JobState.CANCELLED, JobState.FAILED},
}


def assert_transition(source: JobState, target: JobState) -> None:
    if target not in _NEXT.get(source, set()):
        raise TransitionError(
            f"dangerous/invalid transition {source.value} -> {target.value}"
        )
