import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';
import { STLLoader } from 'three/addons/STLLoader.js';
import { ThreeMFLoader } from 'three/addons/3MFLoader.js';

const $ = (s) => document.querySelector(s);
const log = (s) => { $('#log').textContent = `[${new Date().toLocaleTimeString()}] ${s}\n` + $('#log').textContent; };
let pendingRequests = 0;
function setBusy(active, message = 'Processando…') {
  pendingRequests = Math.max(0, pendingRequests + (active ? 1 : -1));
  $('#busyText').textContent = message;
  $('#busyOverlay').classList.toggle('hidden', pendingRequests === 0);
}
const nativeFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  setBusy(true);
  try { return await nativeFetch(...args); }
  finally { setBusy(false); }
};
const api = async (path, options={}) => {
  const response = await fetch(`./api/${path.replace(/^\//,'')}`, {cache:'no-store', ...options});
  const type = response.headers.get('content-type') || '';
  const body = type.includes('json') ? await response.json() : await response.text();
  if (!response.ok) throw new Error(body?.detail || body || `HTTP ${response.status}`);
  return body;
};
const jsonOptions = (body) => ({method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});

let job = null, ace = null, selectedSlot = null, currentObject = null, toolpath = null;
let selectedHa = null;
const viewer = $('#viewer');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0f1115);
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 2000);
camera.position.set(330, 330, 260);
const renderer = new THREE.WebGLRenderer({antialias:true});
viewer.appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement); controls.target.set(130,130,40); controls.update();
scene.add(new THREE.HemisphereLight(0xffffff,0x333344,2.0));
const dl = new THREE.DirectionalLight(0xffffff,2.2); dl.position.set(200,-100,350); scene.add(dl);
const grid = new THREE.GridHelper(260,26,0x607d8b,0x37474f); grid.rotation.x=Math.PI/2; grid.position.set(130,130,0); scene.add(grid);
const bed = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(260,260,1)), new THREE.LineBasicMaterial({color:0x90a4ae})); bed.position.set(130,130,-0.5); scene.add(bed);

function resize(){const w=viewer.clientWidth,h=viewer.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()}
new ResizeObserver(resize).observe(viewer); resize();
(function animate(){requestAnimationFrame(animate);renderer.render(scene,camera)})();

function filamentColor(){return selectedSlot?.rgb ? new THREE.Color(selectedSlot.rgb[0]/255,selectedSlot.rgb[1]/255,selectedSlot.rgb[2]/255) : new THREE.Color(0xbdbdbd)}
function clearModel(){if(currentObject){scene.remove(currentObject);currentObject.traverse?.(n=>{n.geometry?.dispose?.(); n.material?.dispose?.()});currentObject=null}}
function fitObject(object){const box=new THREE.Box3().setFromObject(object);const size=new THREE.Vector3(),center=new THREE.Vector3();box.getSize(size);box.getCenter(center);controls.target.copy(center);const d=Math.max(size.x,size.y,size.z,50)*2.0;camera.position.set(center.x+d,center.y-d,center.z+d*.8);camera.near=.1;camera.far=Math.max(2000,d*5);camera.updateProjectionMatrix();controls.update();$('#bbox').textContent=`${size.x.toFixed(1)} × ${size.y.toFixed(1)} × ${size.z.toFixed(1)} mm`}
function recolor(){if(!currentObject)return;const c=filamentColor();currentObject.traverse(n=>{if(n.isMesh)n.material=new THREE.MeshStandardMaterial({color:c,roughness:.68,metalness:.02,side:THREE.DoubleSide})})}
async function loadModel(oriented=false){if(!job)return;clearModel();const r=await fetch(`./api/jobs/${job.id}/model?oriented=${oriented?'true':'false'}`,{cache:'no-store'});if(!r.ok)throw new Error('não foi possível carregar preview');const buf=await r.arrayBuffer();if((oriented || job.input_type==='3mf')){currentObject=new ThreeMFLoader().parse(buf);currentObject.traverse(n=>{if(n.isMesh)n.material=new THREE.MeshStandardMaterial({color:filamentColor(),roughness:.68,side:THREE.DoubleSide})})}else{const geom=new STLLoader().parse(buf);geom.computeVertexNormals();currentObject=new THREE.Mesh(geom,new THREE.MeshStandardMaterial({color:filamentColor(),roughness:.68,side:THREE.DoubleSide}));currentObject.rotation.x=0}scene.add(currentObject);applyVisualOrientation();fitObject(currentObject)}
function applyVisualOrientation(){if(!currentObject||!job)return;currentObject.rotation.set(0,0,0);currentObject.position.set(0,0,0);if(job.orientation==='rotate_x_90')currentObject.rotation.x=Math.PI/2;if(job.orientation==='rotate_y_90')currentObject.rotation.y=Math.PI/2;if(job.orientation==='rotate_z_90')currentObject.rotation.z=Math.PI/2;currentObject.updateMatrixWorld(true);const box=new THREE.Box3().setFromObject(currentObject),center=new THREE.Vector3();box.getCenter(center);currentObject.position.x+=130-center.x;currentObject.position.y+=130-center.y;currentObject.position.z+=-box.min.z;currentObject.updateMatrixWorld(true)}

async function health(){try{const h=await api('health');$('#printerStatus').textContent=h.printer_host_configured?(h.lan_connected?'LAN conectado':'LAN configurado'):'configuração necessária';$('#printerStatus').className=`status ${h.printer_host_configured?'ok':'bad'}`;const c=await api('config');if(!c.printer_host){$('#configCard').classList.remove('hidden')}else{$('#printerHost').value=c.printer_host}}catch(e){$('#printerStatus').textContent='erro';$('#printerStatus').className='status bad';log(e.message)}}

const HA_REQUIRED_ROLES=['online','available','busy','job_in_progress','state','filename'];
function renderHaRoles(candidate){const root=$('#haRoles');root.innerHTML='';root.classList.remove('hidden');for(const role of [...HA_REQUIRED_ROLES,'current_fault']){const label=document.createElement('label');label.textContent=role;const sel=document.createElement('select');sel.dataset.role=role;sel.innerHTML='<option value="">— não mapeado —</option>'+candidate.entities.map(e=>`<option value="${e.entity_id}">${e.entity_id}${e.translation_key?` · ${e.translation_key}`:''}</option>`).join('');sel.value=candidate.suggested_map[role]||'';label.appendChild(sel);root.appendChild(label)}const errors=document.createElement('label');errors.textContent='error entities (Ctrl/Cmd para múltiplas)';const es=document.createElement('select');es.dataset.role='error_entities';es.multiple=true;es.size=Math.min(5,Math.max(2,candidate.entities.length));es.innerHTML=candidate.entities.map(e=>`<option value="${e.entity_id}">${e.entity_id}</option>`).join('');for(const o of es.options)o.selected=(candidate.suggested_map.error_entities||[]).includes(o.value);errors.appendChild(es);root.appendChild(errors)}
function selectedHaMap(){const out={};for(const sel of document.querySelectorAll('#haRoles select[data-role]')){const role=sel.dataset.role;if(role==='error_entities'){out[role]=[...sel.selectedOptions].map(x=>x.value);continue}if(sel.value)out[role]=sel.value}const missing=HA_REQUIRED_ROLES.filter(x=>!out[x]);if(missing.length)throw new Error(`Mapeie as entidades obrigatórias: ${missing.join(', ')}`);return out}
$('#discoverHa').onclick=async()=>{try{const list=await api('onboarding/discover');const root=$('#haCandidates');root.innerHTML='';$('#haRoles').classList.add('hidden');for(const c of list){const div=document.createElement('div');div.className='candidate';div.innerHTML=`<label><input type="radio" name="haDevice" value="${c.device_id}"><strong>${c.name}</strong></label><small class="muted">${c.entities.length} entidades · mapeamentos pendentes: ${c.unresolved_roles.join(', ')||'nenhum'}</small>`;const radio=div.querySelector('input');radio.onchange=()=>{selectedHa=c;renderHaRoles(c)};root.appendChild(div)}if(!list.length)throw new Error('Nenhum dispositivo anycubic_cloud foi encontrado no registry.');if(list.length===1){selectedHa=list[0];const radio=root.querySelector('input');radio.checked=true;renderHaRoles(selectedHa)}}catch(e){log(e.message)}};
$('#saveConfig').onclick=async()=>{try{if(!selectedHa)throw new Error('Selecione o dispositivo Anycubic descoberto no Home Assistant.');const body={printer_host:$('#printerHost').value.trim(),ha_device_id:selectedHa.device_id,ha_entity_map:selectedHaMap()};const r=await fetch('./api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const b=await r.json();if(!r.ok)throw new Error(b.detail||'falha');$('#configCard').classList.add('hidden');await health();log('Configuração salva.')}catch(e){log(e.message)}};

const dz=$('#dropzone'), fi=$('#fileInput');['dragenter','dragover'].forEach(x=>dz.addEventListener(x,e=>{e.preventDefault();dz.classList.add('drag')}));['dragleave','drop'].forEach(x=>dz.addEventListener(x,e=>{e.preventDefault();dz.classList.remove('drag')}));dz.addEventListener('drop',e=>upload(e.dataTransfer.files[0]));fi.addEventListener('change',()=>upload(fi.files[0]));
async function upload(file){if(!file)return;try{const form=new FormData();form.append('file',file);$('#sliceState').textContent='enviando modelo…';log(`Enviando ${file.name}…`);const r=await fetch('./api/jobs',{method:'POST',body:form});const b=await r.json();if(!r.ok)throw new Error(b.detail||'upload falhou');job=b;$('#supportToggle').checked=job.supports_enabled;$('#uploadMeta').textContent=`${job.original_filename} · ${job.id.slice(0,8)}`;$('#sliceState').textContent='carregando preview…';log(`Job ${job.id} pronto para seleção de filamento.`);await loadModel();$('#sliceState').textContent='consultando ACE…';const aceReady=await refreshAce();$('#sliceBtn').disabled=!aceReady||!selectedSlot}catch(e){$('#sliceState').textContent='falha ao preparar modelo';log(e.message)}}

async function refreshAce(){try{ace=await api(`jobs/${job.id}/ace`);job=await api(`jobs/${job.id}`);selectedSlot=job.selected_slot;renderAce();$('#sliceBtn').disabled=!selectedSlot;$('#sliceBtn').title=selectedSlot?'':'Nenhum slot PLA foi encontrado no ACE';$('#sliceState').textContent=selectedSlot?`Slot ${selectedSlot.human_slot} selecionado; pronto para fatiar`:'nenhum slot PLA encontrado no ACE';return Boolean(selectedSlot)}catch(e){$('#aceSlots').innerHTML='<p class="muted">Não foi possível consultar o ACE.</p>';$('#sliceBtn').disabled=true;$('#sliceBtn').title='A consulta ao ACE falhou';$('#sliceState').textContent=`ACE indisponível: ${e.message}`;log(`ACE: ${e.message}`);return false}}
function renderAce(){const root=$('#aceSlots');root.innerHTML='';for(const s of ace.normalized){const div=document.createElement('div');const supported=s.material_type==='PLA';div.className=`slot ${supported?'':'unsupported'} ${selectedSlot?.human_slot===s.human_slot?'selected':''}`;const color=s.rgb?`rgb(${s.rgb.join(',')})`:'#777';div.innerHTML=`<div class="swatch" style="background:${color}"></div><strong>Slot ${s.human_slot}</strong><div>${s.material_type||'desconhecido'}</div><small>${s.loaded===true?'carregado':s.loaded===false?'':'estado carregado desconhecido'}</small>`;if(supported)div.onclick=async()=>{try{job=await api(`jobs/${job.id}/slot`,jsonOptions({human_slot:s.human_slot}));selectedSlot=job.selected_slot;renderAce();recolor();$('#sliceBtn').disabled=false;$('#sliceBtn').title='';$('#sliceState').textContent=`Slot ${s.human_slot} selecionado; pronto para fatiar`;log(`Slot ${s.human_slot} selecionado.`)}catch(e){log(e.message)}};root.appendChild(div)}if(!ace.normalized.some(s=>s.material_type==='PLA')){$('#sliceBtn').disabled=true;$('#sliceBtn').title='Nenhum slot PLA foi encontrado no ACE';log('Nenhum slot PLA disponível.')}if(selectedSlot)recolor()}

$('#supportToggle').onchange=async e=>{if(!job){e.target.checked=false;return}const enabled=e.target.checked;try{job=await api(`jobs/${job.id}/supports`,jsonOptions({enabled}));$('#resultCard').classList.add('hidden');$('#sliceState').textContent=enabled?'suportes ativados; pronto para fatiar':'suportes desativados; pronto para fatiar';log(enabled?'Suportes automáticos ativados.':'Suportes automáticos desativados.')}catch(err){e.target.checked=!enabled;log(err.message)}};

$('#orientationButtons').addEventListener('click',async e=>{const b=e.target.closest('button[data-o]');if(!b||!job)return;try{const response=await api(`jobs/${job.id}/orientation`,jsonOptions({orientation:b.dataset.o}));job=response.job;document.querySelectorAll('#orientationButtons button').forEach(x=>x.classList.toggle('active',x===b));if(response.preview_file)await loadModel(true);else{applyVisualOrientation();fitObject(currentObject)}$('#resultCard').classList.add('hidden');log(`Orientação: ${b.textContent}`)}catch(err){log(err.message)}});

$('#sliceBtn').onclick=async()=>{try{$('#sliceBtn').disabled=true;$('#sliceState').textContent='fatiando…';$('#resultCard').classList.remove('hidden');log('OrcaSlicer iniciado.');job=await api(`jobs/${job.id}/slice`,{method:'POST'});selectedSlot=job.selected_slot;renderStats();await loadToolpath();$('#sliceState').textContent='aguardando confirmação';log(`Slice validado. SHA-256 ${job.slice_stats.gcode_sha256}`)}catch(e){log(e.message);$('#sliceState').textContent='falhou'}finally{$('#sliceBtn').disabled=false}};
function sec(v){if(v==null)return '—';const h=Math.floor(v/3600),m=Math.floor((v%3600)/60);return h?`${h}h ${m}min`:`${m} min`}
function renderStats(){const s=job.slice_stats,t=s.temperatures,d=s.dimensions;const rows=[['Tempo',sec(s.estimated_print_time_seconds)],['Filamento',s.filament_length_mm?`${(s.filament_length_mm/1000).toFixed(2)} m`:'—'],['Massa',s.filament_mass_g?`${s.filament_mass_g.toFixed(1)} g`:'—'],['Camadas',s.layer_count??'—'],['Nozzle 1ª',t.first_layer_nozzle?`${t.first_layer_nozzle} °C`:'—'],['Nozzle impressão',t.printing_nozzle?`${t.printing_nozzle} °C`:'—'],['Mesa 1ª',t.first_layer_bed?`${t.first_layer_bed} °C`:'—'],['Mesa impressão',t.printing_bed?`${t.printing_bed} °C`:'—'],['Dimensões',d?`${(d.max_x-d.min_x).toFixed(1)}×${(d.max_y-d.min_y).toFixed(1)}×${(d.max_z-d.min_z).toFixed(1)} mm`:'—'],['Suportes',job.supports_enabled?'ativados':'desativados'],['ACE',`Slot ${job.selected_slot.human_slot} · ${job.selected_slot.material_type}`],['Orca',s.orca_version],['Profiles',Object.entries(s.profile_versions||{}).map(([k,v])=>`${k}: ${v}`).join(' · ')||s.profile_manifest_sha256||'—'],['SHA-256',s.gcode_sha256]];$('#stats').innerHTML=rows.map(([k,v])=>`<div class="stat"><small>${k}</small><strong>${v}</strong></div>`).join('');$('#tableClear').checked=false;$('#printBtn').disabled=true}

async function loadToolpath(){toolpath=await api(`jobs/${job.id}/toolpath`);const slider=$('#layerSlider');slider.min=0;slider.max=Math.max(0,toolpath.layers.length-1);slider.value=0;drawLayer(0);slider.oninput=()=>drawLayer(+slider.value)}
function drawLayer(i){const c=$('#toolpath'),ctx=c.getContext('2d'),pts=toolpath.layers[i]||[];ctx.clearRect(0,0,c.width,c.height);ctx.fillStyle='#0f1115';ctx.fillRect(0,0,c.width,c.height);ctx.strokeStyle=selectedSlot?.rgb?`rgb(${selectedSlot.rgb.join(',')})`:'#e0e0e0';ctx.lineWidth=1;if(pts.length){ctx.beginPath();for(let n=0;n<pts.length;n++){const [x,y]=pts[n];const px=20+x/260*(c.width-40),py=c.height-20-y/260*(c.height-40);if(n===0)ctx.moveTo(px,py);else ctx.lineTo(px,py)}ctx.stroke()}$('#layerLabel').textContent=`${i+1}/${toolpath.layers.length}`}
$('#tableClear').onchange=()=>{$('#printBtn').disabled=!$('#tableClear').checked};
$('#printBtn').onclick=async()=>{try{if(!confirm('Iniciar fisicamente a impressão na Kobra X agora?'))return;$('#printBtn').disabled=true;job=await api(`jobs/${job.id}/confirm`,jsonOptions({gcode_sha256:job.slice_stats.gcode_sha256,table_clear:true}));log('Confirmação vinculada ao hash. Executando preflight fresco…');job=await api(`jobs/${job.id}/print`,{method:'POST'});log(`Estado final do comando: ${job.state}${job.error?` · ${job.error}`:''}`);$('#sliceState').textContent=job.state}catch(e){log(e.message);$('#printBtn').disabled=false;try{job=await api(`jobs/${job.id}`);if(job.state==='AWAITING_CONFIRMATION'){$('#tableClear').checked=false;$('#printBtn').disabled=true}}catch{}}};

health();
