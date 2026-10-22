// ======================== EAP (B/3) ========================
// Turmas do calendário da DEC, escala do efetivo e Ordem de Serviço.
// Backend em webapp/routers/eap.py. Usa API, authHeaders() e apiFetch() do
// dashboard.html.

const EAP = {
  iniciado: false,
  ano: null,            // null = o backend escolhe o ano da próxima turma
  turmas: [],
  anos: [],
  publicos: [],
  sub: 'calendario',
  editId: null,
  busca: [],
  buscaTimer: null,
  pendAberto: false,
  osSel: new Set(),
  osDados: null,
};

function eapEsc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// 'YYYY-MM-DD' (ou ISO com hora) -> dd/mm/aa
function eapData(d, comAno = true) {
  if (!d) return '—';
  const [a, m, dia] = String(d).slice(0, 10).split('-');
  return comAno ? `${dia}/${m}/${a.slice(2)}` : `${dia}/${m}`;
}

function eapHora(d) {
  return d && String(d).length > 10 ? String(d).slice(11, 16) : '';
}

async function eapApi(method, url, body) {
  const res = await fetch(API + url, {
    method, headers: authHeaders(), body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401) { logout(); return null; }
  if (!res.ok) {
    let detail = null;
    try { detail = (await res.json())?.detail; } catch {}
    throw new Error(typeof detail === 'string' ? detail : `Erro ${res.status}`);
  }
  return res.json();
}

async function loadEap() {
  if (!EAP.iniciado) {
    EAP.iniciado = true;
    document.addEventListener('click', e => {
      if (!e.target.closest('#eapResultados') && e.target.id !== 'eapBusca') eapFecharBusca();
    });
  }
  await eapCarregar();
  eapSubtab(EAP.sub);
}

async function eapCarregar() {
  const sel = document.getElementById('eapAno');
  if (sel.value) EAP.ano = parseInt(sel.value);
  try {
    const d = await apiFetch(EAP.ano ? `/eap/turmas?ano=${EAP.ano}` : '/eap/turmas');
    if (!d) return;
    EAP.ano = d.ano;
    EAP.turmas = d.turmas;
    EAP.anos = d.anos;
    EAP.publicos = d.publicos;

    const atual = new Date().getFullYear();
    const anos = [...new Set([atual + 1, atual, ...d.anos])].sort((a, b) => b - a);
    sel.innerHTML = anos.map(a => `<option value="${a}" ${a === EAP.ano ? 'selected' : ''}>${a}</option>`).join('');

    if (!document.getElementById('eapFPublicos').children.length) { eapRenderChecksPublico(); eapRenderLocais(EAP_LOCAIS[0]); }

    const r = d.resumo;
    document.getElementById('eapObrigados').textContent = r.obrigados;
    document.getElementById('eapEscalados').textContent = r.escalados;
    document.getElementById('eapPendentes').textContent = r.pendentes;
    document.getElementById('eapQtdTurmas').textContent = d.turmas.length;
    document.getElementById('eapBarra').style.width = r.obrigados ? `${(100 * r.escalados / r.obrigados).toFixed(1)}%` : '0%';

    eapRenderTurmas();
    eapRenderSelectTurma();
    eapRenderOsTurmas();
  } catch (e) {
    document.getElementById('eapTurmasBody').innerHTML =
      `<tr><td colspan="6" class="px-4 py-6 text-center text-red-400 text-sm">${eapEsc(e.message)}</td></tr>`;
  }
}

function eapSubtab(name) {
  EAP.sub = name;
  const ativo = 'px-4 py-2 text-sm font-semibold rounded-t-lg border border-b-0 bg-gray-900 text-white border-gray-800 -mb-px';
  const inativo = 'px-4 py-2 text-sm font-semibold rounded-t-lg border border-b-0 bg-transparent text-gray-500 border-transparent hover:text-gray-300';
  ['calendario', 'escala', 'os'].forEach(s => {
    document.getElementById(`eapBtn-${s}`).className = s === name ? ativo : inativo;
    document.getElementById(`eapCnt-${s}`).classList.toggle('hidden', s !== name);
  });
  if (name === 'escala') eapCarregarInscritos();
  if (name === 'os') eapModeloInfo();
}

// Uma turma = um EaD; cada público tem o número dele na DEC.
// "Turma V (Oficiais) + XIV (Cb/Sd)"
function eapRotuloTurma(t) {
  return 'Turma ' + (t.publicos || []).map(p => `${p.turma} (${p.publico})`).join(' + ');
}

function eapPublicosTxt(t) {
  return (t.publicos || []).map(p => p.publico).join(', ');
}

// ---------------------- CALENDÁRIO ----------------------

function eapRenderTurmas() {
  const body = document.getElementById('eapTurmasBody');
  if (!EAP.turmas.length) {
    body.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-gray-500 text-sm">
      Nenhuma turma cadastrada em ${EAP.ano}. Lance acima as turmas do calendário da DEC.
      ${EAP.anos.filter(a => a !== EAP.ano).length ? `<div class="mt-1 text-amber-400">Há turmas em ${EAP.anos.filter(a => a !== EAP.ano).join(', ')} — troque o ano no alto da tela.</div>` : ''}</td></tr>`;
    return;
  }
  const hoje = new Date().toISOString().slice(0, 10);
  body.innerHTML = EAP.turmas.map(t => {
    const fim = t.presencial_em ? String(t.presencial_em).slice(0, 10) : t.ead_fim;
    const status = fim < hoje ? '<span class="text-[10px] text-gray-600 ml-1">encerrada</span>'
      : t.ead_inicio <= hoje ? '<span class="text-[10px] text-emerald-400 ml-1">em andamento</span>' : '';
    const vagas = t.vagas ? ` / ${t.vagas}` : '';
    return `<tr class="table-row border-b border-gray-800/60">
      <td class="px-4 py-2.5 text-white font-semibold">${t.publicos.map(p => eapEsc(p.turma)).join(' + ')}${status}</td>
      <td class="px-4 py-2.5 text-gray-300">${t.publicos.map(p => `<div><span class="text-gray-500 font-mono text-xs mr-1">${eapEsc(p.turma)}</span>${eapEsc(p.publico)}</div>`).join('')}</td>
      <td class="px-4 py-2.5 text-gray-300 whitespace-nowrap">${eapData(t.ead_inicio)} a ${eapData(t.ead_fim)}</td>
      <td class="px-4 py-2.5 text-gray-300">${t.presencial_em ? `${eapData(t.presencial_em)} ${eapHora(t.presencial_em)}` : '<span class="text-gray-600">—</span>'}
        ${t.presencial_local ? `<div class="text-[11px] text-gray-500 truncate max-w-xs" title="${eapEsc(t.presencial_local)}">${eapEsc(t.presencial_local)}</div>` : ''}</td>
      <td class="px-4 py-2.5 text-right whitespace-nowrap"><span class="text-emerald-400 font-semibold">${t.escalados}</span><span class="text-gray-500">${vagas}</span>
        ${t.inscritos > t.escalados ? `<div class="text-[10px] text-gray-500">+${t.inscritos - t.escalados} só inscritos</div>` : ''}</td>
      <td class="px-4 py-2.5 text-right whitespace-nowrap">
        <button onclick="eapIrEscalar(${t.id})" class="text-sky-400 hover:text-sky-300 text-xs mr-3">Escalar</button>
        <button onclick="eapEditarTurma(${t.id})" class="text-gray-400 hover:text-white text-xs mr-3">Editar</button>
        <button onclick="eapExcluirTurma(${t.id})" class="text-gray-600 hover:text-red-400 text-xs">Excluir</button>
      </td></tr>`;
  }).join('');
}

// Locais do presencial. O texto vai como está para a OS ("... no dia
// 190800NOV26 no <local> e incluirá ..."). Local novo: acrescentar aqui.
const EAP_LOCAIS = [
  'Poliesportivo João do Pulo, Av. Perseu 180 – Jardim Satélite, São José dos Campos',
  'EB Aparecida - Av. Isaac Ferreira Encarnação n° 800, Aparecida',
];

// Lista de locais; um local antigo, fora da lista, continua aparecendo
// para a edição da turma não apagá-lo sem querer.
function eapRenderLocais(atual = '') {
  const extra = atual && !EAP_LOCAIS.includes(atual) ? [atual] : [];
  document.getElementById('eapFLocal').innerHTML = '<option value="">— a definir —</option>' +
    [...EAP_LOCAIS, ...extra].map(l => `<option value="${eapEsc(l)}" ${l === atual ? 'selected' : ''}>${eapEsc(l)}</option>`).join('');
}

// Um check por público, com o número da turma ao lado. O número só abre
// quando o público está marcado.
function eapRenderChecksPublico() {
  document.getElementById('eapFPublicos').innerHTML = EAP.publicos.map((p, i) => `
    <label class="flex items-center gap-2 rounded-lg border border-gray-800 px-3 py-1.5 text-sm text-gray-300 select-none">
      <input type="checkbox" id="eapFPub${i}" data-publico="${eapEsc(p)}" onchange="eapCheckPublico(${i})" class="accent-red-600">
      <span class="whitespace-nowrap">${eapEsc(p)}</span>
      <input id="eapFNum${i}" placeholder="nº" disabled class="input-field w-16 rounded px-2 py-0.5 text-sm uppercase disabled:opacity-30">
    </label>`).join('');
}

function eapCheckPublico(i) {
  const on = document.getElementById(`eapFPub${i}`).checked;
  const num = document.getElementById(`eapFNum${i}`);
  num.disabled = !on;
  if (on) num.focus(); else num.value = '';
}

function eapSetPublicos(lista) {
  EAP.publicos.forEach((p, i) => {
    const sel = (lista || []).find(x => x.publico === p);
    document.getElementById(`eapFPub${i}`).checked = !!sel;
    const num = document.getElementById(`eapFNum${i}`);
    num.value = sel ? sel.turma : '';
    num.disabled = !sel;
  });
}

function eapLerPublicos() {
  return EAP.publicos.map((p, i) => document.getElementById(`eapFPub${i}`).checked
    ? { publico: p, turma: document.getElementById(`eapFNum${i}`).value.trim().toUpperCase() } : null).filter(Boolean);
}

function eapLimparForm() {
  EAP.editId = null;
  document.querySelectorAll('#eapCnt-calendario .ring-red-500').forEach(el => eapMarcarCampo(el, false));
  eapSetPublicos([]);
  ['eapFIni', 'eapFFim', 'eapFPres', 'eapFVagas', 'eapFObs'].forEach(id => document.getElementById(id).value = '');
  eapRenderLocais(EAP_LOCAIS[0]);
  document.getElementById('eapFormTitulo').textContent = 'Nova turma (calendário da DEC)';
  document.getElementById('eapFormCancelar').classList.add('hidden');
  document.getElementById('eapFSalvar').textContent = 'Salvar';
  document.getElementById('eapFErro').classList.add('hidden');
}

function eapEditarTurma(id) {
  const t = EAP.turmas.find(x => x.id === id);
  if (!t) return;
  EAP.editId = id;
  eapSetPublicos(t.publicos);
  document.getElementById('eapFIni').value = t.ead_inicio;
  document.getElementById('eapFFim').value = t.ead_fim;
  document.getElementById('eapFPres').value = t.presencial_em ? String(t.presencial_em).slice(0, 16) : '';
  document.getElementById('eapFVagas').value = t.vagas ?? '';
  eapRenderLocais(t.presencial_local ?? '');
  document.getElementById('eapFObs').value = t.observacao ?? '';
  document.getElementById('eapFormTitulo').textContent = `Editando ${eapRotuloTurma(t)}`;
  document.getElementById('eapFormCancelar').classList.remove('hidden');
  document.getElementById('eapFSalvar').textContent = 'Salvar alteração';
  document.getElementById('eapFIni').focus();
}

// Turma só é salva com tudo preenchido (observação é opcional). O
// presencial (data e local) é dos praças: turma só de Oficiais não pede —
// o deles é na ESB, por convocação. Campo faltando fica com borda vermelha
// até ser preenchido.
function eapMarcarCampo(el, faltando) {
  el.classList.toggle('!border-red-500', faltando);
  el.classList.toggle('ring-1', faltando);
  el.classList.toggle('ring-red-500', faltando);
  if (faltando && !el.dataset.vigia) {
    el.dataset.vigia = '1';
    const limpa = () => { el.classList.remove('!border-red-500', 'ring-1', 'ring-red-500'); };
    el.addEventListener('input', limpa);
    el.addEventListener('change', limpa);
  }
}

function eapCamposFaltando(d) {
  const faltam = [];
  const marca = (id, vazio, nome) => { eapMarcarCampo(document.getElementById(id), vazio); if (vazio) faltam.push(nome); };

  const box = document.getElementById('eapFPublicos');
  eapMarcarCampo(box, !d.publicos.length);
  if (!d.publicos.length) faltam.push('público');
  EAP.publicos.forEach((p, i) => {
    const on = document.getElementById(`eapFPub${i}`).checked;
    marca(`eapFNum${i}`, on && !document.getElementById(`eapFNum${i}`).value.trim(), `nº da turma de ${p}`);
  });

  const soOficiais = d.publicos.length && d.publicos.every(p => p.publico === 'Oficiais');
  marca('eapFIni', !d.ead_inicio, 'EaD início');
  marca('eapFFim', !d.ead_fim, 'EaD fim');
  marca('eapFPres', !soOficiais && !d.presencial_em, 'presencial');
  marca('eapFLocal', !soOficiais && !d.presencial_local, 'local do presencial');
  marca('eapFVagas', !(d.vagas > 0), 'vagas');
  if (d.ead_inicio && d.ead_fim && d.ead_fim < d.ead_inicio) {
    eapMarcarCampo(document.getElementById('eapFFim'), true);
    faltam.push('EaD fim antes do início');
  }
  return faltam;
}

async function eapSalvarTurma() {
  const v = id => document.getElementById(id).value.trim();
  const erro = document.getElementById('eapFErro');
  const ini = v('eapFIni');
  const dados = {
    ano: ini ? parseInt(ini.slice(0, 4)) : EAP.ano,
    publicos: eapLerPublicos(),
    ead_inicio: ini || null, ead_fim: v('eapFFim') || null,
    presencial_em: v('eapFPres') || null, presencial_local: v('eapFLocal') || null,
    vagas: v('eapFVagas') ? parseInt(v('eapFVagas')) : null, observacao: v('eapFObs') || null,
  };
  const faltam = eapCamposFaltando(dados);
  if (faltam.length) {
    erro.textContent = 'Preencha os campos em vermelho: ' + faltam.join(', ') + '.';
    erro.classList.remove('hidden');
    return;
  }
  erro.classList.add('hidden');
  try {
    if (EAP.editId) await eapApi('PUT', `/eap/turmas/${EAP.editId}`, dados);
    else await eapApi('POST', '/eap/turmas', dados);
    EAP.ano = dados.ano;
    document.getElementById('eapAno').value = '';
    eapLimparForm();
    await eapCarregar();
  } catch (e) {
    erro.textContent = e.message;
    erro.classList.remove('hidden');
  }
}

async function eapExcluirTurma(id) {
  const t = EAP.turmas.find(x => x.id === id);
  if (!t) return;
  const aviso = t.inscritos ? `\n\nOs ${t.inscritos} militares inscritos nela saem junto.` : '';
  if (!confirm(`Excluir ${eapRotuloTurma(t)} de ${t.ano}?${aviso}`)) return;
  try {
    await eapApi('DELETE', `/eap/turmas/${id}`);
    await eapCarregar();
  } catch (e) { alert(e.message); }
}

function eapIrEscalar(id) {
  document.getElementById('eapEscTurma').value = id;
  eapSubtab('escala');
}

// ---------------------- ESCALA ----------------------

function eapRenderSelectTurma() {
  const sel = document.getElementById('eapEscTurma');
  const atual = sel.value;
  sel.innerHTML = EAP.turmas.length
    ? EAP.turmas.map(t => `<option value="${t.id}">${eapEsc(eapRotuloTurma(t))} (EaD ${eapData(t.ead_inicio, false)} a ${eapData(t.ead_fim)})</option>`).join('')
    : '<option value="">Nenhuma turma no ano</option>';
  if (EAP.turmas.some(t => String(t.id) === atual)) sel.value = atual;
  else {
    // Sem escolha anterior: a próxima turma que ainda não acabou.
    const hoje = new Date().toISOString().slice(0, 10);
    const prox = EAP.turmas.find(t => t.ead_fim >= hoje);
    if (prox) sel.value = prox.id;
  }
}

function eapTurmaSel() {
  const id = parseInt(document.getElementById('eapEscTurma').value);
  return EAP.turmas.find(t => t.id === id) || null;
}

const EAP_MOTIVO = {
  'FERIAS': 'Férias', 'FERIAS SOBRESTADAS': 'Férias sobrestadas', 'CONVALESCENCA': 'Convalescença',
  'LICENCA-PREMIO': 'LP', 'DISPENSA DO SERVICO': 'Dispensa', 'LUTO': 'Luto', 'NUPCIAS': 'Núpcias',
  'LICENCA-GESTANTE': 'Lic. gestante', 'LICENÇA-PATERNIDADE': 'Lic. paternidade', 'LICENÇA TRAT. SAÚDE': 'LTS',
};

function eapBadge(cor, txt, title = '') {
  return `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold whitespace-nowrap ${cor}" ${title ? `title="${eapEsc(title)}"` : ''}>${txt}</span>`;
}

function eapBadgeIas(m) {
  if (m.ias === 'EM DIA') return eapBadge('bg-emerald-900/40 text-emerald-300', `Em dia até ${eapData(m.ias_validade)}`);
  if (m.ias === 'VENCE ANTES') return eapBadge('bg-amber-900/40 text-amber-300', `Vence ${eapData(m.ias_validade)}`,
    `Em dia hoje, mas vence antes do presencial (${eapData(m.ias_referencia)})`);
  if (m.ias === 'ATRASADA') return eapBadge('bg-red-900/40 text-red-300', `Vencida ${eapData(m.ias_validade)}`);
  return eapBadge('bg-red-900/40 text-red-300', 'Sem IAS');
}

function eapBadgesAfast(m) {
  const b = m.afastamentos.map(a =>
    eapBadge('bg-orange-900/40 text-orange-300', `${eapEsc(EAP_MOTIVO[a.motivo] || a.motivo)} ${eapData(a.inicio, false)}–${a.fim ? eapData(a.fim, false) : '?'}`,
      `${a.motivo} de ${eapData(a.inicio)} a ${eapData(a.fim)}`));
  m.restricoes.forEach(r => {
    const ate = r.fim ? ` até ${eapData(r.fim, false)}` : '';
    if ((r.tipo || '').startsWith('Licen')) b.push(eapBadge('bg-orange-900/40 text-orange-300', `LTS${ate}`, r.tipo));
    else if (r.tipo === 'Apto com Restrição') b.push(eapBadge('bg-sky-900/40 text-sky-300', `Restrição médica${ate}`,
      'Com restrição médica faz só o EaD (36 h)'));
    else b.push(eapBadge('bg-gray-700 text-gray-300', eapEsc(r.tipo || 'SIGS') + ate));
  });
  return b.length ? b.join(' ') : '<span class="text-gray-600 text-xs">—</span>';
}

// Avisos que não são IAS nem afastamento: dispensa, outra turma, público.
function eapBadgesExtra(m, turmaId) {
  const b = [];
  if (m.dispensa) b.push(eapBadge('bg-gray-700 text-gray-300', `Dispensado${m.dispensa === 'CAO' ? ': CAO' : ''}`, m.dispensa));
  if (m.publico_ok === false) b.push(eapBadge('bg-fuchsia-900/40 text-fuchsia-300', 'Fora do público da turma'));
  (m.turmas_ano || []).filter(t => t.turma_id !== turmaId).forEach(t =>
    b.push(eapBadge('bg-violet-900/40 text-violet-300', `${t.escalado ? 'Escalado' : 'Inscrito'} na ${eapEsc(eapRotuloTurma(t))}`)));
  return b.join(' ');
}

function eapBotaoCao(m) {
  if (m.posto_qpo !== 'Cap PM') return '';
  return m.dispensa === 'CAO'
    ? `<button onclick="eapCao(${m.re}, false)" class="text-[11px] text-gray-500 hover:text-white ml-2">tirar CAO</button>`
    : `<button onclick="eapCao(${m.re}, true)" class="text-[11px] text-gray-500 hover:text-white ml-2">possui CAO</button>`;
}

function eapMilitarCelula(m, turmaId) {
  return `<div class="text-white font-medium">${eapEsc(m.nome)}</div>
    <div class="text-[11px] text-gray-500"><span class="font-mono">${eapEsc(m.re_completo)}</span> · ${eapEsc(m.posto_grad)}${eapBotaoCao(m)}</div>
    ${eapBadgesExtra(m, turmaId) ? `<div class="mt-1 flex flex-wrap gap-1">${eapBadgesExtra(m, turmaId)}</div>` : ''}`;
}

async function eapCarregarInscritos() {
  const t = eapTurmaSel();
  const body = document.getElementById('eapInscBody');
  const info = document.getElementById('eapEscTurmaInfo');
  if (!t) {
    body.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-gray-500 text-sm">Cadastre uma turma no Calendário primeiro.</td></tr>`;
    info.textContent = '';
    document.getElementById('eapInscQtd').textContent = '';
    return;
  }
  info.innerHTML = `EaD ${eapData(t.ead_inicio)} a ${eapData(t.ead_fim)}` +
    (t.presencial_em ? ` · presencial ${eapData(t.presencial_em)} ${eapHora(t.presencial_em)}` : ' · presencial sem data') +
    ` · IAS conferida na data do presencial`;
  try {
    const d = await apiFetch(`/eap/turmas/${t.id}/inscritos`);
    if (!d) return;
    const esc = d.inscritos.filter(m => m.escalado).length;
    document.getElementById('eapInscQtd').textContent =
      `— ${esc} escalado${esc === 1 ? '' : 's'} de ${d.inscritos.length}${t.vagas ? ` · ${t.vagas} vagas` : ''}`;
    let html = d.inscritos.map(m => `<tr class="table-row border-b border-gray-800/60 ${m.escalado ? '' : 'opacity-70'}">
      <td class="px-3 py-2.5 text-center"><input type="checkbox" ${m.escalado ? 'checked' : ''} class="accent-red-600 w-4 h-4"
           onchange="eapMarcar(${m.re}, this.checked)"></td>
      <td class="px-3 py-2.5">${eapMilitarCelula(m, t.id)}</td>
      <td class="px-3 py-2.5 text-gray-400 text-xs">${eapEsc(m.lotacao)}<div class="text-gray-600">${eapEsc(m.opm_atual || '')}</div></td>
      <td class="px-3 py-2.5">${eapBadgeIas(m)}</td>
      <td class="px-3 py-2.5"><div class="flex flex-wrap gap-1">${eapBadgesAfast(m)}</div></td>
      <td class="px-3 py-2.5 text-right"><button onclick="eapRemover(${m.re})" class="text-gray-600 hover:text-red-400 text-xs">Remover</button></td>
    </tr>`).join('');
    if (d.fora_do_efetivo.length) {
      html += `<tr><td colspan="6" class="px-3 py-2 text-[11px] text-amber-400">
        Fora do efetivo ativo (não entram na OS): ${d.fora_do_efetivo.join(', ')}
        ${d.fora_do_efetivo.map(re => `<button onclick="eapRemover(${re})" class="text-gray-500 hover:text-red-400 ml-1">remover ${re}</button>`).join('')}</td></tr>`;
    }
    body.innerHTML = html || `<tr><td colspan="6" class="px-4 py-8 text-center text-gray-500 text-sm">
      Ninguém nesta turma ainda. Digite o RE acima para adicionar.</td></tr>`;
    if (EAP.pendAberto) eapCarregarPendentes();
  } catch (e) {
    body.innerHTML = `<tr><td colspan="6" class="px-4 py-6 text-center text-red-400 text-sm">${eapEsc(e.message)}</td></tr>`;
  }
}

function eapBuscar() {
  clearTimeout(EAP.buscaTimer);
  const q = document.getElementById('eapBusca').value.trim();
  if (q.length < (/^\d+$/.test(q) ? 2 : 3)) { eapFecharBusca(); return; }
  EAP.buscaTimer = setTimeout(async () => {
    const t = eapTurmaSel();
    try {
      const lista = await apiFetch(`/eap/militares?q=${encodeURIComponent(q)}${t ? `&turma_id=${t.id}` : ''}`);
      if (!lista || document.getElementById('eapBusca').value.trim() !== q) return;
      EAP.busca = lista;
      eapRenderBusca(t);
    } catch (e) { console.error('EAP busca:', e); }
  }, 200);
}

function eapRenderBusca(t) {
  const box = document.getElementById('eapResultados');
  if (!EAP.busca.length) {
    box.innerHTML = '<div class="px-4 py-3 text-sm text-gray-500">Nenhum militar ativo encontrado.</div>';
    box.classList.remove('hidden');
    return;
  }
  const jaEscalar = document.getElementById('eapJaEscalar').checked;
  box.innerHTML = EAP.busca.map((m, i) => {
    const naTurma = t && (m.turmas_ano || []).some(x => x.turma_id === t.id);
    const acao = !t ? '' : naTurma
      ? '<span class="text-[11px] text-gray-500">já na turma</span>'
      : `<label class="flex items-center gap-1 text-[11px] text-gray-400 select-none"><input type="checkbox" id="eapEscRes${i}" ${jaEscalar ? 'checked' : ''} class="accent-red-600"> escalar</label>
         <button onclick="eapAdicionar(${m.re}, document.getElementById('eapEscRes${i}').checked)"
                 class="bg-red-700 hover:bg-red-600 text-white rounded px-2.5 py-1 text-xs font-semibold">Adicionar</button>`;
    return `<div class="px-4 py-2.5 border-b border-gray-800 last:border-0 hover:bg-gray-900/60 flex items-start gap-3 ${i === 0 ? 'bg-gray-900/40' : ''}">
      <div class="flex-1 min-w-0">
        ${eapMilitarCelula(m, t?.id)}
        <div class="mt-1 flex flex-wrap gap-1 items-center"><span class="text-[10px] text-gray-500 mr-1">${eapEsc(m.lotacao)} · IAS</span>${eapBadgeIas(m)} ${eapBadgesAfast(m)}</div>
      </div>
      <div class="flex items-center gap-2 pt-0.5">${acao}</div>
    </div>`;
  }).join('');
  box.classList.remove('hidden');
}

function eapFecharBusca() {
  document.getElementById('eapResultados')?.classList.add('hidden');
}

function eapBuscaTecla(e) {
  if (e.key === 'Escape') { eapFecharBusca(); return; }
  if (e.key !== 'Enter') return;
  e.preventDefault();
  const t = eapTurmaSel();
  const m = EAP.busca[0];
  if (!t || !m || (m.turmas_ano || []).some(x => x.turma_id === t.id)) return;
  const chk = document.getElementById('eapEscRes0');
  eapAdicionar(m.re, chk ? chk.checked : document.getElementById('eapJaEscalar').checked);
}

async function eapAdicionar(re, escalado) {
  const t = eapTurmaSel();
  if (!t) return;
  try {
    await eapApi('POST', `/eap/turmas/${t.id}/inscritos`, { re, escalado });
    const inp = document.getElementById('eapBusca');
    inp.value = '';
    eapFecharBusca();
    inp.focus();
    await eapCarregarInscritos();
    eapAtualizarResumo();
  } catch (e) { alert(e.message); }
}

async function eapMarcar(re, escalado) {
  const t = eapTurmaSel();
  try {
    await eapApi('PATCH', `/eap/turmas/${t.id}/inscritos/${re}`, { escalado });
    await eapCarregarInscritos();
    eapAtualizarResumo();
  } catch (e) { alert(e.message); }
}

async function eapRemover(re) {
  const t = eapTurmaSel();
  try {
    await eapApi('DELETE', `/eap/turmas/${t.id}/inscritos/${re}`);
    await eapCarregarInscritos();
    eapAtualizarResumo();
  } catch (e) { alert(e.message); }
}

async function eapCao(re, possui) {
  try {
    await eapApi(possui ? 'POST' : 'DELETE', `/eap/dispensa/${re}`);
    if (document.getElementById('eapBusca').value.trim()) eapBuscar();
    await eapCarregarInscritos();
    eapAtualizarResumo();
  } catch (e) { alert(e.message); }
}

// Recarrega cards e contadores; a sub-aba aberta continua a mesma.
function eapAtualizarResumo() {
  return eapCarregar();
}

function eapTogglePendentes() {
  EAP.pendAberto = !EAP.pendAberto;
  document.getElementById('eapPendBox').classList.toggle('hidden', !EAP.pendAberto);
  document.getElementById('eapBtnPend').textContent = EAP.pendAberto
    ? 'Esconder quem ainda não tem turma' : 'Mostrar quem ainda não tem turma no ano';
  if (EAP.pendAberto) eapCarregarPendentes();
}

async function eapCarregarPendentes() {
  const t = eapTurmaSel();
  const body = document.getElementById('eapPendBody');
  body.innerHTML = '<tr><td colspan="5" class="px-4 py-6 text-center text-gray-500 text-sm">Carregando…</td></tr>';
  try {
    const lista = await apiFetch(`/eap/pendentes?ano=${EAP.ano}${t ? `&turma_id=${t.id}` : ''}`);
    if (!lista) return;
    document.getElementById('eapPendQtd').textContent =
      `— ${lista.length}${t ? ` do público ${eapPublicosTxt(t)}` : ''}`;
    body.innerHTML = lista.map(m => {
      const naTurma = t && (m.turmas_ano || []).some(x => x.turma_id === t.id);
      return `<tr class="table-row border-b border-gray-800/60">
        <td class="px-3 py-2">${eapMilitarCelula(m, t?.id)}</td>
        <td class="px-3 py-2 text-gray-400 text-xs">${eapEsc(m.lotacao)}<div class="text-gray-600">${eapEsc(m.opm_atual || '')}</div></td>
        <td class="px-3 py-2">${eapBadgeIas(m)}</td>
        <td class="px-3 py-2"><div class="flex flex-wrap gap-1">${eapBadgesAfast(m)}</div></td>
        <td class="px-3 py-2 text-right whitespace-nowrap">${!t ? '' : naTurma ? '<span class="text-[11px] text-gray-500">inscrito</span>'
          : `<button onclick="eapAdicionar(${m.re}, document.getElementById('eapJaEscalar').checked)" class="text-sky-400 hover:text-sky-300 text-xs">+ Adicionar</button>`}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="5" class="px-4 py-6 text-center text-emerald-400 text-sm">Todo mundo deste público já está escalado no ano.</td></tr>';
  } catch (e) {
    body.innerHTML = `<tr><td colspan="5" class="px-4 py-6 text-center text-red-400 text-sm">${eapEsc(e.message)}</td></tr>`;
  }
}

// ---------------------- ORDEM DE SERVIÇO ----------------------

const EAP_CAMPOS_OS = [
  ['numero', 'Número da OS', 'ex: 073'],
  ['data_extenso', 'Data do documento', '19 de outubro de 2026'],
  ['ano2', 'Ano (2 dígitos) no número', '26'],
  ['ano', 'Ano do EAP', '2026'],
  ['destinatarios', 'Aos Cmt do…', '1º SGB e 4º SGB, SAdm, SAT e COBOM', true],
  ['assunto', 'Assunto', '', true],
  ['periodo_ead', 'Período do EaD', '26OUT26 a 13NOV26'],
  ['publico_pracas', 'Público do presencial (praças)', 'Cb/Sd PM', false, 'pracas'],
  ['presencial_pracas', 'Presencial — data-hora (praças)', '190800NOV26', false, 'pracas'],
  ['local_pracas', 'Local do presencial (praças)', '', true, 'pracas'],
  ['assinante_nome', 'Assinante — nome', 'FULANO DE TAL SILVA'],
  ['assinante_funcao', 'Assinante — posto e função', 'Cap PM Subcomandante Interino'],
];

function eapRenderOsTurmas() {
  const box = document.getElementById('eapOsTurmas');
  EAP.osSel = new Set([...EAP.osSel].filter(id => EAP.turmas.some(t => t.id === id)));
  box.innerHTML = EAP.turmas.length ? EAP.turmas.map(t => {
    const on = EAP.osSel.has(t.id);
    return `<button onclick="eapOsToggle(${t.id})" class="px-3 py-2 rounded-lg border text-left text-xs ${on
      ? 'border-red-600 bg-red-900/30 text-white' : 'border-gray-700 text-gray-400 hover:border-gray-500'}">
      <div class="font-semibold">${eapEsc(eapRotuloTurma(t))}</div>
      <div class="text-[11px] ${on ? 'text-gray-300' : 'text-gray-500'}">EaD ${eapData(t.ead_inicio, false)} a ${eapData(t.ead_fim)} · ${t.escalados} escalados</div>
    </button>`;
  }).join('') : '<div class="text-sm text-gray-500">Nenhuma turma no ano.</div>';
  if (!EAP.osSel.size) {
    document.getElementById('eapOsForm').classList.add('hidden');
    document.getElementById('eapOsLista').classList.add('hidden');
  }
}

async function eapOsToggle(id) {
  const t = EAP.turmas.find(x => x.id === id);
  if (EAP.osSel.has(id)) EAP.osSel.delete(id);
  else {
    // Ajuda: ao escolher a 1ª turma, já marca as outras do mesmo período.
    if (!EAP.osSel.size && t) EAP.turmas.filter(x => x.id !== id && x.ead_inicio === t.ead_inicio && x.ead_fim === t.ead_fim)
      .forEach(x => EAP.osSel.add(x.id));
    EAP.osSel.add(id);
  }
  eapRenderOsTurmas();
  if (EAP.osSel.size) await eapOsPreencher();
}

// Quem assina é sempre o Subcomando; a pessoa muda (Maj ou Ten Cel, ou um
// Capitão como interino). Lista dos oficiais ativos, por antiguidade.
function eapSelectAssinante(lista, atual) {
  const nomes = lista.map(o => o.nome);
  // Assinante da OS anterior que já saiu do efetivo continua escolhível.
  const extra = atual && !nomes.includes(atual) ? `<option value="${eapEsc(atual)}" selected>${eapEsc(atual)}</option>` : '';
  return `<select id="eapOs_assinante_nome" onchange="eapAssinanteMudou()" class="input-field w-full rounded-lg px-2 py-1.5 text-sm">
    <option value="">— escolha o oficial —</option>${extra}
    ${lista.map(o => `<option value="${eapEsc(o.nome)}" ${o.nome === atual ? 'selected' : ''}>${eapEsc(o.posto)} ${eapEsc(o.nome)}</option>`).join('')}
  </select>`;
}

function eapAssinanteMudou() {
  const nome = document.getElementById('eapOs_assinante_nome').value;
  const o = (EAP.osDados?.assinantes || []).find(x => x.nome === nome);
  if (o) document.getElementById('eapOs_assinante_funcao').value = o.funcao;
}

async function eapOsPreencher() {
  // Mantém o que a pessoa já digitou (número, assinante) ao trocar de turma.
  const digitado = {};
  EAP_CAMPOS_OS.forEach(([k]) => { const el = document.getElementById(`eapOs_${k}`); if (el) digitado[k] = el.value; });
  try {
    const d = await apiFetch(`/eap/os/sugestao?turmas=${[...EAP.osSel].join(',')}`);
    if (!d) return;
    EAP.osDados = d;
    const manter = ['numero', 'assinante_nome', 'assinante_funcao', 'data_extenso'];
    document.getElementById('eapOsCampos').innerHTML = EAP_CAMPOS_OS
      .filter(([, , , , so]) => !so || (so === 'pracas' && d.tem_pracas))
      .map(([k, rotulo, ph, largo]) => {
        const val = manter.includes(k) && digitado[k] ? digitado[k] : (d.campos[k] ?? '');
        const rot = `<label class="block text-[11px] uppercase tracking-wider text-gray-500 mb-1">${rotulo}</label>`;
        if (k === 'assinante_nome') return `<div>${rot}${eapSelectAssinante(d.assinantes || [], val)}</div>`;
        return `<div class="${largo ? 'md:col-span-2' : ''}">${rot}
          <input id="eapOs_${k}" value="${eapEsc(val)}" placeholder="${eapEsc(ph)}" class="input-field w-full rounded-lg px-2 py-1.5 text-sm"></div>`;
      }).join('');

    const avisos = [];
    if (!d.militares.length) avisos.push(['red', 'Nenhum militar escalado nas turmas escolhidas.']);
    if (d.sem_digito.length) avisos.push(['amber', `RE sem dígito no cadastro (sai sem o "-X"): ${d.sem_digito.join(', ')}. Ele vem do relatório de efetivo do SGP.`]);
    if (d.periodos_diferentes) avisos.push(['amber', 'As turmas escolhidas têm períodos de EaD diferentes — confira o campo "Período do EaD".']);
    avisos.push(['gray', `Usando o ${d.modelo}. Itens do presencial: ${d.tem_pracas ? 'praças' : ''}${d.tem_pracas && d.tem_oficiais ? ' e ' : ''}${d.tem_oficiais ? 'oficiais (ESB)' : ''}.`]);
    const cor = { red: 'text-red-400', amber: 'text-amber-400', gray: 'text-gray-500' };
    document.getElementById('eapOsAvisos').innerHTML = avisos.map(([c, t]) => `<div class="text-xs ${cor[c]}">${eapEsc(t)}</div>`).join('');

    document.getElementById('eapOsQtd').textContent = `— ${d.militares.length}`;
    document.getElementById('eapOsMilitares').innerHTML = d.militares
      .map((m, i) => `<div><span class="text-gray-600">1.${i + 1}.</span> ${eapEsc(m)}</div>`).join('');
    document.getElementById('eapOsForm').classList.remove('hidden');
    document.getElementById('eapOsLista').classList.remove('hidden');
    document.getElementById('eapOsMsg').textContent = '';
  } catch (e) {
    document.getElementById('eapOsAvisos').innerHTML = `<div class="text-xs text-red-400">${eapEsc(e.message)}</div>`;
  }
}

function eapNomeArquivo(res, padrao) {
  const cd = res.headers.get('Content-Disposition') || '';
  const m = cd.match(/filename\*=UTF-8''([^;]+)/) || cd.match(/filename="?([^";]+)/);
  return m ? decodeURIComponent(m[1]) : padrao;
}

async function eapBaixarBlob(res, padrao) {
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = eapNomeArquivo(res, padrao);
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

async function eapGerarOs() {
  const campos = {};
  EAP_CAMPOS_OS.forEach(([k]) => { const el = document.getElementById(`eapOs_${k}`); if (el) campos[k] = el.value; });
  const msg = document.getElementById('eapOsMsg');
  const btn = document.getElementById('eapOsGerar');
  btn.disabled = true;
  msg.className = 'text-xs text-gray-500';
  msg.textContent = 'Gerando…';
  try {
    const res = await fetch(API + '/eap/os/gerar', {
      method: 'POST', headers: authHeaders(), body: JSON.stringify({ turmas: [...EAP.osSel], campos }),
    });
    if (res.status === 401) { logout(); return; }
    if (!res.ok) {
      let detail = null;
      try { detail = (await res.json())?.detail; } catch {}
      throw new Error(detail || `Erro ${res.status}`);
    }
    await eapBaixarBlob(res, 'OS_EAP.docx');
    msg.className = 'text-xs text-emerald-400';
    msg.textContent = 'OS gerada — confira no Word antes de assinar.';
  } catch (e) {
    msg.className = 'text-xs text-red-400';
    msg.textContent = e.message;
  } finally {
    btn.disabled = false;
  }
}

// ---------------------- MODELO DO ANO ----------------------

async function eapModeloInfo() {
  try {
    const d = await apiFetch(`/eap/modelo/info?ano=${EAP.ano}`);
    if (!d) return;
    document.getElementById('eapModeloInfo').innerHTML = d.proprio
      ? `Modelo de ${d.ano}: <span class="text-white">${eapEsc(d.nome_arquivo)}</span><div class="text-[11px] text-gray-500">enviado por ${eapEsc(d.enviado_por)} em ${eapData(d.enviado_em)}</div>`
      : `${d.ano} ainda usa o modelo padrão (OS 073/26).`;
    document.getElementById('eapModeloPadrao').classList.toggle('hidden', !d.proprio);
  } catch (e) {
    document.getElementById('eapModeloInfo').textContent = e.message;
  }
}

async function eapBaixarModelo() {
  const res = await fetch(API + `/eap/modelo?ano=${EAP.ano}`, { headers: authHeaders() });
  if (res.ok) await eapBaixarBlob(res, `modelo_os_eap_${EAP.ano}.docx`);
}

async function eapEnviarModelo(input) {
  const arq = input.files[0];
  input.value = '';
  if (!arq) return;
  const msg = document.getElementById('eapModeloMsg');
  const fd = new FormData();
  fd.append('arquivo', arq);
  try {
    const res = await fetch(API + `/eap/modelo?ano=${EAP.ano}`, {
      method: 'POST', headers: { 'Authorization': `Bearer ${TOKEN}` }, body: fd,
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(d.detail || `Erro ${res.status}`);
    msg.className = 'text-xs mt-2 text-emerald-400';
    msg.textContent = `Modelo de ${EAP.ano} salvo.`;
    eapModeloInfo();
    if (EAP.osSel.size) eapOsPreencher();
  } catch (e) {
    msg.className = 'text-xs mt-2 text-red-400';
    msg.textContent = e.message;
  }
}

async function eapModeloPadrao() {
  if (!confirm(`Apagar o modelo próprio de ${EAP.ano} e voltar ao padrão?`)) return;
  try {
    await eapApi('DELETE', `/eap/modelo?ano=${EAP.ano}`);
    document.getElementById('eapModeloMsg').textContent = '';
    eapModeloInfo();
  } catch (e) { alert(e.message); }
}
