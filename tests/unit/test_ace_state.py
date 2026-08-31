import pytest
from app.kobra.ace import parse_ace_payload
from app.core.models import JobState
from app.core.state_machine import TransitionError,assert_transition
def test_ace_preserves_missing_fields_and_slot_mapping():
 s=parse_ace_payload({'data':{'slots':[{'materialType':'pla','color':'#010203'},{}]}})
 assert (s.normalized[0].human_slot,s.normalized[0].protocol_slot_index,s.normalized[0].rgb)==(1,0,(1,2,3))
 assert s.normalized[1].material_type is None and s.normalized[1].loaded is None
def test_no_automatic_sliced_to_print_transition():
 with pytest.raises(TransitionError):assert_transition(JobState.SLICED,JobState.UPLOADING_TO_PRINTER)
 assert_transition(JobState.STARTING,JobState.START_UNKNOWN)
