'use strict';

const $ = (id) => document.getElementById(id);

function stamp() {
  const d = new Date(), p = (n) => String(n).padStart(2, '0');
  return `upload-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function size(bytes) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i += 1; }
  return `${bytes.toFixed(i ? 1 : 0)} ${units[i]}`;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v; else node.setAttribute(k, v);
  }
  for (const child of children) node.append(child);
  return node;
}

// navigator.clipboard needs https or localhost; this page is plain http on a
// server, so fall back to selecting the text and execCommand('copy').
async function copy(text, button) {
  let ok = false;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text); ok = true;
    }
  } catch (_) { /* fall through */ }
  if (!ok) {
    const area = el('textarea');
    area.value = text; area.style.position = 'fixed'; area.style.opacity = '0';
    document.body.append(area); area.select();
    try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
    area.remove();
  }
  const label = button.textContent;
  button.textContent = ok ? 'Copied' : 'Select and copy it';
  setTimeout(() => { button.textContent = label; }, 1500);
}

function pathRow(label, path) {
  const input = el('input', { type: 'text', readonly: '' });
  input.value = path;
  input.addEventListener('focus', () => input.select());
  const button = el('button', { type: 'button', class: 'secondary' }, 'Copy');
  button.addEventListener('click', () => copy(path, button));
  return el('div', {}, el('div', { class: 'meta' }, label), el('div', { class: 'pathrow' }, input, button));
}

function zipLink(path, text = 'Download .zip') {
  return el('a', { class: 'button', href: `/gateway/api/zip?path=${encodeURIComponent(path)}` }, text);
}

// ------------------------------------------------------------------ upload

function uploadOne(folder, relative, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const query = `folder=${encodeURIComponent(folder)}&path=${encodeURIComponent(relative)}`;
    xhr.open('PUT', `/gateway/api/upload?${query}`);
    xhr.upload.onprogress = (e) => onProgress(e.loaded);
    xhr.onload = () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch (_) { /* not JSON */ }
      if (xhr.status === 200 && body.ok) resolve(body);
      else reject(new Error(body.error || `HTTP ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error('network error'));
    xhr.send(file);
  });
}

let busy = false;

async function upload(files) {
  if (busy || !files.length) return;
  const folder = $('folder').value.trim();
  if (!/^[A-Za-z0-9._-]{1,100}$/.test(folder) || folder === '.' || folder === '..') {
    showDone([el('p', { class: 'bad' }, "Use only letters, digits, '.', '_' and '-' in the folder name.")]);
    return;
  }
  busy = true;
  $('done').hidden = true;
  $('progress').hidden = false;
  const total = files.reduce((sum, f) => sum + f.size, 0) || 1;
  let sent = 0, last = null;
  try {
    for (const [i, file] of files.entries()) {
      // A picked folder gives "top/sub/file"; keep its inner layout.
      const relative = file.webkitRelativePath
        ? file.webkitRelativePath.split('/').slice(1).join('/') || file.name
        : file.name;
      $('progress-text').textContent = `${i + 1} of ${files.length}: ${relative}`;
      last = await uploadOne(folder, relative, file, (loaded) => {
        $('bar').style.width = `${(100 * (sent + loaded)) / total}%`;
      });
      sent += file.size;
    }
    $('bar').style.width = '100%';
    const parts = [el('p', {}, `Uploaded ${files.length} file${files.length > 1 ? 's' : ''} (${size(sent)}).`)];
    if (files.length === 1) parts.push(pathRow('Path of the file (for a matrix or segmentation file):', last.path));
    parts.push(pathRow('Path of the folder (for VCF or BEDPE files):', last.folder));
    showDone(parts);
    $('folder').value = stamp();
  } catch (err) {
    showDone([el('p', { class: 'bad' }, `Upload failed: ${err.message}`)]);
  } finally {
    busy = false;
    $('progress').hidden = true;
    $('bar').style.width = '0';
    refresh();
  }
}

function showDone(nodes) {
  $('done').replaceChildren(...nodes);
  $('done').hidden = false;
}

// ------------------------------------------------------------------ lists

async function refresh() {
  let data;
  try {
    const r = await fetch('/gateway/api/list', { cache: 'no-store' });
    data = await r.json();
    if (!data.ok) throw new Error(data.error || `HTTP ${r.status}`);
  } catch (err) {
    $('runs').replaceChildren(el('p', { class: 'empty' }, `Could not load: ${err.message}`));
    return;
  }

  $('runs').replaceChildren(...(data.runs.length ? data.runs.map((run) => el('div', { class: 'item' },
    el('div', { class: 'what' },
      el('div', { class: 'name' }, run.name || 'run', el('span', { class: `status ${run.status}` }, run.status)),
      el('div', { class: 'meta' }, run.output_dir)),
    el('div', { class: 'actions' }, run.exists ? zipLink(run.output_dir) : el('span', { class: 'meta' }, 'no output yet')),
  )) : [el('p', { class: 'empty' }, 'No runs yet. Start one from the Workbench’s New run tab.')]));

  $('uploads').replaceChildren(...(data.uploads.length ? data.uploads.map((up) => {
    const copyBtn = el('button', { type: 'button', class: 'secondary' }, 'Copy path');
    const path = up.single_file || up.path;
    copyBtn.addEventListener('click', () => copy(path, copyBtn));
    return el('div', { class: 'item' },
      el('div', { class: 'what' },
        el('div', { class: 'name' }, up.name),
        el('div', { class: 'meta' }, `${up.files} file${up.files === 1 ? '' : 's'}, ${size(up.bytes)} · ${path}`)),
      el('div', { class: 'actions' }, copyBtn, zipLink(up.path)));
  }) : [el('p', { class: 'empty' }, `Nothing uploaded yet. Uploads go to ${data.uploads_root}.`)]));
}

// ------------------------------------------------------------------ wiring

document.addEventListener('DOMContentLoaded', () => {
  $('folder').value = stamp();
  for (const id of ['pick-files', 'pick-folder']) {
    $(id).addEventListener('change', (e) => { upload([...e.target.files]); e.target.value = ''; });
  }
  const drop = $('drop');
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault(); drop.classList.remove('over');
    upload([...e.dataTransfer.files].filter((f) => f.size || f.type));
  });
  $('any').addEventListener('submit', (e) => {
    e.preventDefault();
    const path = $('any-path').value.trim();
    if (path) window.location.href = `/gateway/api/zip?path=${encodeURIComponent(path)}`;
  });
  refresh();
  setInterval(refresh, 10000);
});
