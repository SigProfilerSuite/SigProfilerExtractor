/* SigProfilerExtractor Workbench. No framework and no build step: this ships
   inside a Python package. User-supplied strings only ever reach the page
   through textContent. */

'use strict';

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
};

const state = {
  env: null, settings: null, jobs: [], jobId: null, job: null, logOffset: 0, logTail: '',
  view: 'home', kind: 'vcf', input: null, inputPath: '', inputError: null, outputAuto: true,
  outCheck: null, replaceOutput: false, preset: 'quick', genomes: null,
  results: null, resultsPath: null, deleting: null, seedsProblem: null, dashJob: null,
};

/* ------------------------------------------------------------- helpers */

async function api(path, opts) {
  const r = await fetch(path, opts);
  let body;
  try { body = await r.json(); } catch (e) { throw new Error(`${r.status} ${r.statusText}`); }
  if (!r.ok || body.ok === false) throw new Error(body.error || `${r.status} ${r.statusText}`);
  return body;
}
const get = (path) => api(path);
// Every action must carry this launch's token, which only this page has.
const TOKEN = document.querySelector('meta[name="workbench-token"]').content;
const post = (path, payload) => api(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Dashboard-Token': TOKEN },
  body: JSON.stringify(payload || {}),
});
const q = (params) => new URLSearchParams(params).toString();

const num = (v) => (v === null || v === undefined || Number.isNaN(v)) ? '–' : Number(v).toLocaleString();

function bytes(n) {
  if (n === null || n === undefined) return '–';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}

function clock(sec) {
  if (sec === null || sec === undefined || Number.isNaN(sec)) return '';
  const s = Math.max(0, Math.round(sec));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : (m ? `${m}m ${s % 60}s` : `${s}s`);
}

const shortPath = (p, max) => { const s = String(p || ''); return s.length <= max ? s : '…' + s.slice(-(max - 1)); };
const baseName = (p) => String(p || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop();
const stem = (p) => baseName(p).replace(/\.[A-Za-z0-9]+$/, '');
const slug = (s) => String(s).replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '') || 'run';
const joinPath = (dir, name) => String(dir).replace(/[\\/]+$/, '') + '/' + name;

function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

/* Text with inline emphasis, built without innerHTML: parts are plain strings,
   or {b: text} for bold, or {mono: text} for a path. */
function rich(node, parts) {
  parts.forEach((p) => {
    if (p === null || p === undefined || p === false) return;
    if (typeof p === 'string') node.appendChild(document.createTextNode(p));
    else if (p.b !== undefined) node.appendChild(el('b', null, p.b));
    else if (p.mono !== undefined) node.appendChild(el('span', 'mono', p.mono));
    else if (p.node) node.appendChild(p.node);
  });
  return node;
}
const noteBox = (kind, parts) => rich(el('div', `note-box ${kind || ''}`), parts);
function pill(kind, text) { return el('span', `pill ${kind}`, text); }
const plural = (n, word, many) => `${num(n)} ${n === 1 ? word : (many || `${word}s`)}`;

let toastTimer = null;
function toast(text, action) {
  $('toastText').textContent = text;
  const btn = $('toastAction');
  btn.classList.toggle('hidden', !action);
  btn.onclick = null;
  if (action) {
    btn.textContent = action.label;
    btn.onclick = () => { $('toast').classList.add('hidden'); action.fn(); };
  }
  $('toast').classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').classList.add('hidden'), action ? 9000 : 3500);
}

function listing(items) {
  return items.length < 3 ? items.join(' and ') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}
function whenAt(sec) {
  return new Date(sec * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// The server owns each picker's kind and title; the page only names which one.
async function pickPath(purpose) { return (await post('/api/dialog', { purpose })).path; }

function svgEl(tag, attrs) {
  const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs || {}).forEach(([k, v]) => n.setAttribute(k, v));
  return n;
}

/* --------------------------------------------------------------- theme */

const THEMES = ['sandiego', 'ualbany', 'sigprofilersuite', 'night'];
function currentTheme() {
  const set = document.documentElement.getAttribute('data-theme');
  if (THEMES.includes(set)) return set;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'night' : 'sandiego';
}
function applyTheme(name) {
  if (!THEMES.includes(name)) return;
  document.documentElement.setAttribute('data-theme', name);
  try { localStorage.setItem('spe-theme', name); } catch (e) { /* private mode */ }
  $('themeSel').value = currentTheme();
}
(function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem('spe-theme'); } catch (e) { saved = null; }
  if (THEMES.includes(saved)) document.documentElement.setAttribute('data-theme', saved);
  $('themeSel').value = currentTheme();
  $('themeSel').addEventListener('change', (e) => applyTheme(e.target.value));
})();

/* ------------------------------------------------- side panel: resize, hide */

// Drag the handle to set the side panel's width, or past its narrowest to hide
// it; double-click, the arrow keys or the top-bar button also work. The width
// and whether it is hidden are remembered by the browser.
const SIDE = { min: 200, max: 560, standard: 280, hideBelow: 130, step: 20 };
const side = { width: SIDE.standard, hidden: false };

function applySide(save) {
  side.width = Math.round(Math.min(SIDE.max, Math.max(SIDE.min, side.width)));
  document.documentElement.style.setProperty('--side-w', `${side.width}px`);
  $('app').classList.toggle('side-hidden', side.hidden);
  const toggle = $('sideToggle');
  const label = side.hidden ? 'Show the side panel' : 'Hide the side panel';
  toggle.setAttribute('aria-expanded', String(!side.hidden));
  toggle.title = label;
  toggle.setAttribute('aria-label', label);
  const handle = $('sideSplitter');
  handle.setAttribute('aria-valuenow', String(side.hidden ? 0 : side.width));
  handle.setAttribute('aria-valuetext', side.hidden ? 'hidden' : `${side.width} pixels`);
  if (save) {
    try { localStorage.setItem('spe-side', JSON.stringify(side)); } catch (e) { /* private mode */ }
  }
}

(function initSide() {
  try {
    const saved = JSON.parse(localStorage.getItem('spe-side') || 'null');
    if (saved && Number.isFinite(saved.width)) { side.width = saved.width; side.hidden = !!saved.hidden; }
  } catch (e) { /* nothing saved */ }
  applySide(false);
  const handle = $('sideSplitter');
  $('sideToggle').addEventListener('click', () => { side.hidden = !side.hidden; applySide(true); });
  handle.addEventListener('dblclick', () => { side.hidden = !side.hidden; applySide(true); });
  handle.addEventListener('keydown', (e) => {
    const moves = { ArrowLeft: -SIDE.step, ArrowRight: SIDE.step };
    if (e.key in moves) {
      e.preventDefault();
      if (side.hidden && e.key === 'ArrowRight') { side.hidden = false; side.width = SIDE.min; }
      else if (!side.hidden && e.key === 'ArrowLeft' && side.width <= SIDE.min) side.hidden = true;
      else side.width += moves[e.key];
    } else if (e.key === 'Home') { e.preventDefault(); side.hidden = true; }
    else if (e.key === 'End') { e.preventDefault(); side.hidden = false; side.width = SIDE.max; }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); side.hidden = !side.hidden; }
    else return;
    applySide(true);
  });
  handle.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    document.body.classList.add('resizing');
    const left = document.querySelector('.body').getBoundingClientRect().left;
    const move = (ev) => {
      const width = ev.clientX - left;
      side.hidden = width < SIDE.hideBelow;
      if (!side.hidden) side.width = width;
      applySide(false);
    };
    const up = (ev) => {
      handle.releasePointerCapture(ev.pointerId);
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', up);
      handle.removeEventListener('pointercancel', up);
      document.body.classList.remove('resizing');
      applySide(true);
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', up);
    handle.addEventListener('pointercancel', up);
  });
})();

/* ----------------------------------------------------------- tab router */

const VIEWS = ['home', 'run', 'monitor', 'results', 'help'];
function show(view) {
  state.view = view;
  if (view === 'run' && state.input) checkOutput();
  if (view === 'home') renderRecent();
  VIEWS.forEach((v) => {
    $(`view-${v}`).classList.toggle('hidden', v !== view);
    $(`tab-${v}`).setAttribute('aria-selected', String(v === view));
  });
  $('contextLabel').textContent = view === 'results' && state.resultsPath ? shortPath(state.resultsPath, 64) : '';
  window.scrollTo(0, 0);
  const main = document.querySelector('.main');
  if (main) main.scrollTop = 0;
}
VIEWS.forEach((v) => $(`tab-${v}`).addEventListener('click', () => show(v)));
$('homeBtn').addEventListener('click', () => show('home'));
$('newRunBtn').addEventListener('click', () => show('run'));

/* -------------------------------------------------------------- about ? */

document.querySelectorAll('.about-btn').forEach((button) => {
  button.addEventListener('click', () => {
    const panel = $(button.dataset.about);
    const open = panel.classList.contains('hidden');
    panel.classList.toggle('hidden', !open);
    button.setAttribute('aria-expanded', String(open));
  });
});
function fillAbout(panel, entries) {
  clear(panel);
  const dl = el('dl', 'defs');
  entries.forEach(([term, text]) => { dl.appendChild(el('dt', null, term)); dl.appendChild(el('dd', null, text)); });
  panel.appendChild(dl);
}
fillAbout($('about-ranks'), [
  ['Number of signatures', 'Also called the rank. SigProfilerExtractor tries every number from the fewest to the most, then suggests the best: the largest number whose signatures are stable and still reconstruct the samples well.'],
  ['NMF replicates', 'How many times the factorization runs for each number, each on a resampled copy of the data. More replicates make the stability estimate, and so the choice, more reliable.'],
  ['Quick look', 'Numbers 1 to 5 with 10 replicates: minutes instead of hours, to see whether a cohort has structure worth a full run. Not for reporting.'],
  ['Standard', 'SigProfilerExtractor\'s published setting: 1 to 25 with 100 replicates. Use it for results you will report.'],
]);

/* ---------------------------------------------------------- hero picture */

// A sample's profile as the sum of three signatures: what extraction undoes.
const SBS_COLORS = ['#03BCEE', '#010101', '#E32926', '#CAC9C9', '#A1CE63', '#EBC6C4'];
function heroArt() {
  const W = 300, H = 230;
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, class: 'art-svg', role: 'img' });
  const sigs = [
    (i) => (i >= 32 && i < 48 ? 0.9 * Math.exp(-((i - 38) ** 2) / 8) : 0.03),          // C>T at CpG, ageing-like
    (i) => (i < 16 ? 0.5 + 0.4 * ((i * 7) % 5) / 5 : 0.05) + (i >= 16 && i < 32 ? 0.35 : 0),  // C>A/C>G
    (i) => 0.12 + 0.1 * Math.abs(Math.sin(i * 1.7)),                                    // flat
  ];
  const weights = [0.5, 0.3, 0.2];
  const bar = (x0, y0, w, h, values, scale) => {
    const g = svgEl('g');
    const bw = w / 96;
    values.forEach((v, i) => {
      const bh = Math.max(0.6, (v / scale) * h);
      g.appendChild(svgEl('rect', { x: (x0 + i * bw).toFixed(2), y: (y0 + h - bh).toFixed(2), width: (bw * 0.78).toFixed(2), height: bh.toFixed(2), fill: SBS_COLORS[Math.floor(i / 16)] }));
    });
    return g;
  };
  const profile = Array.from({ length: 96 }, (_, i) => sigs.reduce((s, f, k) => s + weights[k] * f(i), 0));
  const plate = svgEl('rect', { x: 0, y: 0, width: W, height: H, rx: 12, fill: '#ffffff', stroke: 'rgba(0,0,0,.08)' });
  svg.appendChild(plate);
  svg.appendChild(bar(14, 14, 272, 70, profile, Math.max(...profile)));
  const label = (x, y, text, size, weight) => {
    const t = svgEl('text', { x, y, 'font-size': size || 9, 'font-weight': weight || 500, fill: '#556', 'font-family': 'system-ui, sans-serif' });
    t.textContent = text; return t;
  };
  svg.appendChild(label(14, 100, 'a sample', 9.5, 600));
  svg.appendChild(label(150, 100, '=', 13, 600));
  [0, 1, 2].forEach((k) => {
    const x = 14 + k * 93;
    const vals = Array.from({ length: 96 }, (_, i) => sigs[k](i));
    svg.appendChild(bar(x, 110, 84, 70, vals, Math.max(...vals)));
    svg.appendChild(label(x, 196, `${Math.round(weights[k] * 100)}% × signature ${String.fromCharCode(65 + k)}`, 8.5));
    if (k < 2) svg.appendChild(label(x + 86, 150, '+', 11, 600));
  });
  svg.appendChild(label(14, 218, 'extraction finds the signatures and their shares', 8.5));
  return svg;
}
$('heroArt').appendChild(heroArt());

/* ------------------------------------------------------------------ env */

async function loadEnv() {
  const env = await get('/api/env');
  state.env = env;
  state.settings = env.settings;
  // "0+unknown" is setuptools_scm's fallback when it cannot find the version.
  const v = String(env.version || '').split('+')[0];
  $('envVersion').textContent = v && v !== '0' ? `v${v}` : '';
  fillChoices();
  applyGenomes(env.genomes);
  resetAdvanced();
  setPreset('quick');
  setKind('vcf');
  const pillNode = $('envPill');
  pillNode.className = 'pill good';
  pillNode.textContent = env.cuda ? 'ready · GPU' : 'ready';
  return env;
}

function option(value, text) { const o = el('option', null, text); o.value = value; return o; }

function fillChoices() {
  const s = state.settings;
  const ex = $('exampleSel');
  (state.env.examples || []).forEach((e) => ex.appendChild(option(e.id, `${e.label} (${e.detail})`)));
  s.seg_callers.forEach((c) => $('segCaller').appendChild(option(c, c)));
  s.cosmic_genomes.forEach((g) => $('opportunitySel').appendChild(option(g, g)));
  s.cosmic_versions.forEach((v) => $('cosmicVersion').appendChild(option(String(v), String(v))));
  s.nmf_inits.forEach((v) => $('nmfInit').appendChild(option(v, v)));
  s.precisions.forEach((v) => $('precision').appendChild(option(v, v)));
  s.clustering_distances.forEach((v) => $('clustering').appendChild(option(v, v)));
  s.normalizations.forEach((v) => $('normList').appendChild(option(v, v)));
  const chips = $('contextChips');
  s.vcf_contexts.forEach((c) => {
    const lab = el('label', 'chip check-chip');
    const box = el('input');
    box.type = 'checkbox';
    box.value = c;
    box.checked = s.default_vcf_contexts.includes(c);
    box.addEventListener('change', () => { updateContextNotes(); refresh(); });
    lab.appendChild(box);
    lab.appendChild(el('span', null, c));
    chips.appendChild(lab);
  });
  const presets = $('presetGroup');
  Object.entries(s.presets).forEach(([id, p]) => {
    const lab = el('label', 'preset');
    const radio = el('input');
    radio.type = 'radio';
    radio.name = 'preset';
    radio.value = id;
    radio.addEventListener('change', () => setPreset(id));
    lab.appendChild(radio);
    const text = el('span');
    text.appendChild(el('b', null, p.label));
    text.appendChild(el('small', null, p.description));
    lab.appendChild(text);
    presets.appendChild(lab);
  });
  const custom = el('label', 'preset');
  const radio = el('input');
  radio.type = 'radio'; radio.name = 'preset'; radio.value = 'custom'; radio.disabled = true;
  custom.appendChild(radio);
  const ct = el('span');
  ct.appendChild(el('b', null, 'Custom'));
  ct.appendChild(el('small', null, 'Your own numbers: edit the fields below.'));
  custom.appendChild(ct);
  presets.appendChild(custom);
  $('cpuHint').textContent = `Blank uses all ${state.env.cpus} of them.`;
  if (!state.env.cuda) {
    $('gpu').disabled = true;
    $('gpuText').textContent = 'Use the GPU (no CUDA GPU on this computer)';
  }
}

/* ------------------------------------------------------------- genomes */

function applyGenomes(g) {
  state.genomes = g;
  const sel = $('genomeSel');
  const keep = sel.value;
  clear(sel);
  const installed = g.installed || [];
  [['Installed', installed], ['Not installed', (g.available || []).filter((x) => !installed.includes(x))]]
    .forEach(([label, names]) => {
      if (!names.length) return;
      const og = el('optgroup');
      og.label = label;
      names.forEach((n) => og.appendChild(option(n, installed.includes(n) ? n : `${n}  (not installed)`)));
      sel.appendChild(og);
    });
  sel.value = (g.available || []).includes(keep) ? keep : (installed[0] || 'GRCh37');
  updateGenomeStatus();
}
const genomeInstalled = (name) => !!state.genomes && (state.genomes.installed || []).includes(name);

function updateGenomeStatus() {
  const name = $('genomeSel').value;
  const box = $('genomeStatus');
  clear(box);
  if (!name) return;
  if (genomeInstalled(name)) box.appendChild(pill('good', 'installed'));
  else {
    box.appendChild(pill('warn', 'not installed'));
    const btn = el('button', 'btn sm', `Install ${name}`);
    btn.type = 'button';
    btn.addEventListener('click', () => installGenome(name, btn));
    box.appendChild(btn);
  }
  updateContextNotes();
  refresh();
}
$('genomeSel').addEventListener('change', updateGenomeStatus);

async function installGenome(name, btn) {
  if (btn) btn.disabled = true;
  try {
    const { job } = await post('/api/genomes/install', { genome: name, volume: $('volumePath').value.trim() || null });
    toast(`Installing ${name}. It downloads once (about 3 GB for a human genome).`);
    await refreshJobs();
    selectJob(job.id);
    show('monitor');
  } catch (e) { toast(e.message); } finally { if (btn) btn.disabled = false; }
}

/* ------------------------------------------------------------ the input */

const KIND_TEXT = {
  vcf: ['Choose the folder of variant calls', 'input_vcf'],
  matrix: ['Choose the mutation matrix', 'input_matrix'],
  bedpe: ['Choose the folder of BEDPE files', 'input_bedpe'],
  seg: ['Choose the segmentation file', 'input_seg'],
};

function setKind(kind, keepInput) {
  state.kind = kind;
  document.querySelectorAll('input[name="kind"]').forEach((r) => { r.checked = r.value === kind; });
  $('inputChooseText').textContent = KIND_TEXT[kind][0];
  $('callerField').classList.toggle('hidden', kind !== 'seg');
  const vcf = kind === 'vcf';
  $('vcfGenome').classList.toggle('hidden', !vcf);
  $('otherGenome').classList.toggle('hidden', vcf);
  $('genomeTitle').textContent = vcf ? 'Genome and contexts' : 'COSMIC reference';
  $('genomeNote').textContent = vcf ? 'the assembly the calls were made against, and what to extract'
    : 'which genome build the COSMIC signatures are matched for';
  if (!keepInput) {
    state.input = null;
    state.inputPath = '';
    state.inputError = null;
    $('inputPath').value = '';
    clear($('inputInfo'));
  }
  updateContextNotes();
  refresh();
}
document.querySelectorAll('input[name="kind"]').forEach((r) => r.addEventListener('change', () => setKind(r.value)));

let inputSeq = 0;
async function setInput(path) {
  path = String(path || '').trim();
  const seq = ++inputSeq;
  state.inputPath = path;
  state.input = null;
  state.inputError = null;
  const info = $('inputInfo');
  clear(info);
  if (!path) { refresh(); return; }
  const loading = el('div', 'inline muted after-grid');
  loading.appendChild(el('span', 'spin'));
  loading.appendChild(el('span', null, 'Reading the input…'));
  info.appendChild(loading);
  try {
    const r = await get(`/api/inspect?${q({ type: state.kind, path })}`);
    if (seq !== inputSeq) return;
    state.input = r;
    $('inputPath').value = r.path || path;
    renderInputInfo(r);
    if (state.outputAuto || !$('outputPath').value.trim()) {
      $('outputPath').value = joinPath(state.env.results_root, slug(stem(r.path || path)));
      state.outputAuto = true;
    }
    if (state.kind !== 'vcf') suggestOpportunity(r.format);
  } catch (e) {
    if (seq !== inputSeq) return;
    state.inputError = e.message;
    clear(info);
    const box = noteBox('crit', [e.message]);
    box.classList.add('after-grid');
    info.appendChild(box);
  }
  updateContextNotes();
  updateOutput();
  refresh();
}

function tileNode(k, v, d) {
  const t = el('div', 'tile');
  t.appendChild(el('div', 'k', k));
  t.appendChild(el('div', 'v', v));
  const dn = el('div', 'd', d || ' ');
  dn.title = d || '';
  t.appendChild(dn);
  return t;
}

function renderInputInfo(r) {
  const info = $('inputInfo');
  clear(info);
  const tiles = el('div', 'tiles in-card after-grid');
  const preview = (r.samples_preview || []).join(', ') + ((r.sample_count || 0) > (r.samples_preview || []).length ? ', …' : '');
  if (state.kind === 'vcf') {
    tiles.appendChild(tileNode('Format', r.format, r.format === 'Txt' ? 'simple text' : 'one file per sample'));
    tiles.appendChild(tileNode('Samples', num(r.sample_count), preview));
    tiles.appendChild(tileNode('Mutations', num(r.records), `${num(r.indels)} indel${r.indels === 1 ? '' : 's'}`));
    tiles.appendChild(tileNode('Files', num(r.file_count), r.source !== r.path ? 'in input/' : ''));
  } else if (state.kind === 'matrix') {
    tiles.appendChild(tileNode('Context', r.format, `${num(r.rows)} mutation types`));
    tiles.appendChild(tileNode('Samples', num(r.sample_count), preview));
    tiles.appendChild(tileNode('Mutations', num(r.records), 'in all samples'));
    tiles.appendChild(tileNode('Dropped', num(r.dropped_count), r.dropped_count ? 'empty or all zero' : 'none'));
  } else if (state.kind === 'bedpe') {
    tiles.appendChild(tileNode('Context', 'SV32', '32 structural-variant classes'));
    tiles.appendChild(tileNode('Samples', num(r.sample_count), preview));
    tiles.appendChild(tileNode('Variants', num(r.records), 'rows read'));
    tiles.appendChild(tileNode('Files', num(r.file_count), ''));
  } else {
    tiles.appendChild(tileNode('Context', 'CNV48', '48 copy-number classes'));
    tiles.appendChild(tileNode('Samples', r.sample_count ? num(r.sample_count) : '–', preview));
    tiles.appendChild(tileNode('Segments', num(r.records), 'rows read'));
  }
  info.appendChild(tiles);
  const notes = [];
  if (state.kind === 'vcf' && r.other_count) {
    notes.push(noteBox('warn', [`${plural(r.other_count, 'other file')} in this folder (`, { mono: r.other_files.join(', ') },
      '). SigProfilerMatrixGenerator reads every file, so move them out if they are not variant calls.']));
  }
  if (state.kind === 'vcf' && r.writable === false) {
    notes.push(noteBox('crit', [{ b: 'This folder is not writable. ' },
      'SigProfilerMatrixGenerator writes its matrices into the folder of calls, so copy them somewhere writable first.']));
  }
  if (state.kind === 'vcf' && r.writable !== false) {
    notes.push(noteBox('', ['SigProfilerMatrixGenerator will write ', { mono: 'input/' }, ' and ', { mono: 'output/' },
      ' folders into this folder while it builds the matrices.']));
  }
  if (state.kind === 'matrix' && !r.known_context) {
    notes.push(noteBox('warn', [`${num(r.rows)} rows is not a standard context, so it runs as `, { b: r.format },
      ' with no COSMIC catalogue to match against.']));
  }
  if (state.kind === 'matrix' && r.dropped_count) {
    const names = [...(r.empty_samples || []), ...(r.zero_samples || [])];
    notes.push(noteBox('warn', [`${plural(r.dropped_count, 'sample')} will be dropped because ${r.dropped_count === 1 ? 'it is' : 'they are'} empty or all zero: `,
      { mono: names.join(', ') }, r.dropped_count > names.length ? ', …' : '', '.']));
  }
  if (state.kind === 'bedpe' && r.writable === false) {
    notes.push(noteBox('crit', ['The SV matrix is written to ', { mono: r.writes_beside }, ', and that folder is not writable.']));
  }
  notes.forEach((n) => { n.classList.add('after-grid'); info.appendChild(n); });
}

$('inputChoose').addEventListener('click', async () => {
  const btn = $('inputChoose');
  btn.disabled = true;
  try { const path = await pickPath(KIND_TEXT[state.kind][1]); if (path) await setInput(path); }
  catch (e) { toast(e.message); } finally { btn.disabled = false; }
});
$('inputPath').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.value.trim()) setInput(e.target.value); });
$('inputPath').addEventListener('change', (e) => { if (e.target.value.trim() && e.target.value.trim() !== state.inputPath) setInput(e.target.value); });
$('segCaller').addEventListener('change', refresh);

function suggestOpportunity(context) {
  const sel = $('opportunitySel');
  const hint = $('opportunityHint');
  if (context === 'SV32') { sel.value = 'GRCh38'; hint.textContent = 'SV32 COSMIC signatures are defined on GRCh38, so it is set for you.'; }
  else if (context === 'CNV48') { sel.value = 'GRCh37'; hint.textContent = 'CNV48 COSMIC signatures are defined on GRCh37, so it is set for you.'; }
  else hint.textContent = 'The build the COSMIC reference signatures are matched for. Default GRCh37.';
}

/* ------------------------------------------------------------- contexts */

const chosenContexts = () => [...document.querySelectorAll('#contextChips input:checked')].map((b) => b.value);
function runContexts() {
  if (state.kind === 'vcf') return chosenContexts();
  return state.input && state.input.contexts ? state.input.contexts : [];
}

function updateContextNotes() {
  const box = $('genomeCard').querySelector('.bd');
  box.querySelectorAll('.ctx-note').forEach((n) => n.remove());
  const add = (kind, parts) => { const n = noteBox(kind, parts); n.classList.add('after-grid', 'ctx-note'); box.appendChild(n); };
  if (state.kind !== 'vcf') return;
  const r = state.input;
  if (r && r.assembly && r.assembly !== $('genomeSel').value) {
    add('warn', ['These calls say they were made against ', { b: r.assembly }, ', but ', { b: $('genomeSel').value },
      ' is chosen. Most mutations would not match the reference and SigProfilerMatrixGenerator would stop.']);
  }
  if (r && r.indels === 0 && chosenContexts().includes('ID83')) {
    add('', ['These calls hold no insertions or deletions, so ', { b: 'ID83' }, ' will be skipped.']);
  }
  if (!chosenContexts().length) add('crit', ['Choose at least one mutation context.']);
}

/* ---------------------------------------------------- number of signatures */

function setPreset(id) {
  const p = state.settings.presets[id];
  state.preset = id;
  document.querySelectorAll('input[name="preset"]').forEach((r) => { r.checked = r.value === id; });
  if (p) {
    $('minSig').value = p.values.minimum_signatures;
    $('maxSig').value = p.values.maximum_signatures;
    $('replicates').value = p.values.nmf_replicates;
  }
  refresh();
}
['minSig', 'maxSig', 'replicates'].forEach((id) => $(id).addEventListener('input', () => {
  const vals = { minimum_signatures: +$('minSig').value, maximum_signatures: +$('maxSig').value, nmf_replicates: +$('replicates').value };
  const match = Object.entries(state.settings.presets).find(([, p]) =>
    Object.entries(p.values).every(([k, v]) => vals[k] === v));
  state.preset = match ? match[0] : 'custom';
  document.querySelectorAll('input[name="preset"]').forEach((r) => { r.checked = r.value === state.preset; });
  refresh();
}));

function effort() {
  const low = parseInt($('minSig').value, 10), high = parseInt($('maxSig').value, 10);
  const reps = parseInt($('replicates').value, 10);
  const samples = state.input && state.input.sample_count;
  let lo = low, hi = high;
  if (samples) { lo = Math.min(lo, samples); hi = Math.min(hi, samples); }
  const ranks = Math.max(0, hi - lo + 1);
  const contexts = runContexts().length || (state.kind === 'vcf' ? 0 : 1);
  return { low, high, reps, samples, lo, hi, ranks, contexts, fits: ranks * reps * contexts };
}

function renderEstimate() {
  const box = $('estimate');
  clear(box);
  const e = effort();
  if (!(e.low >= 1 && e.high >= 1 && e.reps >= 1)) { box.className = 'note-box after-grid estimate crit'; box.textContent = 'Enter whole numbers of at least 1.'; return; }
  if (e.low > e.high) { box.className = 'note-box after-grid estimate crit'; box.textContent = 'The fewest signatures cannot be more than the most.'; return; }
  box.className = 'note-box after-grid estimate';
  const head = el('div', 'est-head');
  head.appendChild(el('span', 'est-fits', num(e.fits)));
  head.appendChild(el('span', 'est-unit', e.fits === 1 ? 'NMF fit' : 'NMF fits'));
  box.appendChild(head);
  const ctx = e.contexts ? plural(e.contexts, 'context') : 'each context';
  rich(box, [`${ctx} × ${plural(e.ranks, 'number')} of signatures (${e.lo} to ${e.hi}) × ${plural(e.reps, 'replicate')}.`]);
  if (e.samples && e.high > e.samples) {
    rich(box, [' ', { b: `Capped at ${e.samples}` }, ', the number of samples.']);
  }
  const speed = el('p', 'est-speed');
  speed.textContent = state.preset === 'standard'
    ? 'The published setting. Expect hours for a typical cohort; the Monitor tab estimates the time left as it runs.'
    : (state.preset === 'quick' ? 'About three minutes for the 21-genome example on a laptop; time grows with samples, channels and signatures.'
      : 'Time grows with the number of fits, samples and channels.');
  box.appendChild(speed);
}

/* ---------------------------------------------------- COSMIC assignment */

$('assign').addEventListener('change', () => {
  $('assignOpts').classList.toggle('disabled', !$('assign').checked);
  $('assignOpts').querySelectorAll('input, select').forEach((n) => { n.disabled = !$('assign').checked; });
  refresh();
});

/* ---------------------------------------------------------------- output */

$('outputPath').addEventListener('input', () => { state.outputAuto = false; updateOutput(); });
$('outputBrowse').addEventListener('click', async () => {
  try { const p = await pickPath('output'); if (p) { $('outputPath').value = p; state.outputAuto = false; updateOutput(); } }
  catch (e) { toast(e.message); }
});

let outTimer = null;
let outSeq = 0;
function updateOutput() { clearTimeout(outTimer); outTimer = setTimeout(checkOutput, 250); refresh(); }

async function checkOutput() {
  const out = $('outputPath').value.trim();
  const seq = ++outSeq;
  if (!out) { state.outCheck = null; renderOutCheck(); return; }
  let r = null;
  try { r = await get(`/api/output?${q({ path: out, input: state.inputPath || '' })}`); } catch (e) { r = null; }
  if (seq !== outSeq) return;
  if (!r || !state.outCheck || state.outCheck.path !== r.path) state.replaceOutput = false;
  state.outCheck = r;
  renderOutCheck();
  refresh();
}

function renderOutCheck() {
  const box = $('outCheck');
  clear(box);
  const r = state.outCheck;
  if (!r || !r.found) return;
  const what = r.contexts.length ? ` (${listing(r.contexts)})` : '';
  if (state.replaceOutput) {
    const note = el('div', 'note-box warn row after-grid');
    note.appendChild(rich(el('span'), [{ b: 'The earlier results here are deleted when the run starts' }, what,
      '. Only what SigProfilerExtractor wrote goes; other files in the folder stay. This cannot be undone.']));
    const keep = el('button', 'btn sm', 'Keep them');
    keep.type = 'button';
    keep.addEventListener('click', () => { state.replaceOutput = false; renderOutCheck(); refresh(); });
    note.appendChild(keep);
    box.appendChild(note);
    return;
  }
  const note = el('div', 'note-box warn after-grid');
  note.appendChild(rich(el('p'), [{ b: 'This folder already holds results from an earlier run' }, what,
    '. SigProfilerExtractor would move them aside and the dashboard would show both.']));
  const acts = el('div', 'actions');
  if (r.suggested) {
    const fresh = el('button', 'btn sm primary', `Use a new folder: ${baseName(r.suggested)}`);
    fresh.type = 'button';
    fresh.dataset.choice = 'new';
    fresh.addEventListener('click', () => { $('outputPath').value = r.suggested; state.outputAuto = false; updateOutput(); });
    acts.appendChild(fresh);
  }
  const replace = el('button', 'btn sm danger', 'Replace the earlier results');
  replace.type = 'button';
  replace.dataset.choice = 'replace';
  replace.disabled = !!r.replace_problem;
  replace.addEventListener('click', () => { state.replaceOutput = true; renderOutCheck(); refresh(); });
  acts.appendChild(replace);
  note.appendChild(acts);
  if (r.replace_problem) note.appendChild(rich(el('p'), [r.replace_problem]));
  box.appendChild(note);
}

/* --------------------------------------------------------------- advanced */

const ADVANCED = [
  // [element id, settings key, kind]
  ['normalization', 'matrix_normalization', 'text'],
  ['nmfInit', 'nmf_init', 'text'],
  ['precision', 'precision', 'text'],
  ['minIter', 'min_nmf_iterations', 'number'],
  ['maxIter', 'max_nmf_iterations', 'number'],
  ['testConv', 'nmf_test_conv', 'number'],
  ['tolerance', 'nmf_tolerance', 'text'],
  ['clustering', 'clustering_distance', 'text'],
  ['resample', 'resample', 'bool'],
  ['stability', 'stability', 'number'],
  ['minStability', 'min_stability', 'number'],
  ['combinedStability', 'combined_stability', 'number'],
  ['stabilityDrop', 'allow_stability_drop', 'bool'],
  ['addPenalty', 'nnls_add_penalty', 'number'],
  ['removePenalty', 'nnls_remove_penalty', 'number'],
  ['initialPenalty', 'initial_remove_penalty', 'number'],
  ['batchSize', 'batch_size', 'number'],
  ['dashboard', 'make_dashboard', 'bool'],
  ['allMatrices', 'get_all_signature_matrices', 'bool'],
];
const fmtDefault = (v) => (typeof v === 'number' && v !== 0 && Math.abs(v) < 1e-4 ? v.toExponential().replace('e-', 'e-') : String(v));

function resetAdvanced() {
  const d = state.settings.defaults;
  $('cosmicVersion').value = String(d.cosmic_version);
  ADVANCED.forEach(([id, key, kind]) => {
    if (kind === 'bool') $(id).checked = !!d[key];
    else $(id).value = fmtDefault(d[key]);
  });
  $('cpu').value = '';
  $('assignCpu').value = '';
  $('gpu').checked = false;
  $('seedsPath').value = '';
  state.seedsProblem = null;
  clear($('seedsNote'));
  $('batchField').classList.add('hidden');
  refresh();
}
$('resetAdvanced').addEventListener('click', resetAdvanced);

function advancedChanged() {
  const d = state.settings.defaults;
  let n = 0;
  ADVANCED.forEach(([id, key, kind]) => {
    if (kind === 'bool') { if ($(id).checked !== !!d[key]) n++; }
    else if (kind === 'number') { if (Number($(id).value) !== Number(d[key])) n++; }
    else if (String($(id).value).trim() !== fmtDefault(d[key])) n++;
  });
  if ($('cpu').value.trim()) n++;
  if ($('assignCpu').value.trim()) n++;
  if ($('gpu').checked) n++;
  if ($('seedsPath').value.trim()) n++;
  if ($('volumePath').value.trim()) n++;
  return n;
}
document.querySelectorAll('#advCard input, #advCard select').forEach((n) => n.addEventListener('input', refresh));
document.querySelectorAll('#advCard input, #advCard select').forEach((n) => n.addEventListener('change', refresh));
$('gpu').addEventListener('change', () => $('batchField').classList.toggle('hidden', !$('gpu').checked));

let seedSeq = 0;
async function checkSeeds() {
  const path = $('seedsPath').value.trim();
  const seq = ++seedSeq;
  const box = $('seedsNote');
  clear(box);
  state.seedsProblem = null;
  if (!path) { refresh(); return; }
  try {
    const r = await get(`/api/seeds?${q({ path })}`);
    if (seq !== seedSeq) return;
    state.seedsProblem = r.problem;
    const n = r.problem ? noteBox('crit', [r.problem]) : noteBox('good', ['This seed repeats the earlier run exactly, given the same input and settings.']);
    n.classList.add('after-grid');
    box.appendChild(n);
  } catch (e) { state.seedsProblem = e.message; }
  refresh();
}
$('seedsPath').addEventListener('change', checkSeeds);
$('seedsBrowse').addEventListener('click', async () => {
  try { const p = await pickPath('seeds'); if (p) { $('seedsPath').value = p; checkSeeds(); } } catch (e) { toast(e.message); }
});
$('volumeBrowse').addEventListener('click', async () => {
  try { const p = await pickPath('volume'); if (p) { $('volumePath').value = p; refreshGenomes(); } } catch (e) { toast(e.message); }
});
$('volumePath').addEventListener('change', refreshGenomes);
async function refreshGenomes() {
  try { applyGenomes(await get(`/api/genomes?${q({ volume: $('volumePath').value.trim() })}`)); } catch (e) { /* keep */ }
}

/* ----------------------------------------------------------- the launch */

function settings() {
  const d = state.settings.defaults;
  const s = {
    input_type: state.kind,
    input_data: state.inputPath,
    output: $('outputPath').value.trim(),
    name: slug(baseName($('outputPath').value.trim())),
    minimum_signatures: $('minSig').value,
    maximum_signatures: $('maxSig').value,
    nmf_replicates: $('replicates').value,
    cosmic_version: $('cosmicVersion').value,
    stop_after_extraction: !$('assign').checked,
    make_decomposition_plots: $('decompPlots').checked,
    export_probabilities: $('probabilities').checked,
    collapse_to_SBS96: $('collapse96').checked,
    cpu: $('cpu').value.trim() || -1,
    assignment_cpu: $('assignCpu').value.trim() || -1,
    gpu: $('gpu').checked,
    seeds: $('seedsPath').value.trim() || 'random',
    volume: $('volumePath').value.trim() || null,
    replace_existing: !!(state.replaceOutput && state.outCheck && state.outCheck.found),
  };
  ADVANCED.forEach(([id, key, kind]) => { s[key] = kind === 'bool' ? $(id).checked : $(id).value.trim(); });
  if (state.kind === 'vcf') {
    s.reference_genome = $('genomeSel').value;
    s.contexts = chosenContexts();
    s.exome = $('exome').checked;
  } else {
    s.opportunity_genome = $('opportunitySel').value;
    s.exome = $('exomeOther').checked;
  }
  if (state.kind === 'seg') s.seg_caller = $('segCaller').value;
  if (!s.matrix_normalization) s.matrix_normalization = d.matrix_normalization;
  return s;
}

// The first thing still missing, in the order the cards ask for it.
function firstProblem() {
  if (!state.inputPath) return ['inputCard', 'Choose the input.'];
  if (state.inputError) return ['inputCard', 'Fix the problem with the input.'];
  if (!state.input) return ['inputCard', 'Reading the input…'];
  if (state.kind === 'vcf' && state.input.writable === false) return ['inputCard', 'The folder of calls must be writable.'];
  if (state.kind === 'seg' && !$('segCaller').value) return ['inputCard', 'Choose the copy-number caller.'];
  if (state.kind === 'vcf' && !chosenContexts().length) return ['genomeCard', 'Choose at least one mutation context.'];
  if (state.kind === 'vcf' && !genomeInstalled($('genomeSel').value)) return ['genomeCard', `Install ${$('genomeSel').value} first.`];
  const e = effort();
  if (!(e.low >= 1 && e.high >= 1 && e.reps >= 1) || e.low > e.high) return ['ranksCard', 'Fix the number of signatures.'];
  if (!$('outputPath').value.trim()) return ['outputCard', 'Choose the output folder.'];
  if (state.outCheck && state.outCheck.found && !state.replaceOutput) return ['outputCard', 'Choose a new output folder, or replace the earlier results.'];
  if (state.seedsProblem) return ['advCard', 'Fix the seeds file.'];
  return null;
}

function markDone() {
  const problem = firstProblem();
  const order = ['inputCard', 'genomeCard', 'ranksCard', 'cosmicCard', 'outputCard'];
  const stop = problem ? order.indexOf(problem[0]) : order.length;
  order.forEach((id, i) => $(id).classList.toggle('done', stop < 0 ? true : i < stop));
}

function refresh() {
  if (!state.settings) return;
  renderEstimate();
  markDone();
  const n = advancedChanged();
  $('advChanged').textContent = n ? `${n} changed` : 'all default';
  $('advChanged').className = `pill ${n ? 'warn' : 'flat'}`;
  const sum = $('launchSummary');
  clear(sum);
  const problem = firstProblem();
  $('startBtn').disabled = !!problem;
  if (problem) { rich(sum, [{ b: 'Not ready: ' }, problem[1]]); return; }
  const e = effort();
  const ctx = runContexts();
  rich(sum, [{ b: baseName($('outputPath').value.trim()) }, ` · ${plural(state.input.sample_count || 0, 'sample')} · `,
    ctx.length ? ctx.join(', ') : '', ` · ${e.lo} to ${e.hi} signatures · ${num(e.fits)} fits`,
    $('assign').checked ? ' · COSMIC' : '', state.replaceOutput ? ' · replaces earlier results' : '']);
}

$('startBtn').addEventListener('click', async () => {
  const errorBox = $('startError');
  clear(errorBox);
  await checkOutput();
  const problem = firstProblem();
  if (problem) {
    errorBox.appendChild(noteBox('crit', [{ b: 'Not ready yet. ' }, problem[1]]));
    $(problem[0]).scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  const btn = $('startBtn');
  btn.disabled = true;
  try {
    const { job } = await post('/api/run', { settings: settings() });
    state.replaceOutput = false;
    toast(`Started ${job.name}.`);
    await refreshJobs();
    selectJob(job.id);
    show('monitor');
    checkOutput();
  } catch (e) {
    errorBox.appendChild(noteBox('crit', [{ b: 'The run did not start. ' }, e.message]));
  } finally { btn.disabled = false; refresh(); }
});

/* --------------------------------------------------------------- examples */

async function useExample(id) {
  const ex = (state.env.examples || []).find((e) => e.id === id);
  if (!ex) return;
  setKind(ex.input_type);
  if (ex.seg_caller) $('segCaller').value = ex.seg_caller;
  if (ex.reference_genome) { $('genomeSel').value = ex.reference_genome; updateGenomeStatus(); }
  setPreset('quick');
  $('outputPath').value = ex.output;
  state.outputAuto = false;
  await setInput(ex.input_data);
  if (ex.opportunity_genome) $('opportunitySel').value = ex.opportunity_genome;
  $('exampleSel').value = '';
  updateOutput();
}
$('exampleSel').addEventListener('change', (e) => { if (e.target.value) useExample(e.target.value); });
$('homeStart').addEventListener('click', () => show('run'));
$('homeExample').addEventListener('click', async () => { show('run'); await useExample('sbs96'); });
$('homeOpen').addEventListener('click', chooseResults);

function renderRecent() {
  const runs = state.jobs.filter((j) => j.kind === 'run').slice(0, 4);
  $('homeRecentCard').classList.toggle('hidden', !runs.length);
  const box = $('homeRecent');
  clear(box);
  runs.forEach((job) => {
    const row = el('button', 'item');
    row.type = 'button';
    row.appendChild(el('span', `dot ${STATUS_DOT[job.status] || ''}`));
    const txt = el('span', 'txt');
    txt.appendChild(el('span', 'name', job.name));
    txt.appendChild(el('span', 'meta', `${job.status} · ${(job.contexts || []).join(', ')} · ${whenAt(job.created_at)}`));
    row.appendChild(txt);
    row.addEventListener('click', () => {
      if (job.status === 'done') openResults(job.output_dir);
      else { selectJob(job.id); show('monitor'); }
    });
    box.appendChild(row);
  });
}

/* ------------------------------------------------------------------ jobs */

const STATUS_PILL = { running: 'live', done: 'good', failed: 'crit', stopped: 'flat' };
const STATUS_DOT = { running: 'live', done: 'good', failed: 'crit', stopped: '' };
let jobTimer = null;

function jobMeta(job) {
  const bits = [job.status];
  if (job.kind === 'run') bits.push((job.contexts || []).join(', ') || job.input_type);
  if (job.kind === 'install') bits.push(job.reference_genome);
  if (job.kind === 'dashboard') bits.push('dashboard');
  if (job.elapsed_seconds !== undefined) bits.push(clock(job.elapsed_seconds));
  return bits.filter(Boolean).join(' · ');
}

async function refreshJobs() {
  let r;
  try { r = await get('/api/jobs'); } catch (e) { return; }
  const before = new Map(state.jobs.map((j) => [j.id, j.status]));
  state.jobs = r.jobs;
  renderJobList();
  if (state.view === 'home') renderRecent();
  const live = state.jobs.filter((j) => j.status === 'running').length;
  $('liveCount').textContent = String(live);
  $('liveCount').classList.toggle('hidden', !live);
  if (state.jobs.some((j) => j.kind === 'install' && before.get(j.id) === 'running' && j.status !== 'running')) refreshGenomes();
}

function trashIcon() {
  const svg = svgEl('svg', { viewBox: '0 0 16 16', width: '13', height: '13', 'aria-hidden': 'true' });
  svg.appendChild(svgEl('path', { fill: 'currentColor', d: 'M6 1h4l.5 1H14v1.5H2V2h3.5L6 1zm-2.5 3.5h9l-.7 9.6c-.06.8-.7 1.4-1.5 1.4H5.7c-.8 0-1.44-.6-1.5-1.4L3.5 4.5zm3 1.5v7h1.2V6H6.5zm2.8 0v7h1.2V6H9.3z' }));
  return svg;
}

function renderJobList() {
  const list = $('jobList');
  clear(list);
  if (!state.jobs.length) { list.appendChild(el('p', 'empty', 'No runs yet.')); return; }
  state.jobs.forEach((job) => {
    const wrap = el('div', 'runrow');
    wrap.dataset.job = job.id;
    const row = el('button', `item${job.id === state.jobId ? ' on' : ''}`);
    row.type = 'button';
    row.appendChild(el('span', `dot ${STATUS_DOT[job.status] || ''}`));
    const txt = el('span', 'txt');
    txt.appendChild(el('span', 'name', job.name));
    txt.appendChild(el('span', 'meta', jobMeta(job)));
    row.appendChild(txt);
    row.addEventListener('click', () => { selectJob(job.id); show('monitor'); });
    wrap.appendChild(row);
    if (job.status !== 'running') {
      wrap.classList.add('has-actions');
      if (job.kind === 'run') {
        const del = el('button', 'rm del');
        del.type = 'button';
        del.title = 'Delete this run and its results for good';
        del.setAttribute('aria-label', `Delete ${job.name}`);
        del.appendChild(trashIcon());
        del.addEventListener('click', (e) => { e.stopPropagation(); askDelete(job); });
        wrap.appendChild(del);
      }
      const hide = el('button', 'rm hide', '×');
      hide.type = 'button';
      hide.title = 'Remove from the list (its results stay on disk)';
      hide.setAttribute('aria-label', `Remove ${job.name} from the list`);
      hide.addEventListener('click', (e) => { e.stopPropagation(); removeFromList(job); });
      wrap.appendChild(hide);
    }
    list.appendChild(wrap);
  });
}

function leaveMonitor() {
  state.jobId = null;
  state.job = null;
  clearInterval(jobTimer);
  $('monitorBody').classList.add('hidden');
  $('monitorEmpty').classList.remove('hidden');
}

async function removeFromList(job) {
  try { await post(`/api/jobs/${job.id}/hide`); } catch (e) { toast(e.message); return; }
  if (state.jobId === job.id) leaveMonitor();
  await refreshJobs();
  toast(`Removed ${job.name} from the list. Its results stay on disk.`, {
    label: 'Undo',
    fn: async () => { try { await post(`/api/jobs/${job.id}/unhide`); await refreshJobs(); } catch (e) { toast(e.message); } },
  });
}

async function askDelete(job) {
  let plan;
  try { plan = await get(`/api/jobs/${job.id}/delete-preview`); } catch (e) { toast(e.message); return; }
  state.deleting = { job, plan };
  $('deleteTitle').textContent = `Delete ${job.name} for good?`;
  const msg = $('deleteText');
  clear(msg);
  if (plan.deletes_files) {
    msg.appendChild(rich(el('p'), ['This deletes the run and its results: ',
      { b: `${plural(plan.files, 'file')}, ${bytes(plan.bytes)}` },
      ' that SigProfilerExtractor wrote (every context folder, the dashboard and the run files) in']));
    msg.appendChild(el('p', 'mono path', plan.output_dir));
    msg.appendChild(el('p', null, 'Other files in that folder are kept.'));
  } else {
    msg.appendChild(el('p', null, 'This deletes the run from the list for good.'));
    if (plan.kept_because) msg.appendChild(el('p', null, plan.kept_because));
  }
  msg.appendChild(rich(el('p'), [{ b: 'This cannot be undone' },
    ': the files do not go to the Trash or Recycle Bin. To only take the run off the list, use × (Remove from list) instead.']));
  $('deleteGo').disabled = false;
  $('deleteDialog').showModal();
}
$('deleteCancel').addEventListener('click', () => $('deleteDialog').close());
$('deleteGo').addEventListener('click', async () => {
  const { job, plan } = state.deleting || {};
  if (!job) return;
  $('deleteGo').disabled = true;
  try {
    const r = await post(`/api/jobs/${job.id}/delete`);
    $('deleteDialog').close();
    if (state.jobId === job.id) leaveMonitor();
    await refreshJobs();
    if (plan.output_dir && state.resultsPath && r.removed) {
      $('resultsBody').classList.add('hidden');
      $('resultsEmpty').classList.remove('hidden');
      state.resultsPath = null;
    }
    toast(r.removed ? `Deleted ${job.name} and its results.` : `Deleted ${job.name}.`);
  } catch (e) { $('deleteGo').disabled = false; toast(e.message); }
});
// The run the Monitor shows; fetched if its first status poll has not come back.
async function currentJob() {
  if (state.job && state.job.id === state.jobId) return state.job;
  if (!state.jobId) return null;
  try { return (await get(`/api/jobs/${state.jobId}`)).job; } catch (e) { return null; }
}
$('hideBtn').addEventListener('click', async () => { const job = await currentJob(); if (job) removeFromList(job); });
$('deleteBtn').addEventListener('click', async () => { const job = await currentJob(); if (job) askDelete(job); });

/* --------------------------------------------------------------- monitor */

function selectJob(id) {
  state.jobId = id;
  // Known at once from the Runs list, so Remove and Delete work before the
  // first status poll comes back.
  state.job = state.jobs.find((j) => j.id === id) || null;
  state.logOffset = 0;
  state.logTail = '';
  clear($('jobLog'));
  $('monitorEmpty').classList.add('hidden');
  $('monitorBody').classList.remove('hidden');
  renderJobList();
  clearInterval(jobTimer);
  pollJob();
  jobTimer = setInterval(pollJob, 1500);
}

function appendLog(text) {
  const log = $('jobLog');
  const lines = (state.logTail + text).split('\n');
  state.logTail = lines.pop();
  // SigProfilerAssignment draws progress bars with carriage returns: keep
  // what follows the last one. A line ending in \r\n (Windows) is not one.
  lines.forEach((raw) => {
    const line = raw.replace(/\r$/, '').split('\r').pop();
    let node;
    if (line.startsWith('== ')) node = el('span', 'step-line', line);
    else if (/Traceback|Error|error:/.test(line)) node = el('span', 'err-line', line);
    else node = document.createTextNode(line);
    log.appendChild(node);
    log.appendChild(document.createTextNode('\n'));
  });
  if ($('followLog').checked) log.scrollTop = log.scrollHeight;
}

async function pollJob() {
  const id = state.jobId;
  if (!id) return;
  let r;
  try { r = await get(`/api/jobs/${id}`); } catch (e) { return; }
  if (!r.job || id !== state.jobId) return;
  try {
    const chunk = await get(`/api/jobs/${id}/log?offset=${state.logOffset}`);
    if (id !== state.jobId) return;
    if (chunk.text) appendLog(chunk.text);
    state.logOffset = chunk.offset;
  } catch (e) { /* not written yet */ }
  renderJob(r.job, r.progress);
  if (r.job.status !== 'running') {
    clearInterval(jobTimer);
    if (state.logTail) appendLog('\n');
    refreshJobs();
  }
}

const elapsedOf = (job) => (job.elapsed_seconds !== undefined ? job.elapsed_seconds : Date.now() / 1000 - job.created_at);
const PHASE_TEXT = {
  input: 'Reading the input', matrices: 'Building the matrices with SigProfilerMatrixGenerator',
  extract: 'Extracting signatures', assign: 'Matching to COSMIC', dashboard: 'Building the dashboard', done: 'Finished',
};

function renderJob(job, prog) {
  state.job = job;
  $('jobTitle').textContent = job.name;
  const p = $('jobPill');
  p.className = `pill ${STATUS_PILL[job.status] || 'flat'}`;
  p.textContent = job.status;
  $('jobNote').textContent = { run: 'signature extraction', install: 'reference genome install', dashboard: 'dashboard build' }[job.kind] || '';
  const running = job.status === 'running';
  $('stopBtn').classList.toggle('hidden', !running);
  $('hideBtn').classList.toggle('hidden', running);
  $('deleteBtn').classList.toggle('hidden', running || job.kind !== 'run');
  $('jobClock').textContent = clock(elapsedOf(job));

  const bar = $('jobBar');
  bar.className = '';
  const phase = $('jobPhase');
  clear(phase);
  const ctxBox = $('ctxProgress');
  clear(ctxBox);
  if (job.kind === 'run' && prog) {
    const frac = job.status === 'done' ? 1 : prog.fraction;
    bar.style.width = `${Math.max(running ? 3 : 0, frac * 100)}%`;
    if (job.status === 'done') bar.classList.add('done');
    else if (job.status === 'failed') bar.classList.add('failed');
    else if (prog.phase === 'input' || prog.phase === 'matrices') bar.classList.add('indeterminate');
    if (running) {
      rich(phase, [{ b: PHASE_TEXT[prog.phase] || 'Working' }]);
      if (prog.remaining_seconds !== null && prog.remaining_seconds !== undefined && prog.phase === 'extract') {
        rich(phase, [` · about ${clock(prog.remaining_seconds)} of extraction left`]);
      }
    } else rich(phase, [{ b: job.status === 'done' ? 'Finished' : (job.status === 'failed' ? 'Failed' : 'Stopped') }]);
    prog.contexts.forEach((c) => {
      const row = el('div', `ctx-row ${c.state}`);
      row.appendChild(el('span', 'ctx-name', c.name));
      const meter = el('div', 'mini');
      const fill = el('i');
      const f = c.state === 'done' ? 1 : (c.state === 'active'
        ? (c.stage === 'assign' ? 0.95 : (c.ranks_done + c.replicates_done / Math.max(1, c.replicates_total)) / Math.max(1, c.ranks_total)) : 0);
      fill.style.width = `${Math.round(Math.min(1, f) * 100)}%`;
      meter.appendChild(fill);
      row.appendChild(meter);
      let text;
      if (c.state === 'skipped') text = 'skipped: no mutations of this type';
      else if (c.state === 'done') text = 'done';
      else if (c.state === 'waiting') text = 'waiting';
      else if (c.stage === 'assign') text = 'matching to COSMIC';
      else text = `${c.rank} signature${c.rank === 1 ? '' : 's'} (${c.ranks_done + 1} of ${c.ranks_total}) · replicate ${Math.min(c.replicates_done + 1, c.replicates_total)} of ${c.replicates_total}`;
      row.appendChild(el('span', 'ctx-state', text));
      ctxBox.appendChild(row);
    });
  } else {
    if (job.status === 'done') { bar.style.width = '100%'; bar.classList.add('done'); }
    else if (job.status === 'failed') { bar.style.width = '100%'; bar.classList.add('failed'); }
    else if (running) bar.classList.add('indeterminate');
    rich(phase, [{ b: running ? 'Working' : job.status }]);
  }

  const facts = $('jobFacts');
  clear(facts);
  const add = (k, v, mono) => { if (!v && v !== 0) return; facts.appendChild(el('dt', null, k)); facts.appendChild(el('dd', mono ? 'mono' : null, String(v))); };
  if (job.kind === 'run') {
    add('Input', job.input, true);
    add('Output', job.output_dir, true);
    add('Contexts', (job.contexts || []).join(', '));
    add('Signatures', `${job.minimum_signatures} to ${job.maximum_signatures}, ${num(job.nmf_replicates)} replicates each`);
    if (job.effort) add('Work', `${num(job.effort.fits)} NMF fits`);
    add('COSMIC', job.assignment ? `matched (${job.reference_genome})` : 'not matched');
  } else if (job.kind === 'install') add('Genome', job.reference_genome);
  else if (job.kind === 'dashboard') add('Folder', job.output_dir, true);
  add('Started', whenAt(job.created_at));

  const result = $('jobResult');
  clear(result);
  result.classList.toggle('hidden', running);
  if (job.status === 'done' && job.kind === 'run') {
    const box = el('div', 'note-box good row');
    const found = job.found_contexts || [];
    const parts = [{ b: 'Signatures extracted. ' }];
    if (found.length) parts.push(found.map((c) => `${c.name}: ${plural(c.suggested_rank || 0, 'signature')} suggested`).join(' · '));
    box.appendChild(rich(el('span'), parts));
    const open = el('button', 'btn sm primary', 'Open results');
    open.type = 'button';
    open.addEventListener('click', () => openResults(job.output_dir));
    box.appendChild(open);
    result.appendChild(box);
    (job.warnings || []).forEach((w) => result.appendChild(noteBox('warn', [w])));
  } else if (job.status === 'done' && job.kind === 'install') {
    result.appendChild(noteBox('good', [{ b: `${job.reference_genome} is installed. ` }, 'It is ready for runs.']));
  } else if (job.status === 'done' && job.kind === 'dashboard') {
    const box = el('div', 'note-box good row');
    box.appendChild(rich(el('span'), [{ b: 'The dashboard is ready.' }]));
    const open = el('button', 'btn sm primary', 'Open results');
    open.type = 'button';
    open.addEventListener('click', () => openResults(job.output_dir));
    box.appendChild(open);
    result.appendChild(box);
  } else if (job.status === 'failed') {
    result.appendChild(noteBox('crit', [{ b: 'The run failed. ' }, job.error || '', ' The log below has the details.']));
    (job.warnings || []).forEach((w) => result.appendChild(noteBox('warn', [w])));
  } else if (job.status === 'stopped') {
    result.appendChild(noteBox('', ['Stopped before it finished. Files already written stay where they are.']));
  }
}

$('stopBtn').addEventListener('click', async () => {
  if (!state.jobId) return;
  $('stopBtn').disabled = true;
  try { await post(`/api/jobs/${state.jobId}/stop`); toast('Stopped.'); }
  catch (e) { toast(e.message); } finally { $('stopBtn').disabled = false; pollJob(); }
});

/* --------------------------------------------------------------- results */

async function openResults(path) {
  path = String(path || '').trim();
  if (!path) return;
  let r;
  try { r = await get(`/api/results?${q({ path })}`); } catch (e) { toast(e.message); return; }
  state.results = r;
  state.resultsPath = r.output_dir;
  $('openPath').value = r.output_dir;
  $('resultsEmpty').classList.add('hidden');
  $('resultsBody').classList.remove('hidden');
  renderResultNotes(r);
  renderContextCards(r);
  renderComparison(r);
  renderDashboard(r);
  renderPlots(r);
  renderFiles(r);
  show('results');
}

function renderResultNotes(r) {
  const box = $('resNotes');
  clear(box);
  if (r.job_status && !/completed successfully/i.test(r.job_status)) {
    box.appendChild(noteBox('warn', [{ b: 'The run did not finish. ' }, `JOB_METADATA.txt says: ${r.job_status}`]));
  }
  if (!r.contexts.length) box.appendChild(noteBox('warn', ['No context has finished in this folder yet.']));
  if (r.previous.length) {
    box.appendChild(noteBox('', [`${plural(r.previous.length, 'earlier result')} moved aside by SigProfilerExtractor ${r.previous.length === 1 ? 'is' : 'are'} also in this folder (`,
      { mono: r.previous.join(', ') }, '). They are not shown here.']));
  }
}

function renderContextCards(r) {
  const box = $('ctxCards');
  clear(box);
  r.contexts.forEach((c) => {
    const card = el('div', 'card ctx-card');
    const hd = el('div', 'hd');
    hd.appendChild(el('h3', null, c.name));
    hd.appendChild(el('span', 'note', `${plural(c.samples, 'sample')} · ranks ${c.ranks.length ? `${Math.min(...c.ranks)} to ${Math.max(...c.ranks)}` : '–'}`));
    card.appendChild(hd);
    const bd = el('div', 'bd');
    const big = el('div', 'ctx-big');
    big.appendChild(el('span', 'v', c.suggested_rank === null ? '–' : String(c.suggested_rank)));
    big.appendChild(el('span', 'k', c.suggested_rank === 1 ? 'signature suggested' : 'signatures suggested'));
    bd.appendChild(big);
    if (c.denovo_signatures.length) {
      bd.appendChild(el('div', 'lbl', 'De novo'));
      const chips = el('div', 'chips sm');
      c.denovo_signatures.forEach((s) => chips.appendChild(el('span', 'chip static', s)));
      bd.appendChild(chips);
    }
    if (c.cosmic_signatures.length) {
      bd.appendChild(el('div', 'lbl', 'COSMIC'));
      const chips = el('div', 'chips sm');
      c.cosmic_signatures.forEach((s) => chips.appendChild(el('span', 'chip static cosmic', s)));
      bd.appendChild(chips);
    } else if (!c.assigned) bd.appendChild(el('p', 'hint', 'Not matched to COSMIC.'));
    card.appendChild(bd);
    box.appendChild(card);
  });
}

// Okabe-Ito, then a few more: colour-blind safe, one colour per COSMIC name.
const SPLIT_COLORS = ['#0072B2', '#E69F00', '#009E73', '#CC79A7', '#56B4E9', '#D55E00', '#F0E442',
  '#332288', '#999933', '#882255', '#44AA99', '#888888'];
const cosineClass = (v) => (v >= 0.9 ? 'good' : (v >= 0.8 ? 'warn' : 'flat'));
const fmtCos = (v) => (v === undefined || v === null ? '–' : Number(v).toFixed(2));

function renderComparison(r) {
  const withData = r.contexts.filter((c) => c.comparison && c.comparison.signatures.length);
  $('compareCard').classList.toggle('hidden', !withData.length);
  const body = $('compareBody');
  clear(body);
  const catalogues = [...new Set(withData.map((c) => c.comparison.catalogue).filter(Boolean))];
  $('compareNote').textContent = catalogues.length ? `compared with ${catalogues.join(', ')}` : 'how each signature relates to known ones';
  withData.forEach((ctx) => {
    const section = el('div', 'cmp-ctx');
    if (withData.length > 1) section.appendChild(el('h3', null, ctx.name));
    const head = el('div', 'cmp-row cmp-head');
    ['De novo signature', 'Split into COSMIC signatures', 'Closest COSMIC signature'].forEach((t) => head.appendChild(el('div', null, t)));
    section.appendChild(head);
    const colorOf = new Map();
    const color = (name) => {
      if (!colorOf.has(name)) colorOf.set(name, SPLIT_COLORS[colorOf.size % SPLIT_COLORS.length]);
      return colorOf.get(name);
    };
    ctx.comparison.signatures.forEach((sig) => {
      const row = el('div', 'cmp-row');
      row.dataset.signature = sig.name;
      row.appendChild(el('div', 'cmp-name', sig.name));

      const split = el('div', 'cmp-split');
      split.dataset.label = 'Split into COSMIC signatures';
      if (sig.decomposition.length) {
        const bar = el('div', 'split-bar');
        bar.setAttribute('role', 'img');
        bar.setAttribute('aria-label', sig.decomposition.map((p) => `${p.name} ${p.percent.toFixed(1)}%`).join(', '));
        sig.decomposition.forEach((p) => {
          const seg = el('span');
          seg.style.width = `${Math.max(p.percent, 0.6)}%`;
          seg.style.background = color(p.name);
          seg.title = `${p.name}: ${p.percent.toFixed(1)}%`;
          bar.appendChild(seg);
        });
        split.appendChild(bar);
        const legend = el('div', 'split-legend');
        sig.decomposition.forEach((p) => {
          const item = el('span', 'split-item');
          const dot = el('i');
          dot.style.background = color(p.name);
          item.appendChild(dot);
          item.appendChild(el('b', null, p.name));
          item.appendChild(document.createTextNode(` ${p.percent.toFixed(1)}%`));
          legend.appendChild(item);
        });
        split.appendChild(legend);
        if (sig.fit.cosine !== undefined) {
          const fit = el('div', 'split-fit');
          rich(fit, ['Mix reconstructs it with cosine ', { b: fmtCos(sig.fit.cosine) }]);
          if (sig.fit.l2 !== undefined) fit.appendChild(document.createTextNode(` · L2 error ${sig.fit.l2.toFixed(1)}%`));
          split.appendChild(fit);
        }
      } else split.appendChild(el('span', 'muted', 'Not matched to COSMIC in this run.'));
      row.appendChild(split);

      const close = el('div', 'cmp-close');
      close.dataset.label = 'Closest COSMIC signature';
      if (sig.closest.length) {
        const [best, ...rest] = sig.closest;
        const top = el('div', 'close-best');
        top.appendChild(el('b', null, best.name));
        const p = pill(cosineClass(best.cosine), `cosine ${fmtCos(best.cosine)}`);
        p.title = 'Cosine similarity: 1 means an identical profile; 0.9 and above is usually read as the same signature.';
        top.appendChild(p);
        close.appendChild(top);
        if (rest.length) close.appendChild(el('div', 'close-rest', `then ${rest.map((m) => `${m.name} ${fmtCos(m.cosine)}`).join(', ')}`));
      } else close.appendChild(el('span', 'muted', 'No COSMIC catalogue for this context.'));
      row.appendChild(close);
      section.appendChild(row);
    });
    body.appendChild(section);
  });
}

function renderDashboard(r) {
  const frame = $('dashFrame');
  const missing = $('dashMissing');
  clear(missing);
  const has = !!r.dashboard;
  $('dashWrap').classList.toggle('hidden', !has);
  missing.classList.toggle('hidden', has);
  ['dashOpen', 'dashDownload', 'dashRebuild'].forEach((id) => $(id).classList.toggle('hidden', !has));
  if (has) {
    const src = `/api/results/dashboard?${q({ path: r.dashboard.path })}`;
    if (frame.getAttribute('src') !== src) frame.setAttribute('src', src);
    $('dashOpen').href = src;
    $('dashDownload').href = `/api/results/download?${q({ path: r.dashboard.path })}`;
    $('dashDownload').setAttribute('download', 'reports.html');
    $('dashNote').textContent = `SigProfilerExtractor's reports.html · ${bytes(r.dashboard.size)} · ${whenAt(r.dashboard.modified)}`;
  } else {
    frame.removeAttribute('src');
    $('dashNote').textContent = 'not built yet';
    missing.appendChild(rich(el('p'), ['This folder has no ', { mono: 'reports.html' },
      ': it was made before SigProfilerExtractor wrote dashboards, or with the dashboard turned off. It can be built from the files here.']));
    const build = el('button', 'btn primary', 'Build the dashboard');
    build.type = 'button';
    build.addEventListener('click', () => buildDashboard(r.output_dir, build));
    missing.appendChild(build);
  }
}
$('dashRebuild').addEventListener('click', () => buildDashboard(state.resultsPath, $('dashRebuild')));

async function buildDashboard(folder, btn) {
  if (btn) btn.disabled = true;
  let job;
  try { job = (await post('/api/dashboard/build', { path: folder })).job; }
  catch (e) { toast(e.message); if (btn) btn.disabled = false; return; }
  toast('Building the dashboard…');
  refreshJobs();
  const started = Date.now();
  const poll = async () => {
    let j;
    try { j = (await get(`/api/jobs/${job.id}`)).job; } catch (e) { j = null; }
    if (j && j.status === 'running' && Date.now() - started < 30 * 60 * 1000) { setTimeout(poll, 1500); return; }
    if (btn) btn.disabled = false;
    refreshJobs();
    if (j && j.status === 'done') { toast('The dashboard is ready.'); $('dashFrame').removeAttribute('src'); openResults(folder); }
    else toast(j && j.error ? `The dashboard could not be built: ${j.error}` : 'The dashboard could not be built.');
  };
  setTimeout(poll, 1500);
}

function fileRow(f, viewable) {
  const row = el('div', 'f');
  // Plots sit under a heading naming their group already.
  if (!viewable) row.appendChild(el('span', 'badge', f.group.replace('Choosing the number of signatures', 'Selection')));
  const nm = el('span', 'nm', f.rel || f.name);
  nm.title = f.path;
  row.appendChild(nm);
  row.appendChild(el('span', 's', bytes(f.size)));
  if (viewable) {
    const open = el('a', 'btn sm primary', 'Open');
    open.href = `/api/results/view?${q({ path: f.path })}`;
    open.target = '_blank';
    open.rel = 'noopener';
    row.appendChild(open);
  }
  const dl = el('a', 'btn sm', 'Download');
  dl.href = `/api/results/download?${q({ path: f.path })}`;
  dl.setAttribute('download', f.name);
  row.appendChild(dl);
  return row;
}

const PLOT_ORDER = ['Choosing the number of signatures', 'De novo solution', 'COSMIC decomposition'];
function renderPlots(r) {
  const box = $('plotGroups');
  clear(box);
  let total = 0;
  r.contexts.forEach((c) => {
    if (!c.plots.length) return;
    total += c.plots.length;
    const groups = {};
    c.plots.forEach((p) => { (groups[p.group] = groups[p.group] || []).push(p); });
    const names = Object.keys(groups).sort((a, b) => {
      const ia = PLOT_ORDER.indexOf(a), ib = PLOT_ORDER.indexOf(b);
      if (ia >= 0 || ib >= 0) return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
      return (parseInt(a.replace(/\D+/g, ''), 10) || 0) - (parseInt(b.replace(/\D+/g, ''), 10) || 0);
    });
    const sec = el('div', 'plot-ctx');
    sec.appendChild(el('h3', null, c.name));
    names.forEach((name) => {
      const d = el('details', 'plot-group');
      if (PLOT_ORDER.includes(name)) d.open = true;
      const s = el('summary');
      s.appendChild(el('b', null, name.startsWith('Rank') ? `${name.replace('Rank ', '')} signatures` : name));
      s.appendChild(el('span', 'muted', ` · ${plural(groups[name].length, 'PDF')}`));
      d.appendChild(s);
      const list = el('div', 'files');
      groups[name].forEach((p) => list.appendChild(fileRow(p, true)));
      d.appendChild(list);
      sec.appendChild(d);
    });
    box.appendChild(sec);
  });
  $('plotsNote').textContent = total ? `${plural(total, 'figure')} SigProfilerExtractor drew` : '';
  if (!total) box.appendChild(el('p', 'empty', 'No PDF plots in this folder.'));
}

function renderFiles(r) {
  const list = $('fileList');
  clear(list);
  const rows = [...r.files];
  r.contexts.forEach((c) => c.tables.forEach((t) => rows.push(t)));
  rows.forEach((f) => list.appendChild(fileRow(f, false)));
  $('filesNote').textContent = rows.length ? `${plural(rows.length, 'file')}` : '';
}

async function chooseResults() {
  try { const path = await pickPath('results'); if (path) await openResults(path); } catch (e) { toast(e.message); }
}
$('openResultsBtn').addEventListener('click', chooseResults);
$('resultsChoose').addEventListener('click', chooseResults);
$('openPath').addEventListener('keydown', (e) => { if (e.key === 'Enter') openResults(e.target.value); });
$('resultsPath').addEventListener('keydown', (e) => { if (e.key === 'Enter') openResults(e.target.value); });

/* ------------------------------------------------------------------ quit */

$('quitBtn').addEventListener('click', () => {
  const live = state.jobs.filter((j) => j.status === 'running');
  $('quitText').textContent = live.length
    ? `This stops the app and ${live.length === 1 ? 'the run' : `the ${live.length} runs`} still in progress. Results already written stay where they are.`
    : 'This stops the app. Your results stay where they are.';
  $('quitGo').textContent = live.length ? 'Stop and quit' : 'Quit';
  $('quitDialog').showModal();
});
$('quitCancel').addEventListener('click', () => $('quitDialog').close());
$('quitGo').addEventListener('click', async () => {
  try { await post('/api/quit'); } catch (e) { /* the server may close the socket as it stops */ }
  $('quitDialog').close();
  const app = $('app');
  clear(app);
  const box = el('div', 'stopped');
  box.appendChild(el('h2', null, 'The Workbench has stopped.'));
  box.appendChild(el('p', null, 'You can close this tab. Start it again with launch_web.sh, or with sigprofilerextractor-web.'));
  app.appendChild(box);
});

/* ------------------------------------------------------------------ init */

loadEnv().catch((e) => {
  $('envPill').className = 'pill crit';
  $('envPill').textContent = 'no server';
  $('startError').appendChild(noteBox('crit', [{ b: 'Could not reach the server. ' }, e.message]));
});
refreshJobs();
setInterval(refreshJobs, 3000);
