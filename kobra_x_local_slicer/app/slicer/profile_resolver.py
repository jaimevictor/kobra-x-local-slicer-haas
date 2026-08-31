from __future__ import annotations
import hashlib,json
from pathlib import Path
class ProfileError(ValueError):pass
def resolve_profile(path:Path, root:Path, chain:tuple[Path,...]=())->dict:
 path=path.resolve()
 if path in chain: raise ProfileError('circular profile inheritance')
 data=json.loads(path.read_text(encoding='utf-8')); parent=data.get('inherits'); merged={}
 if parent:
  matches=list(root.rglob(f'{parent}.json'))
  if len(matches)!=1: raise ProfileError(f'inherited profile not found uniquely: {parent}')
  merged.update(resolve_profile(matches[0],root,chain+(path,)))
 merged.update(data); merged.pop('inherits',None); return merged
def sha256(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
