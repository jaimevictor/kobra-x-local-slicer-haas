from __future__ import annotations
import os
from typing import Any
import httpx
import aiohttp
from pydantic import BaseModel,Field
class HomeAssistantError(RuntimeError):pass
class HAStatus(BaseModel):
 online:bool|None=None;available:bool|None=None;busy:bool|None=None;job_in_progress:bool|None=None;state:str|None=None;filename:str|None=None;current_fault:bool|None=None;error_states:dict[str,str]=Field(default_factory=dict)
class HomeAssistantClient:
 def __init__(self):
  self.token=os.getenv('SUPERVISOR_TOKEN','')
  if not self.token: raise HomeAssistantError('SUPERVISOR_TOKEN unavailable')
 async def discover_anycubic_devices(self) -> list[dict[str, Any]]:
  """Read registries through Supervisor's authenticated WebSocket, never a user token."""
  async with aiohttp.ClientSession() as session:
   async with session.ws_connect('ws://supervisor/core/websocket',timeout=8) as ws:
    hello=await ws.receive_json()
    if hello.get('type')!='auth_required': raise HomeAssistantError('unexpected Home Assistant WebSocket greeting')
    await ws.send_json({'type':'auth','access_token':self.token})
    if (await ws.receive_json()).get('type')!='auth_ok': raise HomeAssistantError('Supervisor token was not accepted')
    async def command(message_id:int,command_type:str):
     await ws.send_json({'id':message_id,'type':command_type})
     response=await ws.receive_json()
     if not response.get('success'): raise HomeAssistantError(f'Home Assistant {command_type} failed')
     return response.get('result',[])
    devices=await command(1,'config/device_registry/list'); entities=await command(2,'config/entity_registry/list')
  candidates=[]
  for device in devices:
   if not isinstance(device,dict) or not any(i[0]=='anycubic_cloud' for i in device.get('identifiers',[]) if isinstance(i,(list,tuple)) and i): continue
   rows=[e for e in entities if isinstance(e,dict) and e.get('device_id')==device.get('id')]
   candidates.append({'device_id':device['id'],'name':device.get('name_by_user') or device.get('name') or device['id'],'entities':[{'entity_id':e['entity_id'],'translation_key':e.get('translation_key')} for e in rows],'suggested_map':{},'unresolved_roles':['online','available','busy','job_in_progress','state','filename']})
  return candidates
 async def cross_check(self,mapping:dict[str,Any])->HAStatus:
  headers={'Authorization':f'Bearer {self.token}'}
  try:
   async with httpx.AsyncClient(timeout=8) as c:
    states={}
    for role,eid in mapping.items():
     if role=='error_entities':continue
     if not isinstance(eid,str):continue
     r=await c.get(f'http://supervisor/core/api/states/{eid}',headers=headers);r.raise_for_status(); states[role]=r.json().get('state')
  except httpx.HTTPError as exc: raise HomeAssistantError(str(exc)) from exc
  def boolean(v): return None if v is None else str(v).lower() in {'on','true','available','idle','ready'}
  return HAStatus(online=boolean(states.get('online')),available=boolean(states.get('available')),busy=boolean(states.get('busy')) if 'busy'in states else None,job_in_progress=boolean(states.get('job_in_progress')) if 'job_in_progress'in states else None,state=states.get('state'),filename=states.get('filename'),current_fault=boolean(states.get('current_fault')) if 'current_fault'in states else None)
def new_errors(current:dict[str,str],baseline:dict[str,str])->dict[str,str]:return {k:v for k,v in current.items() if baseline.get(k)!=v}
