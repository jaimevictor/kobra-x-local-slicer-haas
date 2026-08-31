from __future__ import annotations
import struct
import re
from dataclasses import dataclass
from pathlib import Path
from app.core.models import Bounds

@dataclass
class MeshInspection: triangles:int; volume_mm3:float; bounds:Bounds
def inspect_stl(path:Path)->MeshInspection:
 data=path.read_bytes()
 if data.lstrip().lower().startswith(b'solid'):
  vertices=[]
  for x,y,z in re.findall(r'\bvertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)',data.decode('ascii','strict'),re.I): vertices.append((float(x),float(y),float(z)))
  if not vertices or len(vertices)%3: raise ValueError('invalid ASCII STL')
  xs,ys,zs=zip(*vertices)
  return MeshInspection(len(vertices)//3,0.0,Bounds(min_x=min(xs),min_y=min(ys),min_z=min(zs),max_x=max(xs),max_y=max(ys),max_z=max(zs)))
 if len(data)<84: raise ValueError('invalid STL')
 count=struct.unpack_from('<I',data,80)[0]
 if 84+count*50!=len(data): raise ValueError('only binary STL is supported')
 xs=[];ys=[];zs=[]
 for n in range(count):
  values=struct.unpack_from('<12f',data,84+n*50)
  for x,y,z in zip(values[3::3],values[4::3],values[5::3]): xs.append(x);ys.append(y);zs.append(z)
 if not xs: raise ValueError('STL contains no triangles')
 return MeshInspection(count,0.0,Bounds(min_x=min(xs),min_y=min(ys),min_z=min(zs),max_x=max(xs),max_y=max(ys),max_z=max(zs)))
