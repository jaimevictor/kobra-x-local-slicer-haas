import pytest
from app.core.security import SecurityError,sanitize_filename,validate_upload_url
from app.kobra.upload import UploadError,validate_upload_response
def test_filename_sanitizer():
 assert sanitize_filename('../../cube.stl',allowed_extensions={'.stl'})=='cube.stl'
 with pytest.raises(SecurityError):sanitize_filename('cube.exe',allowed_extensions={'.stl'})
def test_upload_url_ssrf():
 validate_upload_url('http://192.168.1.4:18910/gcode_upload?s=secret','192.168.1.4')
 for url in ('https://192.168.1.4:18910/gcode_upload?s=x','http://example.com:18910/gcode_upload?s=x','http://192.168.1.4:18910/else?s=x','http://192.168.1.4:18910/gcode_upload'):
  with pytest.raises(SecurityError):validate_upload_url(url,'192.168.1.4')
def test_upload_response():
 validate_upload_response(200,{'code':200,'data':{'gcode':'a.gcode'}},'a.gcode')
 with pytest.raises(UploadError):validate_upload_response(200,{'code':200,'data':{'gcode':'b'}},'a.gcode')
