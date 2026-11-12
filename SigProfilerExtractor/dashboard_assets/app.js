'use strict';

const DATA = JSON.parse(document.getElementById('dashboardData').textContent);
const $ = (id) => document.getElementById(id);
const state = { context: 0, tab: 'overview', rank: null, bundle: 0 };
const TABS = new Set(['overview', 'solutions', 'selected', 'activities', 'statistics']);
const COLORS = ['#137c79', '#d95d4f', '#b78318', '#3276a8', '#7b5aa6', '#59834b', '#bd6d9c', '#6b747c'];
const SIGNATURE_COLORS = ['#332288', '#117733', '#44aa99', '#88ccee', '#ddcc77', '#cc6677', '#aa4499', '#882255', '#999933', '#661100', '#6699cc', '#6b747c'];
const FIGURE_HELP = {
  solutionSelection: {
    title: 'Solution selection',
    description: 'Compares candidate NMF ranks so the selected solution balances reproducibility across replicates with reconstruction quality.',
    sections: [
      ['Axes and traces', 'The x-axis is the number of signatures (k). The upper panel shows average and minimum silhouette stability; values nearer 1 indicate more reproducible signatures across NMF replicates. The lower panel shows matrix Frobenius error on the left scale and mean cosine distance on the right scale; lower values indicate a closer reconstruction.'],
      ['How to interpret it', 'The upper panel shows stability. The lower panel shows reconstruction metrics on explicitly labelled scales. Look for a stable rank before improvements in reconstruction become small. The selected rank is marked by the vertical reference line and highlighted in the table below. A low error alone is not sufficient if replicate stability is poor.'],
    ],
  },
  sampleBurden: {
    title: 'Sample mutation burden',
    description: 'Shows the total number of mutations in each sample before those mutations are attributed to signatures.',
    sections: [
      ['Axes', 'Each x-axis label is a sample. Bar height is the sum of all mutation-channel counts for that sample, with samples ordered from highest to lowest burden.'],
      ['How to interpret it', 'Use this view to identify low-burden samples and unusually large catalogues that may influence extraction. This is an input-size comparison, not a signature-activity plot.'],
    ],
  },
  signatureProfile: {
    title: 'Mutational signature profile',
    description: 'Shows the mutation-channel probability distribution that defines the selected de novo or reference signature.',
    sections: [
      ['Axes and colors', 'The x-axis contains mutation channels for the active context. The y-axis is the relative contribution of each channel to this signature. Context-specific colors group related mutation classes. Values across a signature normally sum to approximately 1.'],
      ['How to interpret it', 'Compare the shape and peaks of profiles to identify characteristic mutation patterns. Profile height does not show how often a signature occurs in a sample; use the Activities view for that. SBS4608 controls expose strand-bias and heatmap panels supplied by SigProfilerPlotting.'],
    ],
  },
  activities: {
    title: 'Signature activities',
    description: 'Shows how many mutations in each sample are attributed to each extracted or fitted signature.',
    sections: [
      ['Stacked view', 'The x-axis contains samples and each colored segment is one signature. Total bar height is the mutations assigned in that sample. Percentage mode normalizes every sample to 100%, emphasizing composition instead of absolute burden.'],
      ['Heatmap view', 'Columns are samples, rows are signatures, and color intensity represents activity. Log color applies log10(value + 1) to the color scale while hover labels retain the original values, making low activities visible without losing quantitative context.'],
    ],
  },
  signatureStatistics: {
    title: 'Signature statistics',
    description: 'Summarizes rank-specific quality and burden measurements for each extracted signature.',
    sections: [
      ['How to read it', 'The x-axis contains signatures. Select one metric at a time so values with different units are never combined on one scale. Stability nearer 1 indicates more consistent recovery across replicates; total mutations describes signature burden.'],
      ['How to interpret it', 'Hover for exact values and use the table for the complete output. Compare stability together with burden: a weak low-burden signature may be less robust than a stable pattern recovered consistently across replicates.'],
    ],
  },
  sampleStatistics: {
    title: 'Sample fit statistics',
    description: 'Describes how closely the selected rank reconstructs each sample mutation catalogue.',
    sections: [
      ['How to read it', 'The x-axis contains samples. Select one fit metric at a time; the dashed reference line marks the cohort median. Cosine similarity and correlation nearer 1 indicate better agreement, while L1, L2, KL, and cosine distance values are errors or distances where lower is better.'],
      ['How to interpret it', 'Samples that differ substantially from the median may have low mutation burden, unusual biology, or patterns not represented well by the extracted signatures. Use the table for exact values and other metrics.'],
    ],
  },
  convergence: {
    title: 'NMF replicate diagnostics',
    description: 'Compares optimization outcomes across independent NMF replicates for the active rank.',
    sections: [
      ['How to read it', 'The x-axis identifies the replicate. Select one diagnostic at a time; the dashed reference line marks the replicate median. Lower KL divergence or reconstruction error indicates a closer fit, while higher correlation indicates better agreement. Convergence iterations show how long each replicate optimized.'],
      ['How to interpret it', 'Tightly grouped replicate outcomes support a stable solution. Outlying errors, correlations, or iteration counts can indicate a replicate that converged to a different local solution.'],
    ],
  },
};

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

function median(values) {
  if (!values.length) return NaN;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function helpDetails(kind, source, description) {
  const details = FIGURE_HELP[kind];
  return { ...details, description: description || details.description, source };
}

function showFigureHelp(details, trigger) {
  const dialog = $('figureHelpDialog');
  const body = $('figureHelpBody');
  $('figureHelpTitle').textContent = details.title;
  body.replaceChildren(node('p', '', details.description));
  details.sections.forEach(([title, text]) => {
    const section = document.createElement('section');
    section.append(node('h3', '', title), node('p', '', text));
    body.append(section);
  });
  if (details.source) {
    const source = node('div', 'help-source');
    source.append(document.createTextNode('Data source: '), node('code', '', details.source));
    body.append(source);
  }
  dialog._returnFocus = trigger;
  if (typeof dialog.showModal === 'function') dialog.showModal();
  else dialog.setAttribute('open', '');
}

function helpButton(details) {
  const button = node('button', 'help-button', 'i');
  button.type = 'button';
  button.title = 'Explain this figure';
  button.setAttribute('aria-label', `Explain ${details.title}`);
  button.addEventListener('click', () => showFigureHelp(details, button));
  return button;
}

function figureTitle(title, details) {
  const wrap = node('div', 'figure-title');
  wrap.append(node('h3', '', title));
  if (details) wrap.append(helpButton(details));
  return wrap;
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
  const headers = [];
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

  function sortBy(index) {
    ascending = sortIndex === index ? !ascending : true; sortIndex = index;
    rows.sort((left, right) => {
      const a = left.row[index]; const b = right.row[index];
      const an = numeric(a); const bn = numeric(b);
      const compared = Number.isNaN(an) || Number.isNaN(bn)
        ? String(a ?? '').localeCompare(String(b ?? '')) : an - bn;
      return ascending ? compared : -compared;
    });
    headers.forEach((header, headerIndex) => header.setAttribute(
      'aria-sort', headerIndex === index ? (ascending ? 'ascending' : 'descending') : 'none',
    ));
    drawRows();
  }

  table.columns.forEach((column, index) => {
    const th = node('th', '', column);
    th.tabIndex = 0; th.title = `Sort by ${column}`; th.setAttribute('aria-sort', 'none');
    th.addEventListener('click', () => sortBy(index));
    th.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); sortBy(index); }
    });
    headers.push(th);
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
  const context = profile?.context || currentContext().name;
  const description = `Shows the ${context} mutation-channel probability distribution that defines the selected signature.`;
  const heading = figureTitle(title, helpDetails('signatureProfile', profile?.source, description));
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
  if (frob >= 0) traces.push({ type: 'scatter', mode: 'lines+markers', name: 'Frobenius error', x: rank, y: table.rows.map((row) => numeric(row[frob])), xaxis: 'x2', yaxis: 'y2', line: { color: COLORS[2], dash: 'dot' } });
  if (cosine >= 0) traces.push({ type: 'scatter', mode: 'lines+markers', name: 'Mean cosine distance', x: rank, y: table.rows.map((row) => numeric(row[cosine])), xaxis: 'x2', yaxis: 'y3', line: { color: COLORS[3], dash: 'dash' } });
  const element = node('div', 'plot'); parent.append(element);
  const selectedRank = context.selected_rank;
  const reference = Number.isFinite(selectedRank) ? {
    shapes: [{ type: 'line', xref: 'x2', yref: 'paper', x0: selectedRank, x1: selectedRank, y0: 0, y1: 1, line: { color: '#59656e', width: 1.5, dash: 'dot' } }],
    annotations: [{ xref: 'x2', yref: 'paper', x: selectedRank, y: 1.03, text: `Selected k=${selectedRank}`, showarrow: false, font: { size: 11, color: '#43515a' }, bgcolor: '#ffffff' }],
  } : { shapes: [], annotations: [] };
  plot(element, traces, {
    height: 560, hovermode: 'x unified', hoversubplots: 'axis', legend: { orientation: 'h', y: 1.12 },
    margin: { l: 68, r: 70, t: 72, b: 58 },
    xaxis: { domain: [0, 1], anchor: 'y', matches: 'x2', showticklabels: false, dtick: 1, gridcolor: '#edf0f2' },
    yaxis: { domain: [0.57, 1], title: 'Stability', range: [-1, 1.05], gridcolor: '#edf0f2', zerolinecolor: '#aeb8be' },
    xaxis2: { domain: [0, 1], anchor: 'y2', title: 'Number of signatures (k)', dtick: 1, gridcolor: '#edf0f2' },
    yaxis2: { domain: [0, 0.39], title: 'Matrix Frobenius error (%)', rangemode: 'tozero', gridcolor: '#edf0f2' },
    yaxis3: { domain: [0, 0.39], title: 'Mean cosine distance', overlaying: 'y2', side: 'right', rangemode: 'tozero', showgrid: false },
    shapes: reference.shapes, annotations: reference.annotations,
  });
}

function selectedEvidence(context) {
  const table = context.overall_stats;
  if (!table || !table.rows.length || !context.selected_rank) return null;
  const row = table.rows.find((candidate) => numeric(candidate[0]) === context.selected_rank);
  if (!row) return null;
  const metrics = [
    ['Average stability', columnIndex(table, [/Stability \(Avg/i, /avg.*stability/i])],
    ['Minimum stability', columnIndex(table, [/Minimum Stability/i])],
    ['Frobenius error', columnIndex(table, [/Frobenius/i])],
    ['Mean cosine distance', columnIndex(table, [/Mean Cosine Distance/i])],
  ].filter(([, index]) => index >= 0);
  const wrap = node('dl', 'selection-evidence');
  metrics.forEach(([label, index]) => {
    const item = node('div');
    item.append(node('dt', '', label), node('dd', '', format(row[index])));
    wrap.append(item);
  });
  return wrap;
}

function activityValues(table, query, normalized, order) {
  const names = table.columns.slice(1);
  const rows = table.rows.filter((row) => !query || String(row[0]).toLowerCase().includes(query)).map((row) => ({
    row, total: row.slice(1).reduce((sum, value) => sum + (Number(value) || 0), 0),
  }));
  if (order === 'burden') rows.sort((left, right) => right.total - left.total);
  if (order === 'name') rows.sort((left, right) => String(left.row[0]).localeCompare(String(right.row[0])));
  const samples = rows.map(({ row }) => String(row[0]));
  const values = names.map((_, index) => rows.map(({ row }) => Number(row[index + 1]) || 0));
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
  const sectionHead = node('div', 'section-head');
  const heading = figureTitle(title, helpDetails('activities', table?.source));
  sectionHead.append(heading); section.append(sectionHead);
  if (!table || table.columns.length < 2) { empty(section, 'No activity matrix is available for this result.'); parent.append(section); return; }
  const controls = node('div', 'toolbar');
  const search = document.createElement('input'); search.type = 'search'; search.placeholder = 'Filter samples'; search.setAttribute('aria-label', 'Filter samples');
  const order = document.createElement('select'); order.setAttribute('aria-label', 'Sample order'); order.title = 'Sample order';
  [['input', 'Input order'], ['burden', 'Burden: high to low'], ['name', 'Sample name']].forEach(([value, label]) => {
    const option = node('option', '', label); option.value = value; order.append(option);
  });
  const mode = node('div', 'segment');
  const stacked = node('button', 'active', 'Stacked'); const heatmap = node('button', '', 'Heatmap');
  stacked.type = heatmap.type = 'button'; mode.append(stacked, heatmap);
  const normalizeLabel = document.createElement('label'); const normalize = document.createElement('input'); normalize.type = 'checkbox';
  normalizeLabel.append(normalize, document.createTextNode(' Percentage'));
  const logLabel = document.createElement('label'); logLabel.className = 'hidden'; const logColor = document.createElement('input'); logColor.type = 'checkbox';
  logLabel.append(logColor, document.createTextNode(' Log color'));
  controls.append(search, order, mode, normalizeLabel, logLabel); sectionHead.append(controls);
  const plotElement = node('div', 'plot'); section.append(plotElement);
  let view = 'stacked';
  function draw() {
    const data = activityValues(table, search.value.trim().toLowerCase(), normalize.checked, order.value);
    logLabel.classList.toggle('hidden', view !== 'heatmap');
    if (view === 'stacked') {
      const traces = data.names.map((name, index) => ({ type: 'bar', name, x: data.samples, y: data.values[index], marker: { color: SIGNATURE_COLORS[index % SIGNATURE_COLORS.length] }, hovertemplate: `${name}<br>%{x}: %{y:.4g}<extra></extra>` }));
      plot(plotElement, traces, { height: 450, barmode: 'stack', xaxis: { title: 'Sample', tickangle: -55, automargin: true }, yaxis: { title: normalize.checked ? 'Activity (%)' : 'Mutations', rangemode: 'tozero' }, legend: { orientation: 'h', y: 1.13 } });
    } else {
      const displayValues = logColor.checked ? data.values.map((row) => row.map((value) => Math.log10(value + 1))) : data.values;
      const colorTitle = logColor.checked ? `log10(${normalize.checked ? '% + 1' : 'activity + 1'})` : (normalize.checked ? '%' : 'Activity');
      plot(plotElement, [{ type: 'heatmap', x: data.samples, y: data.names, z: displayValues, customdata: data.values, colorscale: 'Cividis', colorbar: { title: colorTitle }, hovertemplate: '%{y}<br>%{x}: %{customdata:.4g}<extra></extra>' }], { height: Math.max(380, 34 * data.names.length), xaxis: { title: 'Sample', tickangle: -55, automargin: true }, yaxis: { title: 'Signature', automargin: true } });
    }
  }
  stacked.addEventListener('click', () => { view = 'stacked'; stacked.classList.add('active'); heatmap.classList.remove('active'); draw(); });
  heatmap.addEventListener('click', () => { view = 'heatmap'; heatmap.classList.add('active'); stacked.classList.remove('active'); draw(); });
  search.addEventListener('input', draw); order.addEventListener('change', draw); normalize.addEventListener('change', draw); logColor.addEventListener('change', draw); draw();
  const tableSection = node('details'); const summary = node('summary', '', 'Activity matrix'); tableSection.append(summary);
  const tableBody = node('div'); renderTable(tableBody, table, { filename: table.source || 'activities.csv' }); tableSection.append(tableBody); section.append(tableSection);
  parent.append(section);
}

function renderOverview(content, context) {
  content.append(header('Overview', `${context.name} extraction and solution selection`));
  const burdens = context.sample_summary.totals.map((item) => item.mutations).filter(Number.isFinite);
  kpis(content, [
    ['Selected rank', context.selected_rank ? `k=${context.selected_rank}` : '—'],
    ['Ranks evaluated', context.solutions.length],
    ['Samples', context.sample_summary.samples],
    ['Mutation channels', context.sample_summary.channels],
    ['Total mutations', burdens.length ? burdens.reduce((sum, value) => sum + value, 0) : '—'],
    ['Median per sample', burdens.length ? median(burdens) : '—'],
  ]);
  const selection = node('section', 'section');
  selection.append(figureTitle('Solution selection', helpDetails('solutionSelection', context.overall_stats?.source)));
  const evidence = selectedEvidence(context); if (evidence) selection.append(evidence);
  overallPlot(selection, context); renderTable(selection, context.overall_stats, { filename: `${context.name}_all_solutions.csv`, selectedRank: context.selected_rank }); content.append(selection);
  if (context.sample_summary.totals.length) {
    const burden = node('section', 'section');
    burden.append(figureTitle('Sample mutation burden', helpDetails('sampleBurden', `${context.source}/Samples.txt`)));
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

function statsPlot(parent, table, options) {
  if (!table || !table.rows.length) return;
  const first = table.columns[0]; const x = table.rows.map((row) => row[0]);
  const numericColumns = table.columns.slice(1).map((name, offset) => ({ name, index: offset + 1 })).filter(({ index }) => table.rows.some((row) => !Number.isNaN(numeric(row[index]))));
  if (!numericColumns.length) return;
  const preferred = numericColumns.find(({ name }) => (options.preferred || []).some((pattern) => pattern.test(name))) || numericColumns[0];
  const controls = node('div', 'plot-tools');
  const metric = document.createElement('select'); metric.setAttribute('aria-label', `${options.label} metric`);
  numericColumns.forEach(({ name, index }) => { const option = node('option', '', name); option.value = String(index); option.selected = index === preferred.index; metric.append(option); });
  controls.append(metric); parent.append(controls);
  const element = node('div', 'plot compact'); parent.append(element);
  function draw() {
    const index = Number(metric.value);
    const name = table.columns[index];
    const values = table.rows.map((row) => numeric(row[index]));
    const finite = values.filter(Number.isFinite);
    const middle = median(finite);
    const isPercentage = /%/.test(name);
    const isBounded = /stability|similarity|correlation/i.test(name) && finite.every((value) => value >= -1 && value <= 1);
    const trace = options.kind === 'bar'
      ? { type: 'bar', x, y: values, marker: { color: options.color }, hovertemplate: `%{x}<br>${name}: %{y:.5g}${isPercentage ? '%' : ''}<extra></extra>` }
      : { type: 'scatter', mode: options.kind === 'line' ? 'lines+markers' : 'markers', x, y: values, marker: { color: options.color, size: 7 }, line: { color: options.color, width: 1.5 }, hovertemplate: `%{x}<br>${name}: %{y:.5g}${isPercentage ? '%' : ''}<extra></extra>` };
    const showMedian = Number.isFinite(middle) && finite.length > 1;
    plot(element, [trace], {
      height: 360,
      margin: { l: 65, r: 25, t: 28, b: 80 },
      xaxis: { title: first, tickangle: -45, automargin: true, nticks: x.length > 12 ? 12 : undefined },
      yaxis: { title: name, ticksuffix: isPercentage ? '%' : '', range: isBounded ? (finite.every((value) => value >= 0) ? [0, 1.05] : [-1.05, 1.05]) : undefined, rangemode: isBounded ? undefined : 'tozero' },
      shapes: showMedian ? [{ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: middle, y1: middle, line: { color: '#6b747c', width: 1.5, dash: 'dash' } }] : [],
      annotations: showMedian ? [{ xref: 'paper', yref: 'y', x: 1, y: middle, text: `Median ${format(middle)}`, showarrow: false, xanchor: 'right', yshift: 10, font: { size: 10, color: '#56616a' }, bgcolor: '#ffffff' }] : [],
    });
  }
  metric.addEventListener('change', draw); draw();
}

function renderStatistics(content) {
  content.append(header('Statistics', 'Per-signature, per-sample, and replicate diagnostics'));
  rankStrip(content); const solution = currentSolution();
  if (!solution) { empty(content, 'No statistics were found.'); return; }
  const grid = node('div', 'split');
  const signature = node('section', 'section');
  signature.append(figureTitle('Signature statistics', helpDetails('signatureStatistics', solution.signature_stats?.source)));
  statsPlot(signature, solution.signature_stats, { label: 'Signature statistics', preferred: [/^Stability$/i], kind: 'bar', color: COLORS[0] });
  renderTable(signature, solution.signature_stats, { filename: `k${solution.rank}_signature_stats.csv` });
  const sample = node('section', 'section');
  sample.append(figureTitle('Sample fit statistics', helpDetails('sampleStatistics', solution.sample_stats?.source)));
  statsPlot(sample, solution.sample_stats, { label: 'Sample fit statistics', preferred: [/Cosine Similarity/i, /Correlation/i], kind: 'markers', color: COLORS[3] });
  renderTable(sample, solution.sample_stats, { filename: `k${solution.rank}_sample_stats.csv` });
  grid.append(signature, sample); content.append(grid);
  const convergence = node('section', 'section');
  convergence.append(figureTitle('NMF replicate diagnostics', helpDetails('convergence', solution.convergence?.source)));
  statsPlot(convergence, solution.convergence, { label: 'NMF replicate diagnostics', preferred: [/KL Divergence/i], kind: 'line', color: COLORS[1] });
  renderTable(convergence, solution.convergence, { filename: `k${solution.rank}_convergence.csv` });
  content.append(convergence);
}

function render() {
  const content = $('content'); purgePlots(content); content.replaceChildren();
  const context = currentContext();
  if (state.rank === null || !context.solutions.some((item) => item.rank === state.rank)) state.rank = context.selected_rank || context.solutions[0]?.rank || null;
  document.querySelectorAll('.tabs button').forEach((button) => button.classList.toggle('active', button.dataset.tab === state.tab));
  ({ overview: renderOverview, solutions: renderSolutions, selected: renderSelected, activities: renderActivities, statistics: renderStatistics }[state.tab])(content, context);
  $('contextSummary').textContent = `${context.solutions.length} ranks\n${context.sample_summary.samples} samples\n${context.sample_summary.channels} channels`;
}

// The panel on the left: drag its edge to resize it, past its narrowest to
// hide it; double-click, the arrow keys or the button beside the title also
// work. Remembered where the browser allows it (a sandboxed frame does not).
const PANEL = { min: 160, max: 440, standard: 220, hideBelow: 110, step: 20 };
const panel = { width: PANEL.standard, hidden: false };

function applyPanel(save) {
  panel.width = Math.round(Math.min(PANEL.max, Math.max(PANEL.min, panel.width)));
  document.documentElement.style.setProperty('--sidebar-w', `${panel.width}px`);
  document.body.classList.toggle('sidebar-hidden', panel.hidden);
  const label = panel.hidden ? 'Show the panel' : 'Hide the panel';
  const toggle = $('sidebarToggle');
  toggle.setAttribute('aria-expanded', String(!panel.hidden));
  toggle.title = label;
  toggle.setAttribute('aria-label', label);
  const handle = $('sidebarSplitter');
  handle.setAttribute('aria-valuenow', String(panel.hidden ? 0 : panel.width));
  handle.setAttribute('aria-valuetext', panel.hidden ? 'hidden' : `${panel.width} pixels`);
  if (save) {
    try { window.localStorage.setItem('spe-dashboard-panel', JSON.stringify(panel)); } catch (error) { /* not allowed here */ }
    // Plotly's responsive figures follow the window: tell them the room changed.
    window.dispatchEvent(new Event('resize'));
  }
}

function initPanel() {
  try {
    const saved = JSON.parse(window.localStorage.getItem('spe-dashboard-panel') || 'null');
    if (saved && Number.isFinite(saved.width)) { panel.width = saved.width; panel.hidden = Boolean(saved.hidden); }
  } catch (error) { /* nothing saved, or not allowed */ }
  applyPanel(false);
  const handle = $('sidebarSplitter');
  $('sidebarToggle').addEventListener('click', () => { panel.hidden = !panel.hidden; applyPanel(true); });
  handle.addEventListener('dblclick', () => { panel.hidden = !panel.hidden; applyPanel(true); });
  handle.addEventListener('keydown', (event) => {
    const moves = { ArrowLeft: -PANEL.step, ArrowRight: PANEL.step };
    if (event.key in moves) {
      event.preventDefault();
      if (panel.hidden && event.key === 'ArrowRight') { panel.hidden = false; panel.width = PANEL.min; }
      else if (!panel.hidden && event.key === 'ArrowLeft' && panel.width <= PANEL.min) panel.hidden = true;
      else panel.width += moves[event.key];
    } else if (event.key === 'Home') { event.preventDefault(); panel.hidden = true; }
    else if (event.key === 'End') { event.preventDefault(); panel.hidden = false; panel.width = PANEL.max; }
    else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); panel.hidden = !panel.hidden; }
    else return;
    applyPanel(true);
  });
  handle.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    document.body.classList.add('resizing');
    const left = document.querySelector('.workspace').getBoundingClientRect().left;
    const move = (moveEvent) => {
      const width = moveEvent.clientX - left;
      panel.hidden = width < PANEL.hideBelow;
      if (!panel.hidden) panel.width = width;
      applyPanel(false);
    };
    const up = (upEvent) => {
      handle.releasePointerCapture(upEvent.pointerId);
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', up);
      handle.removeEventListener('pointercancel', up);
      document.body.classList.remove('resizing');
      applyPanel(true);
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', up);
    handle.addEventListener('pointercancel', up);
  });
}

function init() {
  initPanel();
  const initialTab = window.location.hash.slice(1);
  if (TABS.has(initialTab)) state.tab = initialTab;
  $('projectTitle').textContent = DATA.project;
  $('runMeta').textContent = `Extractor ${DATA.extractor_version} · Plotting ${DATA.plotting_version}\n${new Date(DATA.generated_at).toLocaleString()}`;
  const select = $('contextSelect');
  const helpDialog = $('figureHelpDialog');
  $('figureHelpClose').addEventListener('click', () => helpDialog.close());
  helpDialog.addEventListener('click', (event) => { if (event.target === helpDialog) helpDialog.close(); });
  helpDialog.addEventListener('close', () => helpDialog._returnFocus?.focus());
  DATA.contexts.forEach((context, index) => { const option = node('option', '', context.name); option.value = String(index); select.append(option); });
  select.addEventListener('change', () => { state.context = Number(select.value); state.rank = null; state.bundle = 0; render(); });
  document.querySelectorAll('.tabs button').forEach((button) => button.addEventListener('click', () => {
    const next = button.dataset.tab;
    if (window.location.hash === `#${next}`) { state.tab = next; render(); }
    else window.location.hash = next;
  }));
  window.addEventListener('hashchange', () => {
    const next = window.location.hash.slice(1);
    if (TABS.has(next)) { state.tab = next; render(); }
  });
  if (!window.Plotly) { $('content').append(node('div', 'notice', 'Plotly could not be loaded from this dashboard file.')); return; }
  render();
}

init();
