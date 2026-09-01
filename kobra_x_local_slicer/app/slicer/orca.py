from __future__ import annotations
import asyncio,hashlib,json,os,shutil
from pathlib import Path
from app.core.models import Orientation
class OrcaError(RuntimeError):pass
class OrcaRunner:
 def __init__(self,profile_dir:Path,timeout_seconds:int,gcode_limit_bytes:int): self.profile_dir=profile_dir;self.timeout_seconds=timeout_seconds;self.gcode_limit_bytes=gcode_limit_bytes;self.app=os.getenv('ORCA_APP','OrcaSlicer');self.version=os.getenv('ORCA_VERSION','2.4.2')
 def _profile(self,name:str)->Path:
  p=self.profile_dir/name
  if not p.is_file(): raise OrcaError(f'resolved profile missing: {name}')
  return p
 def load_filament_profile(self)->dict:return json.loads(self._profile('anycubic_pla_kobra_x.resolved.json').read_text(encoding='utf-8'))
 def manifest_sha256(self)->str|None:
  p=self.profile_dir/'manifest.json';return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
 def profile_versions(self)->dict[str,str]:
  p=self.profile_dir/'manifest.json'
  return json.loads(p.read_text()).get('resolved_sha256',{}) if p.is_file() else {}
 def _process_for_slice(self,directory:Path,supports_enabled:bool)->Path:
  process=self._profile('kobra_x_020_standard.resolved.json')
  if not supports_enabled:return process
  settings=json.loads(process.read_text(encoding='utf-8'));settings['enable_support']='1'
  enabled=directory/'process_with_supports.json';enabled.write_text(json.dumps(settings),encoding='utf-8')
  return enabled
 def _clear_previous_gcode(self,directory:Path)->None:
  for previous in directory.glob('*.gcode'):
   if previous.is_file(): previous.unlink()
 async def slice(self,input_path:Path,directory:Path,orientation:Orientation,supports_enabled:bool=False)->Path:
  out=directory/'output.gcode'; machine=self._profile('kobra_x_04.resolved.json');process=self._process_for_slice(directory,supports_enabled);filament=self._profile('anycubic_pla_kobra_x.resolved.json')
  # A re-slice happens in the same job directory. Orca writes plate_1.gcode,
  # while the previous successful result is normalized to output.gcode; both
  # must not be considered outputs of the new invocation.
  self._clear_previous_gcode(directory)
  # Verified with OrcaSlicer 2.4.2 --help in the built image.
  cmd=[self.app,'--load-settings',f'{machine};{process}','--load-filaments',str(filament),'--ensure-on-bed','--outputdir',str(directory),'--slice','0',str(input_path)]
  if orientation==Orientation.ROTATE_X_90: cmd.extend(['--rotate-x','90'])
  if orientation==Orientation.ROTATE_Y_90: cmd.extend(['--rotate-y','90'])
  if orientation==Orientation.ROTATE_Z_90: cmd.extend(['--rotate','90'])
  try:
   proc=await asyncio.wait_for(asyncio.create_subprocess_exec(*cmd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE),10)
   stdout,stderr=await asyncio.wait_for(proc.communicate(),self.timeout_seconds)
  except FileNotFoundError as exc: raise OrcaError('OrcaSlicer executable unavailable') from exc
  generated=list(directory.glob('*.gcode'))
  if proc.returncode or len(generated)!=1:
   output=(stdout+b'\n'+stderr).decode(errors='replace').strip()[-2000:]
   files=', '.join(sorted(path.name for path in directory.iterdir()))
   raise OrcaError(f'Orca slicing failed: exit={proc.returncode}, gcode_files={len(generated)}, supports={supports_enabled}, files=[{files}], output={output or "(no output)"}')
  if generated[0]!=out: generated[0].replace(out)
  if out.stat().st_size>self.gcode_limit_bytes: raise OrcaError('Orca output exceeds G-code limit')
  return out
 async def export_oriented_3mf(self,input_path:Path,directory:Path,orientation:Orientation)->Path:
  # The CLI has no verified auto-orient/export workflow in this revision: safe preview is original geometry.
  if input_path.suffix.lower()=='.3mf':
   out=directory/'oriented_preview.3mf';shutil.copyfile(input_path,out);return out
  raise OrcaError('auto orientation preview is only available for 3MF files')
