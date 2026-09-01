from __future__ import annotations
import logging
from fastapi import APIRouter,File,HTTPException,Request,UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.core.models import Orientation
from app.core.security import validate_printer_host
from app.kobra.lan import ValidatedLegacyLanStart
from app.ha.client import AnycubicHomeAssistantAdapter

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
class ConfigInput(BaseModel):printer_host:str;ha_device_id:str
@router.get('/health')
async def health(request:Request):
 s=request.app.state.settings; return {'ok':True,'printer_host_configured':bool(s.printer_host),'ha_device_configured':bool(s.ha_device_id),'integration_error':getattr(request.app.state,'integration_error',None),'lan_connected':bool(svc(request).lan and svc(request).lan.connected)}
@router.get('/config')
async def config(request:Request): return {'printer_host':request.app.state.settings.printer_host}
@router.put('/config')
async def set_config(body:ConfigInput,request:Request):
 try:
   if not body.ha_device_id: raise ValueError('Anycubic printer device selection is required')
   adapter=AnycubicHomeAssistantAdapter(body.ha_device_id)
   await adapter.resolve()
   snapshot=await adapter.snapshot()
   if not snapshot.essential_entities_available: raise ValueError('selected device is missing required anycubic_cloud entities')
   s=request.app.state.settings;s.printer_host=validate_printer_host(body.printer_host);s.ha_device_id=body.ha_device_id;s.save_config()
   old=svc(request).lan
   if old: await old.close()
   svc(request).lan=ValidatedLegacyLanStart(s.printer_host)
   svc(request)._ha=None
   return {'ok':True}
 except Exception as exc:error(exc)
@router.get('/onboarding/discover')
async def discover_home_assistant():
  try:return await AnycubicHomeAssistantAdapter().discover()
  except Exception as exc:error(exc)
@router.get('/printer/state')
async def printer_state(request:Request):
 try:return await svc(request).printer_snapshot()
 except Exception as exc:error(exc)
@router.get('/printer/capabilities')
async def printer_capabilities(request:Request):
 try:return (await svc(request).printer_snapshot()).capabilities
 except Exception as exc:error(exc)
@router.get('/printer/integration')
async def printer_integration(request:Request):
 try:return await svc(request).integration_diagnostics()
 except Exception as exc:error(exc)
@router.get('/jobs/active')
async def active_jobs(request:Request):
 active={'PREFLIGHT','UPLOADING_TO_PRINTER','UPLOADED_TO_PRINTER','STARTING','START_UNKNOWN','PRINT_ACCEPTED','MONITORING'}
 await svc(request).reconcile_active_jobs()
 return [job for job in svc(request).store.list() if job.state.value in active]
@router.get('/jobs/recent')
async def recent_jobs(request:Request): return svc(request).store.list()[:20]
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
 try:return await svc(request).confirm(job_id,body.gcode_sha256,body.table_clear)
 except Exception as exc:error(exc)
@router.post('/jobs/{job_id}/print')
async def print_job(job_id:str,request:Request):
 try:return await svc(request).print(job_id)
 except Exception as exc:error(exc)
@router.post('/jobs/{job_id}/pause')
async def pause_job(job_id:str,request:Request):
 try:return await svc(request).control(job_id,'pause')
 except Exception as exc:error(exc)
@router.post('/jobs/{job_id}/resume')
async def resume_job(job_id:str,request:Request):
 try:return await svc(request).control(job_id,'resume')
 except Exception as exc:error(exc)
@router.post('/jobs/{job_id}/cancel')
async def cancel_job(job_id:str,request:Request):
 try:return await svc(request).control(job_id,'cancel')
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
