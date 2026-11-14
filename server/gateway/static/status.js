'use strict';

// What this SLURM job was given and how much of it is in use. Two places use
// it: the Workbench page (#spe-gw, a pill that opens a panel) and the upload
// page (#job-card, the same details as a card).
(() => {
  // Live while someone is looking (the panel open, or the upload page's
  // card); otherwise just often enough to keep the pill current. The server
  // samples every 2 s whatever this does, so the trends are always there.
  const POLL_FAST_MS = 3000;
  const POLL_SLOW_MS = 15000;
  const SVG = 'http://www.w3.org/2000/svg';

  function el(tag, cls, ...children) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    for (const child of children) node.append(child);
    return node;
  }

  function gb(bytes) {
    if (bytes == null) return '?';
    const value = bytes / 2 ** 30;
    return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} GB`;
  }

  function duration(seconds) {
    if (seconds == null) return null;
    const d = Math.floor(seconds / 86400), h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d) return `${d}d ${h}h`;
    if (h) return `${h}h ${m}m`;
    return `${m}m`;
  }

  function bar(percent, warn) {
    const fill = el('span');
    const p = Math.max(0, Math.min(100, percent || 0));
    fill.style.width = `${p}%`;
    if (warn && p >= 90) fill.className = 'high';
    return el('div', 'spe-bar', fill);
  }

  // A trend of the last samples, scaled to `max` (100 for a percentage, the
  // allocation for memory), so a full-height line means "all of it".
  function spark(values, max, label) {
    const points = (values || []).map((v, i) => [i, v]).filter(([, v]) => v != null);
    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('class', 'spe-spark');
    svg.setAttribute('viewBox', '0 0 100 24');
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', label);
    const n = Math.max(1, values.length - 1);
    const xy = points.map(([i, v]) => [
      (100 * i) / n, 23 - 22 * Math.max(0, Math.min(1, max ? v / max : 0))]);
    if (xy.length > 1) {
      const line = xy.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
      const area = document.createElementNS(SVG, 'polygon');
      area.setAttribute('class', 'area');
      area.setAttribute('points', `${xy[0][0].toFixed(2)},24 ${line} ${xy[xy.length - 1][0].toFixed(2)},24`);
      const stroke = document.createElementNS(SVG, 'polyline');
      stroke.setAttribute('class', 'line');
      stroke.setAttribute('points', line);
      svg.append(area, stroke);
    }
    return svg;
  }

  // One measured value: its text, then a trend once there are samples to
  // draw, else a bar of the current share. `warn` turns it red at 90% and
  // above: right for memory (nearly full), wrong for load (a busy GPU
  // during a run is the point).
  function gauge(text, percent, values, max, label, warn) {
    const box = el('div', 'spe-gauge', el('div', 'spe-reading', text));
    if (values && values.filter((v) => v != null).length > 1) {
      const trend = spark(values, max, label);
      if (warn && percent >= 90) trend.classList.add('high');
      box.append(trend);
    } else if (percent != null) {
      box.append(bar(percent, warn));
    }
    return box;
  }

  function row(label, ...content) {
    return [el('div', 'spe-label', label), el('div', 'spe-value', ...content)];
  }

  function details(r) {
    const h = r.history || { cpu: [], mem: [], gpus: {} };
    const minutes = Math.round(((h.t || []).length * (h.interval_seconds || 2)) / 60);
    const grid = el('div', 'spe-grid');
    const left = duration(r.time_left_seconds);
    // A SLURM job, or the app running directly on a server or in a container.
    grid.append(...(r.job_id
      ? row('Job', `${r.job_id} on ${r.node}${left ? ` · ${left} left` : ''}`)
      : row('Server', r.node)));
    const where = r.job_id ? 'node' : 'server';

    const c = r.cpus;
    grid.append(...row('CPUs',
      el('div', null, c.allocated < c.node_total
        ? `${c.allocated} for this ${r.job_id ? 'job' : 'app'}, of ${c.node_total} on the ${where}`
        : `${c.allocated} on the ${where}`),
      gauge(c.busy_percent != null ? `${Math.round(c.busy_percent)}% busy` : 'load unknown',
        c.busy_percent, h.cpu, 100, 'CPU load, recent minutes')));

    const m = r.memory;
    const memPercent = m.allocated_bytes ? (100 * m.used_bytes) / m.allocated_bytes : null;
    grid.append(...row('Memory', gauge(m.allocated_bytes
      ? `${gb(m.used_bytes)} used of ${gb(m.allocated_bytes)} for this ${r.job_id ? 'job' : 'app'}`
      : `${gb(m.used_bytes)} used (the ${where} has ${gb(m.node_total_bytes)})`,
    memPercent, h.mem, m.allocated_bytes || m.node_total_bytes, 'Job memory, recent minutes', true)));

    if (r.gpus.length) {
      for (const g of r.gpus) {
        const gh = (h.gpus || {})[String(g.index)] || {};
        const gpuMemPercent = (100 * g.memory_used_bytes) / g.memory_total_bytes;
        grid.append(...row(`GPU ${g.index}`,
          el('div', null, g.name),
          gauge(`${g.busy_percent}% busy`, g.busy_percent, gh.busy, 100, `GPU ${g.index} load, recent minutes`),
          gauge(`${gb(g.memory_used_bytes)} of ${gb(g.memory_total_bytes)} memory`, gpuMemPercent,
            gh.mem, g.memory_total_bytes, `GPU ${g.index} memory, recent minutes`, true)));
      }
    } else {
      grid.append(...row('GPU', `None ${r.job_id ? 'in this job' : 'available'}: runs use the CPUs`));
    }

    const n = r.node_usage;
    if (n) {
      grid.append(...row('Whole node',
        `All jobs hold ${n.cpus_allocated} of ${n.cpus_total} CPUs` +
        (n.gpus_total ? ` and ${n.gpus_allocated} of ${n.gpus_total} GPUs` : '')));
    }
    const notes = [];
    if (minutes >= 1) {
      notes.push(el('p', 'spe-note', `Graphs show the last ${minutes} min, sampled every ` +
        `${h.interval_seconds || 2} s; a full-height line means all of it is in use.`));
    }
    notes.push(el('p', 'spe-note',
      `Runs use at most these ${c.allocated} CPUs. To run several at once, ` +
      'lower the CPUs in each run’s Advanced settings so they share them.'));
    return [grid, ...notes];
  }

  function plural(n, word) { return `${n} ${word}${n === 1 ? '' : 's'}`; }

  // The GPU count with live numbers for the pill: "1 GPU (0% busy, 0.0/80 GB)",
  // or for several, their average load and total memory.
  function gpuLive(r) {
    const g = r.gpus;
    if (!g.length) return null;
    const busy = Math.round(g.reduce((s, x) => s + x.busy_percent, 0) / g.length);
    const used = g.reduce((s, x) => s + x.memory_used_bytes, 0) / 2 ** 30;
    const total = g.reduce((s, x) => s + x.memory_total_bytes, 0) / 2 ** 30;
    const memory = `${used < 10 ? used.toFixed(1) : Math.round(used)}/${Math.round(total)} GB`;
    return `${plural(g.length, 'GPU')} (${busy}% busy, ${memory})`;
  }

  function summary(r) {
    const parts = [r.node, plural(r.cpus.allocated, 'CPU'), gpuLive(r) || 'no GPU'];
    const left = duration(r.time_left_seconds);
    if (left) parts.push(`${left} left`);
    return parts.join(' · ');
  }

  // ------------------------------------------------------------ limits

  // The Workbench's Computer fields (Advanced settings) have no upper bound.
  // Cap them at this job's CPUs: the max attribute for the spinner, and a
  // clamp on change, since the page reads the values with script rather
  // than submitting a form. The server refuses anything above it as well.
  const limitNotes = {};

  function capField(id, limit, label) {
    const input = document.getElementById(id);
    if (!input) return;
    input.max = String(limit);
    input.placeholder = `all ${limit}`;
    let note = limitNotes[id];
    if (!note) {
      note = limitNotes[id] = el('p', 'hint spe-limit');
      input.after(note);
      input.addEventListener('change', () => {
        const value = Number(input.value);
        const max = Number(input.max);
        if (input.value.trim() && value > max) {
          input.value = String(max);
          input.dispatchEvent(new Event('input', { bubbles: true }));
          note.textContent = `${label} can be at most ${max}, the CPUs this job has. Set to ${max}.`;
          note.classList.add('warn');
        } else {
          note.textContent = `At most ${max}: the CPUs this job has.`;
          note.classList.remove('warn');
        }
      });
    }
    if (!note.classList.contains('warn')) note.textContent = `At most ${limit}: the CPUs this job has.`;
  }

  function applyLimits(r) {
    capField('cpu', r.cpus.allocated, 'CPUs for extraction');
    capField('assignCpu', r.cpus.allocated, 'CPUs for assignment');
    // The Workbench numbers the extraction hint only ("Blank uses all N of them").
    const assignHint = document.getElementById('assignCpu')?.closest('label')?.querySelector('.hint');
    if (assignHint) assignHint.textContent = `Blank uses all ${r.cpus.allocated} of them.`;
    const gpuText = document.getElementById('gpuText');
    const gpuBox = document.getElementById('gpu');
    if (gpuText && gpuBox && !gpuBox.disabled && r.gpus.length) {
      const names = r.gpus.map((g) => `${g.name}, ${gb(g.memory_total_bytes)}`).join('; ');
      gpuText.textContent = `Use the GPU (CUDA): ${names}`;
    }
  }

  // ------------------------------------------------------------ widget

  // On the Workbench page, the top bar's "ready" pill (#envPill, which the
  // Workbench sets to "ready" or "ready · GPU" once it has loaded) gains this
  // job's CPU and GPU counts and opens the details panel just below it. If a
  // Workbench version drops that pill, a pill of our own beside Upload &
  // download does the same.
  const widget = document.getElementById('spe-gw');
  const envPill = document.getElementById('envPill');
  let trigger = null, panel = null, latest = null, written = null;
  let ready = false, cudaUsable = false;

  function setOpen(open) {
    panel.hidden = !open;
    trigger.setAttribute('aria-expanded', String(open));
    if (open && trigger === envPill) {
      panel.style.top = `${Math.round(trigger.getBoundingClientRect().bottom + 8)}px`;
    }
    if (open) refresh();
  }

  // Takes over the Workbench's text once it says "ready", remembering what it
  // said about CUDA ("ready · GPU" means torch can use the GPU), and then
  // shows the live numbers: "ready · 32 CPUs · GPU 63% · 14/80 GB".
  function labelEnvPill() {
    if (trigger !== envPill) return;
    const own = envPill.textContent;
    if (own !== written) {
      if (!own.startsWith('ready')) { ready = false; return; }
      ready = true;
      cudaUsable = own.includes('GPU');
    }
    if (!ready || !latest) return;
    const n = latest.gpus.length;
    const gpu = !n ? 'no GPU' : cudaUsable ? gpuLive(latest) : `${plural(n, 'GPU')} (not usable)`;
    const text = `ready · ${plural(latest.cpus.allocated, 'CPU')} · ${gpu}`;
    if (text !== envPill.textContent) {
      written = text;
      envPill.textContent = text;
    }
  }

  if (widget) {
    panel = el('div', 'spe-panel');
    panel.id = 'spe-gw-panel';
    panel.hidden = true;
    if (envPill) {
      trigger = envPill;
      trigger.setAttribute('role', 'button');
      trigger.tabIndex = 0;
      trigger.classList.add('spe-trigger');
      panel.classList.add('spe-top');
      document.body.append(panel);
      new MutationObserver(labelEnvPill).observe(envPill, { childList: true, characterData: true, subtree: true });
    } else {
      trigger = el('button', 'spe-pill', 'Job resources');
      trigger.type = 'button';
      const buttons = el('div', 'spe-row', trigger);
      buttons.append(...widget.children);
      widget.replaceChildren(panel, buttons);
    }
    trigger.title = 'CPUs, memory and GPUs of this job';
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-controls', panel.id);
    trigger.addEventListener('click', () => setOpen(panel.hidden));
    trigger.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen(panel.hidden); }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !panel.hidden) { setOpen(false); trigger.focus(); }
    });
    document.addEventListener('click', (e) => {
      if (!panel.hidden && !panel.contains(e.target) && !trigger.contains(e.target)) setOpen(false);
    });
  }
  const card = document.getElementById('job-card');

  async function load() {
    let r;
    try {
      const response = await fetch('/gateway/api/resources', { cache: 'no-store' });
      r = await response.json();
      if (!r.ok) throw new Error(r.error || `HTTP ${response.status}`);
    } catch (err) {
      if (card) card.replaceChildren(el('p', 'spe-note', `Could not read the job’s resources: ${err.message}`));
      return;
    }
    latest = r;
    if (widget) {
      applyLimits(r);
      if (trigger === envPill) labelEnvPill(); else trigger.textContent = summary(r);
      panel.replaceChildren(el('h2', 'spe-title', r.job_id ? 'This job' : 'This server'), ...details(r));
    }
    if (card) card.replaceChildren(...details(r));
  }

  // Reads now, then again after the fast or slow delay; opening the panel
  // calls this too, so it fills at once and then stays live.
  let timer = null;
  function refresh() {
    clearTimeout(timer);
    load().finally(() => {
      clearTimeout(timer);
      const watching = card || (panel && !panel.hidden);
      timer = setTimeout(refresh, watching ? POLL_FAST_MS : POLL_SLOW_MS);
    });
  }

  refresh();
})();
