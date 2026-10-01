const english = new Map(Object.entries({
  'Etapas da impressão':'Print steps','Importar':'Import','Preparar':'Prepare','Prévia':'Preview','Validar':'Validate',
  'Escolha um modelo para começar.':'Choose a model to begin.',
  'Confira a orientação, o material e a qualidade.':'Check orientation, material and quality.',
  'Inspecione o percurso antes de continuar.':'Inspect the toolpath before continuing.',
  'Confira a peça e confirme que a mesa está livre.':'Review the model and confirm the build plate is clear.',
  'Estado e temperaturas recebidos do Home Assistant.':'Status and temperatures from Home Assistant.',
  'Conexão da impressora':'Printer connection','Importar modelo':'Import model',
  'STL e 3MF · escolha um arquivo ou arraste aqui':'STL and 3MF · choose a file or drop it here',
  'Importar modelo STL ou 3MF':'Import STL or 3MF model','Sobre o perfil de impressão':'About the print profile',
  'PRÉVIA':'PREVIEW','Inspecione as camadas':'Inspect layers',
  'Percurso de extrusão · vista superior':'Extrusion path · top view','Selecionar camada':'Select layer',
  'Detalhes do fatiamento':'Slice details','Continuar para validação →':'Continue to validation →',
  'VALIDAÇÃO':'VALIDATION','Pronto para enviar?':'Ready to send?',
  'A conexão, o ACE e o volume de impressão serão verificados novamente ao enviar.':'Connection, ACE and build volume will be checked again when sending.',
  'Impressora online':'Printer online','Conexão será verificada ao enviar':'Connection will be checked when sending',
  'G-code validado; confirmação vinculada ao arquivo':'G-code validated; confirmation bound to the file',
  'IMPRESSÃO':'PRINTING','Acompanhe a Kobra X':'Monitor the Kobra X','Sem dados recentes':'No recent data',
  'Nenhuma impressão informada':'No print reported','Progresso':'Progress','Decorrido':'Elapsed','Restante':'Remaining',
  'Bico':'Nozzle','Mesa':'Bed','Alvo':'Target','Atualizado':'Updated',
  'Aguardando informações do Home Assistant.':'Waiting for Home Assistant data.',
  'Aguardando informações recentes do Home Assistant.':'Waiting for recent Home Assistant data.',
  'Falha ativa na impressora. Confira o Home Assistant.':'Active printer fault. Check Home Assistant.',
  'Início incerto. Aguarde a reconciliação no Home Assistant; não envie novamente.':'Start uncertain. Wait for Home Assistant reconciliation; do not send again.',

  'Impressora selecionada':'Printer selected','Salve a conexão para confirmar.':'Save the connection to confirm.',
  'Salvando…':'Saving…','Falha ao salvar conexão':'Failed to save connection',
  'Conexão salva. Use Descobrir para selecionar outra impressora.':'Connection saved. Use Discover to select another printer.',
  'Envie um modelo STL ou 3MF. Arquivos G-code já fatiados não são aceitos.':'Upload an STL or 3MF model. Pre-sliced G-code files are not supported.',

  'Impressão local':'Local printing','Estado da impressora indisponível':'Printer state unavailable','Verificando…':'Checking…',
  'ESTÚDIO DE IMPRESSÃO':'PRINT STUDIO','Do modelo à impressão,':'From model to print,','com controle em cada etapa.':'with control at every step.',
  'Prepare a peça, confira o filamento e revise o fatiamento antes de iniciar na Kobra X.':'Prepare your model, check the filament, and review the slice before starting the Kobra X.',
  'Modelo':'Model','Preparação':'Preparation','Revisão':'Review','Impressão':'Print','CONEXÃO':'CONNECTION',
  'Impressora e Home Assistant':'Printer and Home Assistant','Configuração inicial':'Initial setup','IP da Kobra X':'Kobra X IP address',
  'Descobrir dispositivos':'Discover devices','Salvar conexão':'Save connection','Selecione a impressora no Home Assistant para começar.':'Select the printer in Home Assistant to begin.',
  'Dispositivo HA salvo. Use Descobrir para selecionar outro.':'Home Assistant device saved. Use Discover to select another.',
  'ETAPA 01':'STEP 01','Escolha o modelo':'Choose a model','STL ou 3MF · uma placa · um material':'STL or 3MF · one plate · one material',
  'Solte o arquivo aqui ou clique para escolher':'Drop a file here or click to choose','STL e 3MF · tamanho máximo conforme configuração':'STL and 3MF · size limit set in configuration',
  'ETAPA 02':'STEP 02','Visualize a peça':'Preview the model','Aguardando modelo':'Waiting for a model','Girar X 90°':'Rotate X 90°','Girar Y 90°':'Rotate Y 90°','Girar Z 90°':'Rotate Z 90°',
  'ETAPA 02 · PREPARAÇÃO':'STEP 02 · PREPARATION','Filamento e fatiamento':'Filament and slicing','Selecione um slot ACE com material compatível e confira a cor na prévia.':'Select an ACE slot with a supported material and check its color in the preview.',
  'Diâmetro do bico':'Nozzle diameter','Altura de camada':'Layer height','0,4 mm · perfil oficial':'0.4 mm · official profile',
  '0,08 mm':'0.08 mm','0,12 mm':'0.12 mm','0,16 mm':'0.16 mm','0,20 mm':'0.20 mm','0,24 mm':'0.24 mm','0,28 mm':'0.28 mm',
  'A versão oficial do Orca 2.4.2 fornece apenas o perfil Kobra X de bico 0,4 mm.':'The official Orca 2.4.2 release provides only a 0.4 mm Kobra X nozzle profile.',
  'Gerar suportes automáticos':'Generate automatic supports','Fatiar modelo':'Slice model','ETAPA 03 · REVISÃO':'STEP 03 · REVIEW',
  'Confira antes de imprimir':'Review before printing','Prévia do percurso':'Toolpath preview','Camada':'Layer','A mesa está livre e pronta':'The build plate is clear and ready',
  'Confirmar e imprimir':'Confirm and print','Registro de atividades':'Activity log','Alternar modo escuro':'Toggle dark mode',
  'Configuração necessária':'Setup required','configuração necessária':'setup required','impressora offline':'printer offline','integração HA indisponível':'Home Assistant integration unavailable',
  'aguardando Home Assistant':'waiting for Home Assistant','erro':'error','sem job':'no job','falha ativa':'active fault','desconhecido':'unknown',
  'carregado':'loaded','estado carregado desconhecido':'loaded state unknown','Nenhum material compatível disponível.':'No supported material available.',
  'Nenhum material compatível foi encontrado no ACE':'No supported material was found in ACE',
  'Tempo':'Time','Filamento':'Filament','Massa':'Mass','Camadas':'Layers','Nozzle 1ª':'First layer nozzle','Nozzle impressão':'Printing nozzle',
  'Mesa 1ª':'First layer bed','Mesa impressão':'Printing bed','Dimensões':'Dimensions','Suportes':'Supports','ativados':'enabled','desativados':'disabled',
  'Pausar':'Pause','Retomar':'Resume','Cancelar':'Cancel','Controles do job ativo':'Active print controls',
  'enviando modelo…':'uploading model…','carregando preview…':'loading preview…','consultando ACE…':'checking ACE…','falha ao preparar modelo':'could not prepare model',
  'fatiando…':'slicing…','aguardando confirmação':'waiting for confirmation','pronto para fatiar':'ready to slice',
  'suportes ativados; pronto para fatiar':'supports enabled; ready to slice','suportes desativados; pronto para fatiar':'supports disabled; ready to slice',
  'Altura alterada; pronto para fatiar':'Layer height changed; ready to slice',
  'A mesa está livre e pronta':'The build plate is clear and ready','Não foi possível consultar o ACE.':'Could not read ACE.',
  'ACE indisponível':'ACE unavailable','Confirmação vinculada ao hash. Executando preflight fresco…':'Confirmation bound to hash. Running a fresh preflight…',
  'Iniciar fisicamente a impressão na Kobra X agora?':'Start the physical print on the Kobra X now?',
  'Cancelar fisicamente o job ativo?':'Cancel the active physical print?',
  'Nenhum dispositivo anycubic_cloud foi encontrado no registry.':'No anycubic_cloud device was found in the Home Assistant registry.',
  'Selecione o dispositivo Anycubic descoberto no Home Assistant.':'Select the Anycubic device discovered in Home Assistant.',
  'Configuração salva; entidades serão resolvidas automaticamente.':'Configuration saved; entities will be resolved automatically.',
  'Suportes automáticos ativados.':'Automatic supports enabled.','Suportes automáticos desativados.':'Automatic supports disabled.',
  'OrcaSlicer iniciado.':'OrcaSlicer started.','Nenhum slot PLA disponível.':'No PLA slot available.',
  'Este job falhou; envie o modelo novamente após corrigir o motivo exibido.':'This job failed; fix the displayed reason and upload the model again.',
  'A consulta ao ACE falhou':'ACE query failed','O modelo não pode ser carregado':'The model could not be loaded',
  'não foi possível carregar preview':'could not load preview'
}));

const phrases = [
  [/^job: /,'job: '],[/^camada /,'layer '],[/^bico /,'nozzle '],[/^mesa /,'bed '],[/^último erro: /,'last error: '],
  [/^capabilities: /,'capabilities: '],[/^Slot (\d+) selecionado; pronto para fatiar$/,'Slot $1 selected; ready to slice'],
  [/^Slot (\d+) selecionado\.$/,'Slot $1 selected.'],[/^Enviando (.+)…$/,'Uploading $1…'],
  [/^Job (.+) pronto para seleção de filamento\.$/,'Job $1 ready for filament selection.'],
  [/^Slice validado\. SHA-256 /,'Slice validated. SHA-256 '],[/^Slice falhou: /,'Slice failed: '],
  [/^Altura de camada: /,'Layer height: '],[/^Orientação: /,'Orientation: '],
  [/^Nenhum slot PLA disponível\.$/,'No PLA slot available.'],[/^ACE indisponível: /,'ACE unavailable: '],
  [/^Estado final do comando: /,'Final command state: '],[/^falhou: /,'failed: ']
];
const states = {'printing':['imprimindo','printing'],'paused':['pausada','paused'],'idle':['ociosa','idle'],'free':['livre','ready'],'heating':['aquecendo','heating'],'checking':['verificando','checking'],'pausing':['pausando','pausing'],'ready':['pronta','ready'],'available':['disponível','available'],'completed':['concluída','completed'],'failed':['falhou','failed'],'offline':['offline','offline'],'online':['online','online']};
const portugueseErrors = [
  [/3MF multicolor\/multi-material slicing is not yet validated for Kobra X:/,'O fatiamento 3MF multimatéria ainda não foi validado para a Kobra X:'],
  [/per-face filament painting present/g,'há pintura de filamento por face'],
  [/project assigns objects\/parts to additional extruders/g,'o projeto atribui peças a extrusores adicionais'],
  [/selected ACE material has no verified Kobra X profile/g,'O material do ACE não possui perfil Kobra X verificado'],
  [/no ACE slot has a supported Kobra X material profile/g,'Nenhum slot ACE possui perfil Kobra X compatível'],
  [/selected ACE material changed; reselect and slice again/g,'O material do ACE mudou; selecione o slot e fatie novamente'],
  [/unsupported layer height for the 0\.4 mm Kobra X nozzle/g,'Altura de camada incompatível com o bico Kobra X de 0,4 mm']
];

function haLanguage() {
  try { const hass = window.parent?.document?.querySelector('home-assistant')?.hass; if (hass?.locale?.language) return hass.locale.language; }
  catch { /* Ingress may be isolated in another origin. */ }
  return navigator.language || 'pt-BR';
}
export const language = haLanguage().toLowerCase().startsWith('pt') ? 'pt-BR' : 'en';
document.documentElement.lang = language;

export function tr(value) {
  const source = String(value);
  const state = states[source.toLowerCase()];
  if (state) return state[language === 'en' ? 1 : 0];
  if (language !== 'en') return portugueseErrors.reduce((result,[pattern,replacement])=>result.replace(pattern,replacement),source);
  if (english.has(source)) return english.get(source);
  let result = source;
  for (const [pattern, replacement] of phrases) result = result.replace(pattern, replacement);
  return result;
}

export function translatePage() {
  if (language !== 'en') return;
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walk.nextNode())) {
    const raw = node.nodeValue;
    const trimmed = raw.trim();
    if (trimmed) node.nodeValue = raw.replace(trimmed, tr(trimmed));
  }
  for (const element of document.querySelectorAll('[aria-label],[placeholder],[title]')) {
    for (const attr of ['aria-label','placeholder','title']) if (element.hasAttribute(attr)) element.setAttribute(attr, tr(element.getAttribute(attr)));
  }
  const observer = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'characterData') {
        const raw = record.target.nodeValue, trimmed = raw.trim();
        if (trimmed) { const translated = tr(trimmed); if (translated !== trimmed) record.target.nodeValue = raw.replace(trimmed, translated); }
      } else for (const node of record.addedNodes) {
        if (node.nodeType === Node.TEXT_NODE) { const raw=node.nodeValue, trimmed=raw.trim(); if (trimmed) node.nodeValue=raw.replace(trimmed,tr(trimmed)); }
        else if (node.nodeType === Node.ELEMENT_NODE) {
          const sub=document.createTreeWalker(node,NodeFilter.SHOW_TEXT); let child;
          while ((child=sub.nextNode())) { const raw=child.nodeValue, trimmed=raw.trim(); if (trimmed) child.nodeValue=raw.replace(trimmed,tr(trimmed)); }
        }
      }
    }
  });
  observer.observe(document.body,{subtree:true,childList:true,characterData:true});
}
