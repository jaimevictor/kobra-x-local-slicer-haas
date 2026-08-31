"""Real Orca test; executed only by scripts/golden_slice.sh or CI's Docker job."""
import asyncio
import os
from pathlib import Path
import pytest
from app.core.models import Orientation
from app.slicer.gcode import inspect_gcode
from app.slicer.orca import OrcaRunner

pytestmark=pytest.mark.skipif(os.getenv('ORCA_GOLDEN')!='1',reason='requires verified Orca image')

def test_golden_cube(tmp_path):
 runner=OrcaRunner(Path('/opt/kobra/profiles/resolved'),600,512*1024*1024)
 output=asyncio.run(runner.slice(Path('/tests/fixtures/20mm_cube.stl'),tmp_path,Orientation.ORIGINAL))
 analysis=inspect_gcode(output,filament_profile=runner.load_filament_profile(),gcode_limit_bytes=512*1024*1024,orca_version=runner.version,profile_manifest_sha256=runner.manifest_sha256(),profile_versions=runner.profile_versions())
 assert output.stat().st_size>0
 assert analysis.has_g9111 and not analysis.has_m600 and analysis.tools<= {0}
 assert analysis.stats.dimensions.size[0]<=20.1 and analysis.stats.dimensions.size[1]<=20.1
 assert analysis.stats.gcode_sha256 and analysis.stats.profile_manifest_sha256

def test_golden_cube_with_supports_enabled(tmp_path):
 runner=OrcaRunner(Path('/opt/kobra/profiles/resolved'),600,512*1024*1024)
 output=asyncio.run(runner.slice(Path('/tests/fixtures/20mm_cube.stl'),tmp_path,Orientation.ORIGINAL,True))
 assert output.stat().st_size>0
 assert (tmp_path/'process_with_supports.json').is_file()
