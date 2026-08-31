import pytest
from app.slicer.gcode import GCodeValidationError,inspect_gcode
PROFILE={'nozzle_temperature_range_low':[190],'nozzle_temperature_range_high':[230],'cool_plate_temp':[60],'cool_plate_temp_initial_layer':[60]}
GOOD='; total layer number = 2\nG9111 BEDTEMP=60 EXTRUDERTEMP=210\nM104 S210\nM140 S60\nG90\nM82\nG1 X0 Y0 Z0.2 E1\n;LAYER:1\nG1 X20 Y20 Z0.4 E2\n'
def inspect(tmp_path,text):p=tmp_path/'x.gcode';p.write_text(text);return inspect_gcode(p,filament_profile=PROFILE,gcode_limit_bytes=10000,orca_version='2.4.2')
def test_gcode_temperature_dimensions_and_marker(tmp_path):assert inspect(tmp_path,GOOD).stats.dimensions.size==(20.0,20.0,0.2)
@pytest.mark.parametrize('line',["M600\n","T1\n"])
def test_gcode_blocks_tool_changes(tmp_path,line):
 with pytest.raises(GCodeValidationError):inspect(tmp_path,GOOD+line)
def test_gcode_blocks_temperature(tmp_path):
 with pytest.raises(GCodeValidationError):inspect(tmp_path,GOOD.replace('S210','S250'))
