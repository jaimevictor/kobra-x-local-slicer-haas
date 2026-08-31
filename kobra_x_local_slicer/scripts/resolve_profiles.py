#!/usr/bin/env python3
"""Resolve Orca JSON inherits chains root-first without trusting leaf-only loading."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def resolve(path:Path,root:Path,seen:tuple[Path,...]=())->tuple[dict,list[Path]]:
 path=path.resolve()
 if path in seen: raise RuntimeError('circular inherits: '+' -> '.join(p.name for p in seen+(path,)))
 data=json.loads(path.read_text(encoding='utf-8')); sources=[]; result={}; parent=data.get('inherits')
 if parent:
  found=[p for p in root.rglob('*.json') if p.stem==parent]
  if len(found)!=1: raise RuntimeError(f'inherits {parent!r} from {path} is not unique/found')
  result,sources=resolve(found[0],root,seen+(path,))
 result=dict(result); result.update(data); result.pop('inherits',None); return result,sources+[path]
def main():
 p=argparse.ArgumentParser();p.add_argument('--vendor-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);p.add_argument('--orca-version',required=True);p.add_argument('--orca-source-ref',required=True);p.add_argument('--machine',required=True);p.add_argument('--process',required=True);p.add_argument('--filament',required=True);args=p.parse_args()
 args.output_root.mkdir(parents=True,exist_ok=True); output={}; sources={};resolved_sha={};cli_compatibility_removed={}
 for kind,value in [('machine',args.machine),('process',args.process),('filament',args.filament)]:
  source_name,out_name=value.split(':',1);source=args.vendor_root/source_name
  if not source.is_file(): raise RuntimeError(f'official {kind} preset missing: {source_name}')
  flat,chain=resolve(source,args.vendor_root)
  # OrcaSlicer 2.4.2 CLI rejects the official Kobra X value ["0"] for this cutter-only
  # setting (it demands 10-18 despite Kobra X not having a cutter).  Omit it so Orca applies
  # its valid internal default; all printer/process/filament slicing values remain official.
  if kind=='machine' and flat.get('retraction_distances_when_cut') in ('0',['0'],0,[0]):
   flat.pop('retraction_distances_when_cut');cli_compatibility_removed[out_name]=['retraction_distances_when_cut']
  target=args.output_root/out_name;target.write_text(json.dumps(flat,sort_keys=True,indent=2)+'\n',encoding='utf-8')
  output[kind]=out_name;resolved_sha[out_name]=digest(target);sources[kind]=[{'path':str(x.relative_to(args.vendor_root)).replace('\\','/'),'sha256':digest(x)} for x in chain]
 (args.output_root/'manifest.json').write_text(json.dumps({'orca_version':args.orca_version,'orca_source_ref':args.orca_source_ref,'outputs':output,'sources':sources,'resolved_sha256':resolved_sha,'cli_compatibility_removed':cli_compatibility_removed},sort_keys=True,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
