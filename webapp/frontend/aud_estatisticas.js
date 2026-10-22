// ================= AUDITORIA COBOM — ESTATÍSTICAS =================
// Score (nota da ficha, 0 a 100) por período e por PM. Backend em
// /auditoria-cobom/estatisticas (webapp/routers/auditoria_cobom.py).
// Usa audEsc, audPosto, audDataBR, audAbrir, AUD_PARECERES e
// AUD_PARECER_COR do dashboard.html.

let AUD_SUB = 'fichas';
let AUD_EST = null;
let audEstChart = null;
const audEstAbertos = new Set();

function audSubtab(nome) {
  AUD_SUB = nome;
  const ativo = 'px-4 py-2 text-sm font-semibold rounded-t-lg border border-b-0 bg-gray-900 text-white border-gray-800 -mb-px';
  const inativo = 'px-4 py-2 text-sm font-semibold rounded-t-lg border border-b-0 bg-transparent text-gray-500 border-transparent hover:text-gray-300';
  document.getElementById('audBtn-fichas').className = nome === 'fichas' ? ativo : inativo;
  document.getElementById('audBtn-stats').className = nome === 'stats' ? ativo : inativo;
  document.getElementById('audLista').classList.toggle('hidden', nome !== 'fichas');
  document.getElementById('audStats').classList.toggle('hidden', nome !== 'stats');
  if (nome === 'stats') {
    if (!document.getElementById('audEstDe').value) audEstAtalho('ano');
    else audEstCarregar();
  }
}

function audMes(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function audEstAtalho(qual) {
  const h = new Date();
  const de = qual === 'ano' ? new Date(h.getFullYear(), 0, 1) : new Date(h.getFullYear(), h.getMonth() - 11, 1);
  document.getElementById('audEstDe').value = audMes(de);
  document.getElementById('audEstAte').value = audMes(h);
  audEstCarregar();
}

async function audEstCarregar() {
  const de = document.getElementById('audEstDe').value;
  const ate = document.getElementById('audEstAte').value;
  const agrupar = document.getElementById('audEstAgrupar').value;
  const erro = document.getElementById('audEstErro');
  erro.textContent = '';
  if (!de || !ate) return;
  try {
    const d = await apiFetch(`/auditoria-cobom/estatisticas?de=${de}&ate=${ate}&agrupar=${agrupar}`);
    if (!d) return;
    AUD_EST = d;
    audEstAbertos.clear();
    audEstRenderResumo();
    audEstRenderGrafico();
    audEstRenderPeriodos();
    audEstRenderPMs();
  } catch (e) {
    erro.textContent = e.message;
  }
}

function audEstRenderResumo() {
  const g = AUD_EST.geral;
  document.getElementById('audEstMedia').textContent = g.media ?? '—';
  document.getElementById('audEstFichas').textContent = g.fichas;
  document.getElementById('audEstPareceres').textContent = g.fichas
    ? AUD_PARECERES.filter(p => g.pareceres[p]).map(p => `${g.pareceres[p]} ${p.toLowerCase()}`).join(' · ') : '';
  document.getElementById('audEstMonit').innerHTML =
    `${g.monitorados}<span class="text-gray-500 text-base font-normal"> / ${g.efetivo}</span>`;
  document.getElementById('audEstMin').textContent = g.min ?? '—';
  const pior = AUD_EST.por_pm.filter(m => m.min === g.min && g.min != null);
  document.getElementById('audEstMinQuem').textContent =
    pior.map(m => `${audPosto(m.posto_grad)} ${m.nome}`).join(', ');
}

function audEstRenderGrafico() {
  const per = AUD_EST.periodos;
  if (audEstChart) audEstChart.destroy();
  audEstChart = new Chart(document.getElementById('audEstChart'), {
    type: 'bar',
    data: {
      labels: per.map(p => p.rotulo),
      datasets: [{
        label: 'Score médio', data: per.map(p => p.media),
        backgroundColor: '#38bdf8', borderRadius: 4, maxBarThickness: 48,
      }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: c => {
              const p = per[c.dataIndex];
              return p.fichas ? [`Score médio: ${p.media}`, `${p.fichas} ficha(s), ${p.monitorados} PM(s)`, `Mínima: ${p.min}`]
                : 'Sem ficha';
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: '#8b949e', font: { size: 11 } }, grid: { display: false } },
        y: { min: 0, max: 100, ticks: { color: '#8b949e', font: { size: 11 }, stepSize: 20 },
             grid: { color: 'rgba(139,148,158,0.12)' } },
      },
    },
  });
}

function audEstCorNota(n) {
  if (n == null) return 'text-gray-600';
  if (n >= 90) return 'text-white';
  if (n >= 70) return 'text-amber-300';
  return 'text-red-400';
}

function audEstRenderPeriodos() {
  document.getElementById('audEstPeriodos').innerHTML = AUD_EST.periodos.slice().reverse().map(p => `
    <tr class="table-row">
      <td class="px-4 py-2 text-gray-300 whitespace-nowrap">${audEsc(p.rotulo)}</td>
      <td class="px-2 py-2 text-center ${p.fichas ? 'text-gray-300' : 'text-gray-600'}">${p.fichas}</td>
      <td class="px-2 py-2 text-center text-gray-400">${p.monitorados || '—'}</td>
      <td class="px-2 py-2 text-center font-bold ${audEstCorNota(p.media)}">${p.media ?? '—'}</td>
      <td class="px-2 py-2 text-center ${audEstCorNota(p.min)}">${p.min ?? '—'}</td>
    </tr>`).join('');
}

function audEstRenderPMs() {
  const ordem = document.getElementById('audEstOrdem').value;
  const semFicha = document.getElementById('audEstSemFicha').checked;
  const nulo = (v, alto) => v == null ? (alto ? Infinity : -Infinity) : v;
  const lista = AUD_EST.por_pm.filter(m => semFicha || m.fichas).slice().sort((a, b) =>
    ordem === 'media_asc' ? nulo(a.media, true) - nulo(b.media, true) || a.nome.localeCompare(b.nome)
    : ordem === 'fichas' ? b.fichas - a.fichas || a.nome.localeCompare(b.nome)
    : ordem === 'nome' ? a.nome.localeCompare(b.nome)
    : nulo(b.media, false) - nulo(a.media, false) || a.nome.localeCompare(b.nome));

  const rotulos = AUD_EST.periodos.map(p => p.rotulo);
  document.getElementById('audEstPMs').innerHTML = lista.map(m => {
    const aberto = audEstAbertos.has(m.re);
    const larg = m.media == null ? 0 : m.media;
    const par = AUD_PARECERES.filter(p => p !== 'APROVADO' && m.pareceres[p])
      .map(p => `<span class="whitespace-nowrap text-[10px] px-1.5 py-0.5 rounded border ${AUD_PARECER_COR[p] || ''}">${m.pareceres[p]} ${audEsc(p.toLowerCase())}</span>`).join(' ');
    const linha = `
      <tr class="table-row cursor-pointer ${m.fichas ? '' : 'opacity-60'}" onclick="audEstToggle(${m.re})">
        <td class="px-4 py-2 text-white min-w-[15rem]">${audEsc(audPosto(m.posto_grad))} ${audEsc(m.nome)}
          <div class="text-gray-500 text-xs">RE ${m.re}${m.no_cobom ? '' : ' · fora do COBOM hoje'}</div></td>
        <td class="px-2 py-2 text-gray-400">${audEsc(m.equipe || '—')}</td>
        <td class="px-2 py-2 text-center ${m.fichas ? 'text-gray-300' : 'text-gray-600'}">${m.fichas}</td>
        <td class="px-2 py-2">${m.fichas ? `<div class="flex items-center gap-2">
            <span class="font-bold w-10 ${audEstCorNota(m.media)}">${m.media}</span>
            <div class="progress-bar h-1.5 flex-1 min-w-[5rem]"><div class="progress-fill" style="width:${larg}%;background:#38bdf8"></div></div></div>`
          : '<span class="text-gray-600 text-xs">sem ficha</span>'}</td>
        <td class="px-2 py-2 text-center ${audEstCorNota(m.min)}">${m.min ?? '—'}</td>
        <td class="px-2 py-2 text-center ${m.inconformidades ? 'text-amber-300 font-semibold' : 'text-gray-600'}">${m.inconformidades}</td>
        <td class="px-2 py-2">${par || (m.fichas ? '<span class="text-gray-600 text-xs">só aprovado</span>' : '')}</td>
        <td class="px-4 py-2 text-gray-400 whitespace-nowrap">${m.ultima
          ? `<button onclick="event.stopPropagation(); audAbrir(${m.ultima.id})" class="hover:text-white">${audDataBR(m.ultima.data)} · <span class="${audEstCorNota(m.ultima.nota)}">${m.ultima.nota}</span></button>` : '—'}</td>
      </tr>`;
    if (!aberto) return linha;
    return linha + `<tr><td colspan="8" class="px-4 py-3 bg-gray-900/40">
      <div class="text-[11px] uppercase tracking-wider text-gray-500 mb-2">Score médio por período</div>
      <div class="flex flex-wrap gap-1.5">${m.serie.map((v, i) => `
        <div class="rounded border border-gray-800 px-2 py-1 text-center min-w-[3.5rem]">
          <div class="text-[10px] text-gray-500">${audEsc(rotulos[i])}</div>
          <div class="text-sm font-semibold ${audEstCorNota(v)}">${v ?? '—'}</div></div>`).join('')}</div>
    </td></tr>`;
  }).join('') || '<tr><td colspan="8" class="px-4 py-6 text-center text-gray-600">Nenhuma ficha no intervalo</td></tr>';
}

function audEstToggle(re) {
  if (audEstAbertos.has(re)) audEstAbertos.delete(re); else audEstAbertos.add(re);
  audEstRenderPMs();
}
