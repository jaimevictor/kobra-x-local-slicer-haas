"""Real Orca test; executed only by scripts/golden_slice.sh or CI's Docker job."""
import asyncio
import os
import zipfile
from pathlib import Path
import pytest
from app.core.models import Orientation
from app.slicer.gcode import inspect_gcode
from app.slicer.orca import OrcaRunner
from app.slicer.three_mf import sanitize_3mf_for_slicing

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

def test_golden_sanitized_3mf_with_supports_enabled(tmp_path):
 model=b'''<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources><object id="1" type="model"><mesh><vertices><vertex x="0" y="0" z="0"/><vertex x="20" y="0" z="0"/><vertex x="20" y="20" z="0"/><vertex x="0" y="20" z="0"/><vertex x="0" y="0" z="20"/><vertex x="20" y="0" z="20"/><vertex x="20" y="20" z="20"/><vertex x="0" y="20" z="20"/></vertices><triangles><triangle v1="0" v2="2" v3="1"/><triangle v1="0" v2="3" v3="2"/><triangle v1="4" v2="5" v3="6"/><triangle v1="4" v2="6" v3="7"/><triangle v1="0" v2="1" v3="5"/><triangle v1="0" v2="5" v3="4"/><triangle v1="1" v2="2" v3="6"/><triangle v1="1" v2="6" v3="5"/><triangle v1="2" v2="3" v3="7"/><triangle v1="2" v2="7" v3="6"/><triangle v1="3" v2="0" v3="4"/><triangle v1="3" v2="4" v3="7"/></triangles></mesh></object></resources><build><item objectid="1"/></build></model>'''
 source=tmp_path/'source.3mf'
 with zipfile.ZipFile(source,'w') as archive:
  archive.writestr('[Content_Types].xml',b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/3D/3dmodel.model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/><Override PartName="/Metadata/model_settings.config" ContentType="text/xml"/></Types>')
  archive.writestr('_rels/.rels',b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
  archive.writestr('3D/3dmodel.model',model)
  archive.writestr('Metadata/model_settings.config',b'<config><plate><metadata key="plater_id" value="1"/><model_instance/></plate></config>')
  archive.writestr('3D/_rels/3dmodel.model.rels',b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/Metadata/model_settings.config" Id="rel1" Type="settings"/></Relationships>')
 sanitized=tmp_path/'sanitized.3mf'
 sanitize_3mf_for_slicing(source,sanitized,max_decompressed=32*1024*1024)
 runner=OrcaRunner(Path('/opt/kobra/profiles/resolved'),600,512*1024*1024)
 output_dir=tmp_path/'slice';output_dir.mkdir()
 output=asyncio.run(runner.slice(sanitized,output_dir,Orientation.ORIGINAL,True))
 assert output.stat().st_size>0
