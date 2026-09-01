from __future__ import annotations
import logging
from fastapi import APIRouter,File,HTTPException,Request,UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.core.models import Orientation
from app.core.security import validate_printer_host
from app.kobra.lan import KobraLanSession
from app.ha.client import HomeAssistantClient

router=APIRouter()
LOGGER=logging.getLogger(__name__)
def svc(request:Request):return request.app.state.service
def error(exc:Exception):
 LOGGER.warning('Kobra API request rejected: %s',exc)
 raise HTTPException(400,str(exc)) from exc
class OrientationInput(BaseModel):orientation:Orientation
class SupportInput(BaseModel):enabled:bool
class SlotInput(BaseModel):human_slot:int
class ConfirmInput(BaseModel):gcode_sha256:str;table_clear:bool
class ConfigInput(BaseModel):printer_host:str;ha_device_id:str;ha_entity_map:dict={};ha_ace_entity_map:dict={}
@router.get('/health')
async def health(request:Request):
 s=request.app.state.settings; return {'ok':True,'printer_host_configured':bool(s.printer_host),'lan_connected':bool(svc(request).lan and svc(request).lan.connected)}
@router.get('/config')
async def config(request:Request): return {'printer_host':request.app.state.settings.printer_host}
@router.put('/config')
async def set_config(body:ConfigInput,request:Request):
 try:
  required={'online','available','busy','job_in_progress','state','filename'}
  if not body.ha_device_id or required-set(body.ha_entity_map): raise ValueError('safety-critical Home Assistant role mappings are required')
  s=request.app.state.settings;s.printer_host=validate_printer_host(body.printer_host);s.ha_device_id=body.ha_device_id;s.ha_entity_map=body.ha_entity_map;s.ha_ace_entity_map=body.ha_ace_entity_map;s.save_config()
  old=svc(request).lan
  if old: await old.close()
  svc(request).lan=KobraLanSession(s.printer_host)
  return {'ok':True}
 except Exception as exc:error(exc)
@router.get('/onboarding/discover')
async def discover_home_assistant():
 try:return await HomeAssistantClient().discover_anycubic_devices()
 except Exception as exc:error(exc)
@router.post('/jobs')
async def create(file:UploadFile=File(...),request:Request=None):
 try:return await svc(request).create_job(file)
 except Exception as exc:error(exc)
@router.get('/jobs/{job_id}')
async def job(job_id:str,request:Request):
 try:return svc(request).job(job_id)
 except Exception as exc:error(exc)
@router.get('/jobs/{job_id}/ace')
async def ace(job_id:str,request:Request):
 try:return await svc(request).ace(job_id)
 except Exception as exc:error(exc)
@router.post('/jobs/{job_id}/slot')
async def slot(job_id:str,body:SlotInput,request:Request):
 try:return await svc(request).select_slot(job_id,body.human_slot)
 except Exception as exc:error(exc)
@router.post('/jobs/{job_id}/orientation')
async def orientation(job_id:str,body:OrientationInput,request:Request):
 try:
  job,preview=await svc(request).set_orientation(job_id,body.orientation);return {'job':job,'preview_file':preview}
 except Exception as exc:error(exc)
@router.post('/jobs/{job_id}/supports')
async def supports(job_id:str,body:SupportInput,request:Request):
 try:return svc(request).set_supports(job_id,body.enabled)
 except Exception as exc:error(exc)
@router.post('/jobs/{job_id}/slice')
async def slice_job(job_id:str,request:Request):
 try:return await svc(request).slice(job_id)
 except Exception as exc:error(exc)
@router.post('/jobs/{job_id}/confirm')
async def confirm(job_id:str,body:ConfirmInput,request:Request):
 try:return svc(request).confirm(job_id,body.gcode_sha256,body.table_clear)
 except Exception as exc:error(exc)
@router.post('/jobs/{job_id}/print')
async def print_job(job_id:str,request:Request):
 try:return await svc(request).print(job_id)
 except Exception as exc:error(exc)
@router.get('/jobs/{job_id}/toolpath')
async def toolpath(job_id:str,request:Request):
 p=svc(request).store.job_dir(job_id)/'toolpath.json'
 if not p.is_file():raise HTTPException(404,'toolpath unavailable')
 return FileResponse(p,media_type='application/json')
@router.get('/jobs/{job_id}/model')
async def model(job_id:str,request:Request,oriented:bool=False):
 job=svc(request).job(job_id);p=svc(request).store.job_dir(job_id)/('oriented_preview.3mf' if oriented else job.input_filename)
 if not p.is_file():raise HTTPException(404,'model unavailable')
 return FileResponse(p)
