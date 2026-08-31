from .models import JobState

class TransitionError(ValueError): pass

_NEXT = {
 JobState.UPLOADED:{JobState.INSPECTING,JobState.FAILED}, JobState.INSPECTING:{JobState.READY_TO_SLICE,JobState.FAILED},
 JobState.READY_TO_SLICE:{JobState.SLICING,JobState.CANCELLED,JobState.EXPIRED}, JobState.SLICING:{JobState.SLICED,JobState.FAILED},
 JobState.SLICED:{JobState.AWAITING_CONFIRMATION,JobState.READY_TO_SLICE}, JobState.AWAITING_CONFIRMATION:{JobState.PREFLIGHT,JobState.READY_TO_SLICE,JobState.CANCELLED,JobState.EXPIRED},
 JobState.PREFLIGHT:{JobState.AWAITING_CONFIRMATION,JobState.UPLOADING_TO_PRINTER,JobState.FAILED}, JobState.UPLOADING_TO_PRINTER:{JobState.UPLOADED_TO_PRINTER,JobState.FAILED},
 JobState.UPLOADED_TO_PRINTER:{JobState.STARTING,JobState.FAILED}, JobState.STARTING:{JobState.PRINT_ACCEPTED,JobState.START_UNKNOWN},
 JobState.START_UNKNOWN:{JobState.PRINT_ACCEPTED,JobState.MONITORING}, JobState.PRINT_ACCEPTED:{JobState.MONITORING}, JobState.MONITORING:{JobState.FAILED},
}
def assert_transition(source: JobState, target: JobState) -> None:
    if target not in _NEXT.get(source, set()): raise TransitionError(f"dangerous/invalid transition {source.value} -> {target.value}")
