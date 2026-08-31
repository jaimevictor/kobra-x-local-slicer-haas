import json
import pytest
from app.slicer.profile_resolver import ProfileError,resolve_profile
def write(path,name,payload):
 p=path/f'{name}.json';p.write_text(json.dumps(payload));return p
def test_profile_resolver_merges_root_first(tmp_path):
 write(tmp_path,'root',{'name':'root','value':1,'shared':'root'})
 child=write(tmp_path,'child',{'inherits':'root','value':2})
 assert resolve_profile(child,tmp_path)=={'name':'root','value':2,'shared':'root'}
def test_profile_resolver_rejects_circular_inheritance(tmp_path):
 first=write(tmp_path,'first',{'inherits':'second'})
 write(tmp_path,'second',{'inherits':'first'})
 with pytest.raises(ProfileError,match='circular'):
  resolve_profile(first,tmp_path)
