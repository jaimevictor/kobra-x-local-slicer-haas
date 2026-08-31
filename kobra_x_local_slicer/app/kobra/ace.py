from __future__ import annotations
from typing import Any
from app.core.models import AceSlot, AceSnapshot
class AceParseError(ValueError): pass
def _items(payload:dict[str,Any])->list[dict[str,Any]]:
 data=payload.get('data',payload); candidates=[]
 if isinstance(data,dict): candidates=[data.get(k) for k in ('slots','boxInfo','materials','multiColorBox')]
 for item in candidates:
  if isinstance(item,list): return [x for x in item if isinstance(x,dict)]
 return []
def parse_ace_payload(payload:dict[str,Any])->AceSnapshot:
 if not isinstance(payload,dict): raise AceParseError('ACE payload is not an object')
 parsed=_items(payload); normalized=[]
 for index,item in enumerate(parsed[:4]):
  material=item.get('material_type',item.get('materialType',item.get('type'))); material=str(material).upper() if material is not None else None
  color=item.get('color',item.get('rgb')); rgb=None
  if isinstance(color,str) and color.lstrip('#').__len__()==6:
   try: rgb=tuple(int(color.lstrip('#')[i:i+2],16) for i in (0,2,4))
   except ValueError: pass
  elif isinstance(color,(list,tuple)) and len(color)==3 and all(isinstance(x,int) and 0<=x<=255 for x in color): rgb=tuple(color)
  loaded=item.get('loaded',item.get('isLoaded'))
  normalized.append(AceSlot(human_slot=index+1,protocol_slot_index=index,material_type=material,rgb=rgb,loaded=loaded if isinstance(loaded,bool) else None))
 return AceSnapshot(raw=payload,parsed=parsed,normalized=normalized)
def pla_slots(snapshot:AceSnapshot)->list[AceSlot]: return [x for x in snapshot.normalized if x.material_type=='PLA']
def select_default_pla(snapshot:AceSnapshot)->AceSlot|None:
 slots=pla_slots(snapshot)
 loaded=[slot for slot in slots if slot.loaded is True]
 return loaded[0] if loaded else (slots[0] if slots else None)
