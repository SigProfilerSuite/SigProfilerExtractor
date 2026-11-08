'use strict';

const DATA = JSON.parse(document.getElementById('dashboardData').textContent);
const $ = (id) => document.getElementById(id);
const state = { context: 0, tab: 'overview', rank: null, bundle: 0 };
const COLORS = ['#137c79', '#d95d4f', '#b78318', '#3276a8', '#7b5aa6', '#59834b', '#bd6d9c', '#6b747c'];

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function clone(value) {
  return typeof structuredClone === 'function'
    ? structuredClone(value)
    : JSON.parse(JSON.stringify(value));
}

function numeric(value) {
  if (typeof value === 'number') return value;
  const match = String(value ?? '').replace(/,/g, '').match(/[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?/i);
  return match ? Number(match[0]) : NaN;
}

function format(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') {
    if (Math.abs(value) >= 1000) return value.toLocaleString();
    return Number.isInteger(value) ? String(value) : value.toLocaleString(undefined, { maximumFractionDigits: 5 });
  }
  return String(value);
}

function currentContext() { return DATA.contexts[state.context]; }
function currentSolution() {
  const context = currentContext();
  return context.solutions.find((item) => item.rank === state.rank) || context.solutions[0] || null;
}

function columnIndex(table, patterns) {
  if (!table) return -1;
  return table.columns.findIndex((column) => patterns.some((pattern) => pattern.test(String(column))));
}

function purgePlots(root) {
  if (!window.Plotly) return;
  root.querySelectorAll('.js-plotly-plot').forEach((plot) => Plotly.purge(plot));
}

function plot(target, traces, layout, config = {}) {
  const finalLayout = {
    font: { family: 'Inter, Segoe UI, Arial, sans-serif', size: 12, color: '#28323a' },
    paper_bgcolor: '#ffffff', plot_bgcolor: '#ffffff',
    margin: { l: 65, r: 35, t: 45, b: 70 },
    ...clone(layout || {}),
  };
  const pending = Plotly.newPlot(target, clone(traces), finalLayout, {
    responsive: true, displaylogo: false,
    toImageButtonOptions: { format: 'svg' },
    ...clone(config || {}),
  });
  // View builders can prepare a section before attaching it to <main>.
  // Resize on the next task, after the synchronous render has attached it.
  setTimeout(() => { if (target.isConnected) Plotly.Plots.resize(target); }, 0);
  return pending;
}

function header(title, subtitle) {
  const wrap = node('div', 'view-header');
  const text = node('div');
  text.append(node('h2', '', title), node('p', '', subtitle));
  wrap.append(text);
  return wrap;
}

function empty(parent, message) { parent.append(node('div', 'empty', message)); }

function kpis(parent, items) {
  const wrap = node('div', 'kpis');
  items.forEach(([label, value]) => {
    const item = node('div', 'kpi');
    item.append(node('div', 'label', label), node('div', 'value', format(value)));
    wrap.append(item);
  });
  parent.append(wrap);
}

function downloadTable(table, filename) {
  const quote = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const rows = [table.columns, ...table.rows];
  const blob = new Blob([rows.map((row) => row.map(quote).join(',')).join('\n')], { type: 'text/csv;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

function renderTable(parent, table, options = {}) {
  if (!table || !table.columns.length) { empty(parent, options.empty || 'No table was produced for this result.'); return; }
  const tools = node('div', 'table-tools');
  const search = document.createElement('input');
  search.type = 'search'; search.placeholder = 'Filter rows'; search.setAttribute('aria-label', 'Filter rows');
  const exportButton = node('button', 'button', 'Export CSV');
  exportButton.type = 'button';
  exportButton.addEventListener('click', () => downloadTable(table, options.filename || table.source || 'results.csv'));
  tools.append(search, exportButton);
  const wrap = node('div', 'table-wrap');
  const tableElement = document.createElement('table');
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  const tbody = document.createElement('tbody');
  let rows = table.rows.map((row, index) => ({ row, index }));
  let sortIndex = -1; let ascending = true;

  function drawRows() {
    const query = search.value.trim().toLowerCase();
    tbody.replaceChildren();
    rows.filter(({ row }) => !query || row.some((cell) => String(cell ?? '').toLowerCase().includes(query)))
      .forEach(({ row }) => {
        const tr = document.createElement('tr');
        if (options.selectedRank !== undefined && numeric(row[0]) === options.selectedRank) tr.className = 'selected-row';
        row.forEach((cell) => tr.append(node('td', '', format(cell))));
        tbody.append(tr);
      });
  }

  table.columns.forEach((column, index) => {
    const th = node('th', '', column);
    th.addEventListener('click', () => {
      ascending = sortIndex === index ? !ascending : true; sortIndex = index;
      rows.sort((left, right) => {
        const a = left.row[index]; const b = right.row[index];
        const an = numeric(a); const bn = numeric(b);
        const compared = Number.isNaN(an) || Number.isNaN(bn)
          ? String(a ?? '').localeCompare(String(b ?? '')) : an - bn;
        return ascending ? compared : -compared;
      });
      drawRows();
    });
    headerRow.append(th);
  });
  thead.append(headerRow); tableElement.append(thead, tbody); wrap.append(tableElement);
  search.addEventListener('input', drawRows); drawRows();
  parent.append(tools, wrap);
}

function rankStrip(parent) {
  const context = currentContext();
  const strip = node('div', 'rank-strip');
  context.solutions.forEach((solution) => {
    const button = node('button', `rank-button${solution.rank === state.rank ? ' active' : ''}${solution.selected ? ' selected' : ''}`, `k=${solution.rank}`);
    button.type = 'button'; button.title = solution.selected ? 'Selected solution' : `Rank ${solution.rank}`;
    button.addEventListener('click', () => { state.rank = solution.rank; render(); });
    strip.append(button);
  });
  parent.append(strip);
}

const SECTION_AXES = {
  total_heatmap: ['yaxis4'], detailed_heatmaps: ['yaxis2', 'yaxis3'],
  transcription_bias: ['yaxis5', 'yaxis6', 'xaxis2', 'xaxis3'],
};

// Kept equivalent to SigProfilerPlotting 1.5's client-side panel compaction.
function compactPlot(variant, toggles) {
  const traces = clone(variant.traces); const layout = clone(variant.layout); const removed = [];
  Object.entries(variant.sections || {}).forEach(([key, section]) => {
    const on = toggles[key] !== false; const [start, end] = section.trace_range;
    if (!on && end > start && section.paper_band) removed.push([...section.paper_band]);
    for (let index = start; index < end; index++) traces[index].visible = on;
    (SECTION_AXES[key] || []).forEach((axis) => { if (layout[axis]) layout[axis].visible = on && end > start; });
    (section.annotation_indices || []).forEach((index) => { if (layout.annotations?.[index]) layout.annotations[index].visible = on; });
  });
  if (!removed.length) return { traces, layout };
  const margin = layout.margin || {};
  const verticalMargins = (margin.t ?? 100) + (margin.b ?? 80);
  const remaining = 1 - removed.reduce((sum, [low, high]) => sum + high - low, 0);
  const mapY = (y) => (y - removed.reduce((sum, [low, high]) => sum + Math.max(0, Math.min(y, high) - low), 0)) / remaining;
  Object.entries(layout).forEach(([key, axis]) => {
    if (!/^yaxis\d*$/.test(key) || !axis.domain) return;
    axis.domain = axis.visible === false ? [0, 0.001] : axis.domain.map(mapY);
  });
  (layout.annotations || []).forEach((annotation) => { if (annotation.yref === 'paper') annotation.y = mapY(annotation.y); });
  (layout.shapes || []).forEach((shape) => { if (shape.yref === 'paper') { shape.y0 = mapY(shape.y0); shape.y1 = mapY(shape.y1); } });
  traces.forEach((trace) => {
    if (trace.visible === false || !trace.colorbar) return;
    if (trace.colorbar.y !== undefined) trace.colorbar.y = mapY(trace.colorbar.y);
    if (trace.colorbar.len !== undefined && trace.colorbar.lenmode !== 'pixels') trace.colorbar.len /= remaining;
  });
  layout.height = Math.round(verticalMargins + (layout.height - verticalMargins) * remaining);
  return { traces, layout };
}

function renderProfileSection(parent, profile, title) {
  const section = node('section', 'section');
  const sectionHead = node('div', 'section-head');
  const heading = node('div'); heading.append(node('h3', '', title));
  sectionHead.append(heading); section.append(sectionHead);
  if (!profile || !profile.names.length) { empty(section, 'No signature matrix is available for this result.'); parent.append(section); return; }
  const controls = node('div', 'toolbar');
  const select = document.createElement('select'); select.setAttribute('aria-label', 'Signature');
  profile.names.forEach((name) => { const option = node('option', '', name); option.value = name; select.append(option); });
  controls.append(select); sectionHead.append(controls);
  const panelControls = node('div', 'toolbar hidden');
  const variantSelect = document.createElement('select'); variantSelect.setAttribute('aria-label', 'SBS top panel');
  const checks = node('div', 'check-row');
  const toggles = { transcription_bias: true, total_heatmap: true, detailed_heatmaps: true };
  [['transcription_bias', 'Transcription bias'], ['total_heatmap', 'Total heatmap'], ['detailed_heatmaps', 'Detailed heatmaps']].forEach(([key, label]) => {
    const item = document.createElement('label'); const input = document.createElement('input');
    input.type = 'checkbox'; input.checked = true; input.addEventListener('change', () => { toggles[key] = input.checked; draw(); });
    item.append(input, document.createTextNode(label)); checks.append(item);
  });
  panelControls.append(variantSelect, checks); section.append(panelControls);
  const plotElement = node('div', 'plot'); section.append(plotElement);

  function draw() {
    const response = profile.figures[select.value];
    if (!response) return;
    panelControls.classList.toggle('hidden', response.kind !== 'sbs4608');
    if (response.kind === 'standard') {
      const figure = response.figure; plot(plotElement, figure.traces, figure.layout, figure.config); return;
    }
    const variants = response.variants || {};
    if (!variantSelect.options.length) {
      Object.keys(variants).forEach((name) => { const option = node('option', '', name.replace(/_/g, ' ')); option.value = name; variantSelect.append(option); });
      variantSelect.addEventListener('change', draw);
    }
    const variant = variants[variantSelect.value] || variants.default || Object.values(variants)[0];
    const compacted = compactPlot(variant, toggles);
    plot(plotElement, compacted.traces, compacted.layout, variant.config);
  }
  select.addEventListener('change', draw); draw(); parent.append(section);
}

function overallPlot(parent, context) {
  const table = context.overall_stats;
  if (!table || !table.rows.length) return;
  const rank = table.rows.map((row) => numeric(row[0]));
  const avg = columnIndex(table, [/Stability \(Avg/i, /avg.*stability/i]);
  const min = columnIndex(table, [/Minimum Stability/i]);
  const frob = columnIndex(table, [/Frobenius/i]);
  const cosine = columnIndex(table, [/Mean Cosine Distance/i]);
  const traces = [];
  if (avg >= 0) traces.push({ type: 'scatter', mode: 'lines+markers', name: 'Average stability', x: rank, y: table.rows.map((row) => numeric(row[avg])), line: { color: COLORS[0], width: 3 } });
  if (min >= 0) traces.push({ type: 'scatter', mode: 'lines+markers', name: 'Minimum stability', x: rank, y: table.rows.map((row) => numeric(row[min])), line: { color: COLORS[1], width: 2 } });
  if (frob >= 0) traces.push({ type: 'scatter', mode: 'lines+markers', name: 'Frobenius error', x: rank, y: table.rows.map((row) => numeric(row[frob])), yaxis: 'y2', line: { color: COLORS[2], dash: 'dot' } });
  if (cosine >= 0) traces.push({ type: 'scatter', mode: 'lines+markers', name: 'Mean cosine distance', x: rank, y: table.rows.map((row) => numeric(row[cosine])), yaxis: 'y2', line: { color: COLORS[3], dash: 'dash' } });
  const element = node('div', 'plot'); parent.append(element);
  plot(element, traces, {
    height: 430, hovermode: 'x unified', legend: { orientation: 'h', y: 1.12 },
    xaxis: { title: 'Number of signatures', dtick: 1, gridcolor: '#edf0f2' },
    yaxis: { title: 'Stability', range: [-1, 1.05], gridcolor: '#edf0f2' },
    yaxis2: { title: 'Reconstruction metric', overlaying: 'y', side: 'right', rangemode: 'tozero' },
  });
}

function activityValues(table, query, normalized) {
  const names = table.columns.slice(1);
  const rows = table.rows.filter((row) => !query || String(row[0]).toLowerCase().includes(query));
  const samples = rows.map((row) => String(row[0]));
  const values = names.map((_, index) => rows.map((row) => Number(row[index + 1]) || 0));
  if (normalized) {
    samples.forEach((_, sampleIndex) => {
      const total = values.reduce((sum, signature) => sum + signature[sampleIndex], 0);
      values.forEach((signature) => { signature[sampleIndex] = total ? 100 * signature[sampleIndex] / total : 0; });
    });
  }
  return { names, samples, values };
}

function renderActivitiesBlock(parent, table, title) {
  const section = node('section', 'section');
  const sectionHead = node('div', 'section-head'); const heading = node('div'); heading.append(node('h3', '', title));
  sectionHead.append(heading); section.append(sectionHead);
  if (!table || table.columns.length < 2) { empty(section, 'No activity matrix is available for this result.'); parent.append(section); return; }
  const controls = node('div', 'toolbar');
  const search = document.createElement('input'); search.type = 'search'; search.placeholder = 'Filter samples'; search.setAttribute('aria-label', 'Filter samples');
  const mode = node('div', 'segment');
  const stacked = node('button', 'active', 'Stacked'); const heatmap = node('button', '', 'Heatmap');
  stacked.type = heatmap.type = 'button'; mode.append(stacked, heatmap);
  const normalizeLabel = document.createElement('label'); const normalize = document.createElement('input'); normalize.type = 'checkbox';
  normalizeLabel.append(normalize, document.createTextNode(' Percentage'));
  controls.append(search, mode, normalizeLabel); sectionHead.append(controls);
  const plotElement = node('div', 'plot'); section.append(plotElement);
  let view = 'stacked';
  function draw() {
    const data = activityValues(table, search.value.trim().toLowerCase(), normalize.checked);
    if (view === 'stacked') {
      const traces = data.names.map((name, index) => ({ type: 'bar', name, x: data.samples, y: data.values[index], marker: { color: COLORS[index % COLORS.length] }, hovertemplate: `${name}<br>%{x}: %{y:.4g}<extra></extra>` }));
      plot(plotElement, traces, { height: 450, barmode: 'stack', xaxis: { title: 'Sample', tickangle: -55, automargin: true }, yaxis: { title: normalize.checked ? 'Activity (%)' : 'Mutations', rangemode: 'tozero' }, legend: { orientation: 'h', y: 1.13 } });
    } else {
      plot(plotElement, [{ type: 'heatmap', x: data.samples, y: data.names, z: data.values, colorscale: 'Viridis', colorbar: { title: normalize.checked ? '%' : 'Activity' }, hovertemplate: '%{y}<br>%{x}: %{z:.4g}<extra></extra>' }], { height: Math.max(380, 34 * data.names.length), xaxis: { title: 'Sample', tickangle: -55, automargin: true }, yaxis: { title: 'Signature', automargin: true } });
    }
  }
  stacked.addEventListener('click', () => { view = 'stacked'; stacked.classList.add('active'); heatmap.classList.remove('active'); draw(); });
  heatmap.addEventListener('click', () => { view = 'heatmap'; heatmap.classList.add('active'); stacked.classList.remove('active'); draw(); });
  search.addEventListener('input', draw); normalize.addEventListener('change', draw); draw();
  const tableSection = node('details'); const summary = node('summary', '', 'Activity matrix'); tableSection.append(summary);
  const tableBody = node('div'); renderTable(tableBody, table, { filename: table.source || 'activities.csv' }); tableSection.append(tableBody); section.append(tableSection);
  parent.append(section);
}

function renderOverview(content, context) {
  content.append(header('Overview', `${context.name} extraction and solution selection`));
  kpis(content, [
    ['Selected rank', context.selected_rank ? `k=${context.selected_rank}` : '—'],
    ['Ranks evaluated', context.solutions.length],
    ['Samples', context.sample_summary.samples],
    ['Mutation channels', context.sample_summary.channels],
  ]);
  const selection = node('section', 'section'); selection.append(node('h3', '', 'Solution selection'));
  overallPlot(selection, context); renderTable(selection, context.overall_stats, { filename: `${context.name}_all_solutions.csv`, selectedRank: context.selected_rank }); content.append(selection);
  if (context.sample_summary.totals.length) {
    const burden = node('section', 'section'); burden.append(node('h3', '', 'Sample mutation burden'));
    const plotElement = node('div', 'plot compact'); burden.append(plotElement);
    const sorted = [...context.sample_summary.totals].sort((a, b) => b.mutations - a.mutations);
    plot(plotElement, [{ type: 'bar', x: sorted.map((item) => item.sample), y: sorted.map((item) => item.mutations), marker: { color: '#3276a8' }, hovertemplate: '%{x}: %{y:,.0f}<extra></extra>' }], { height: 360, xaxis: { tickangle: -55, automargin: true }, yaxis: { title: 'Mutations', rangemode: 'tozero' } });
    content.append(burden);
  }
  if (DATA.job_metadata) {
    const details = document.createElement('details'); details.append(node('summary', '', 'Run metadata'), node('pre', '', DATA.job_metadata)); content.append(details);
  }
  if (DATA.seeds) {
    const details = document.createElement('details'); details.append(node('summary', '', 'Reproducibility seed'));
    const body = node('div'); renderTable(body, DATA.seeds, { filename: 'Seeds.txt' }); details.append(body); content.append(details);
  }
}

function renderSolutions(content, context) {
  content.append(header('All solutions', 'Signature profiles and rank-specific output'));
  rankStrip(content); const solution = currentSolution();
  if (!solution) { empty(content, 'No rank output was found.'); return; }
  renderProfileSection(content, solution.signatures, `Signatures at k=${solution.rank}`);
  const stats = node('section', 'section'); stats.append(node('h3', '', 'Signature statistics'));
  renderTable(stats, solution.signature_stats, { filename: `${context.name}_k${solution.rank}_signature_stats.csv` }); content.append(stats);
  if (solution.warnings.length) content.append(node('div', 'notice', solution.warnings.join(' ')));
}

function selectedFallback(context) {
  const solution = context.solutions.find((item) => item.rank === context.selected_rank);
  return solution ? [{ kind: 'denovo', name: `Selected de novo solution (k=${solution.rank})`, signatures: solution.signatures, activities: solution.activities, sample_stats: solution.sample_stats }] : [];
}

function renderSelected(content, context) {
  content.append(header('Selected solution', `Selected rank ${context.selected_rank ? `k=${context.selected_rank}` : ''}`));
  const bundles = context.selected_bundles.length ? context.selected_bundles : selectedFallback(context);
  if (!bundles.length) { empty(content, 'No selected solution output was found.'); return; }
  state.bundle = Math.min(state.bundle, bundles.length - 1);
  const tabs = node('div', 'bundle-tabs');
  bundles.forEach((bundle, index) => {
    const button = node('button', index === state.bundle ? 'active' : '', bundle.kind === 'cosmic' ? 'COSMIC decomposition' : 'De novo');
    button.type = 'button'; button.title = bundle.name; button.addEventListener('click', () => { state.bundle = index; render(); }); tabs.append(button);
  });
  content.append(tabs); const bundle = bundles[state.bundle];
  renderProfileSection(content, bundle.signatures, bundle.name);
  renderActivitiesBlock(content, bundle.activities, 'Selected activities');
  if (bundle.mapping) { const mapping = node('section', 'section'); mapping.append(node('h3', '', 'De novo to COSMIC mapping')); renderTable(mapping, bundle.mapping, { filename: `${context.name}_cosmic_mapping.csv` }); content.append(mapping); }
}

function renderActivities(content, context) {
  content.append(header('Activities', 'Sample activities for every extracted rank'));
  rankStrip(content); const solution = currentSolution();
  if (!solution) { empty(content, 'No activity matrices were found.'); return; }
  renderActivitiesBlock(content, solution.activities, `Activities at k=${solution.rank}`);
}

function statsPlot(parent, table, title) {
  if (!table || !table.rows.length) return;
  const first = table.columns[0]; const x = table.rows.map((row) => row[0]);
  const numericColumns = table.columns.slice(1).map((name, offset) => ({ name, index: offset + 1 })).filter(({ index }) => table.rows.some((row) => !Number.isNaN(numeric(row[index]))));
  if (!numericColumns.length) return;
  const traces = numericColumns.slice(0, 4).map(({ name, index }, traceIndex) => ({ type: 'scatter', mode: 'markers+lines', name, x, y: table.rows.map((row) => numeric(row[index])), marker: { color: COLORS[traceIndex % COLORS.length] } }));
  const element = node('div', 'plot compact'); parent.append(element);
  plot(element, traces, { height: 360, title: { text: title, x: 0.01 }, xaxis: { title: first, tickangle: -45, automargin: true }, yaxis: { rangemode: 'tozero' }, legend: { orientation: 'h', y: 1.13 } });
}

function renderStatistics(content) {
  content.append(header('Statistics', 'Per-signature, per-sample, and replicate diagnostics'));
  rankStrip(content); const solution = currentSolution();
  if (!solution) { empty(content, 'No statistics were found.'); return; }
  const grid = node('div', 'split');
  const signature = node('section', 'section'); signature.append(node('h3', '', 'Signature statistics')); statsPlot(signature, solution.signature_stats, 'Signature stability and burden'); renderTable(signature, solution.signature_stats, { filename: `k${solution.rank}_signature_stats.csv` });
  const sample = node('section', 'section'); sample.append(node('h3', '', 'Sample fit statistics')); statsPlot(sample, solution.sample_stats, 'Sample fit metrics'); renderTable(sample, solution.sample_stats, { filename: `k${solution.rank}_sample_stats.csv` });
  grid.append(signature, sample); content.append(grid);
  const convergence = node('section', 'section'); convergence.append(node('h3', '', 'NMF replicate diagnostics')); statsPlot(convergence, solution.convergence, 'Convergence diagnostics'); renderTable(convergence, solution.convergence, { filename: `k${solution.rank}_convergence.csv` }); content.append(convergence);
}

function render() {
  const content = $('content'); purgePlots(content); content.replaceChildren();
  const context = currentContext();
  if (state.rank === null || !context.solutions.some((item) => item.rank === state.rank)) state.rank = context.selected_rank || context.solutions[0]?.rank || null;
  document.querySelectorAll('.tabs button').forEach((button) => button.classList.toggle('active', button.dataset.tab === state.tab));
  ({ overview: renderOverview, solutions: renderSolutions, selected: renderSelected, activities: renderActivities, statistics: renderStatistics }[state.tab])(content, context);
  $('contextSummary').textContent = `${context.solutions.length} ranks\n${context.sample_summary.samples} samples\n${context.sample_summary.channels} channels`;
}

function init() {
  $('projectTitle').textContent = DATA.project;
  $('runMeta').textContent = `Extractor ${DATA.extractor_version} · Plotting ${DATA.plotting_version}\n${new Date(DATA.generated_at).toLocaleString()}`;
  const select = $('contextSelect');
  DATA.contexts.forEach((context, index) => { const option = node('option', '', context.name); option.value = String(index); select.append(option); });
  select.addEventListener('change', () => { state.context = Number(select.value); state.rank = null; state.bundle = 0; render(); });
  document.querySelectorAll('.tabs button').forEach((button) => button.addEventListener('click', () => { state.tab = button.dataset.tab; render(); }));
  if (!window.Plotly) { $('content').append(node('div', 'notice', 'Plotly could not be loaded from this dashboard file.')); return; }
  render();
}

init();
