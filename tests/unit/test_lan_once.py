from types import SimpleNamespace
from unittest.mock import patch
from app.kobra.lan import publish_once_no_retry
from app.core.config import Settings
from app.core.service import AppService,ServiceError
import pytest
class FakeClient:
 publishes=0
 def username_pw_set(self,*a):pass
 def tls_set_context(self,*a):pass
 def connect(self,*a,**k):self.on_connect(self,None,None,0);self.on_subscribe(self,None,1,[0])
 def subscribe(self,*a,**k):return (0,1)
 def publish(self,*a,**k):self.__class__.publishes+=1;return SimpleNamespace(rc=0)
 def loop(self,*a,**k):return 0
 def disconnect(self):pass
def test_print_start_timeout_publishes_at_most_once():
 FakeClient.publishes=0
 with patch('app.kobra.lan._client',return_value=FakeClient()):
  result=publish_once_no_retry(SimpleNamespace(username='u',password='p',host='h',port=1),'q','r',{'filename':'a'},.01)
 assert result.unknown and result.sent and FakeClient.publishes==1

@pytest.mark.asyncio
async def test_physical_start_requires_two_explicit_flags(monkeypatch,tmp_path):
 monkeypatch.delenv('KOBRA_HARDWARE_TEST',raising=False)
 monkeypatch.delenv('KOBRA_ALLOW_PHYSICAL_PRINT',raising=False)
 with pytest.raises(ServiceError,match='physical print/start is disabled'):
  await AppService(Settings(data_dir=tmp_path)).print('unused')
