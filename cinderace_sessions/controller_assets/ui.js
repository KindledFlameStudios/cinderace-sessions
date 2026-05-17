/* CinderACE Sessions v2 — Controller UI JavaScript */

let api = window.pywebview ? window.pywebview.api : null;
let allSessions = [];
let currentSession = null;
let currentRange = 'all';
let currentCliFilter = 'all';
let searchQuery = '';
let refreshTimer = null;

// ── Helpers ──────────────────────────────────────────────────────

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function callApi(method, ...args) {
  if (api) return api[method](...args);
  return Promise.resolve(null);
}

function toast(msg, type = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  try { return new Date(dateStr).toLocaleDateString(); }
  catch { return dateStr; }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + 'B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB';
  return (bytes / (1024 * 1024)).toFixed(1) + 'MB';
}

function cliBadgeClass(source) {
  if (source === 'claude-code') return 'claude-code';
  if (source === 'codex') return 'codex';
  if (source === 'gemini-cli') return 'gemini-cli';
  return 'custom';
}

function cliDisplayName(source) {
  if (source === 'claude-code') return 'Claude Code';
  if (source === 'codex') return 'Codex';
  if (source === 'gemini-cli') return 'Gemini CLI';
  return source.replace('custom-', '');
}

// ── Tab Switching ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Wait for pywebview to be ready
  window.addEventListener('pywebviewready', () => {
    api = window.pywebview.api;
    init();
  });

  // Fallback: try after short delay if pywebview already loaded
  setTimeout(() => {
    if (!api && window.pywebview && window.pywebview.api) {
      api = window.pywebview.api;
      init();
    }
  }, 500);

  // Set up tab switching
  $$('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.tab-btn').forEach(b => b.classList.remove('active'));
      $$('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const panel = $(`#tab-${btn.dataset.tab}`);
      if (panel) panel.classList.add('active');
    });
  });

  // Set up filter buttons
  $$('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentRange = btn.dataset.range;
      renderSessionList();
    });
  });

  // Search
  const search = $('#sessionSearch');
  if (search) search.addEventListener('input', (e) => {
    searchQuery = e.target.value.toLowerCase();
    renderSessionList();
  });

  // CLI filter
  const cliFilter = $('#cliFilter');
  if (cliFilter) cliFilter.addEventListener('change', (e) => {
    currentCliFilter = e.target.value;
    renderSessionList();
  });

  // Refresh button
  $('#btnRefresh')?.addEventListener('click', refreshSessions);

  // Export button
  $('#btnExport')?.addEventListener('click', exportSession);

  // Summarize button
  $('#btnSummarize')?.addEventListener('click', () => {
    // Switch to summarizer tab
    $$('.tab-btn').forEach(b => b.classList.remove('active'));
    $$('.tab-panel').forEach(p => p.classList.remove('active'));
    $$('[data-tab="summarizer"]').forEach(b => b.classList.add('active'));
    $('#tab-summarizer')?.classList.add('active');
  });

  // Ingest button
  $('#btnIngest')?.addEventListener('click', ingestSession);

  // Settings
  $('#btnSaveSettings')?.addEventListener('click', saveSettings);
  $('#btnBrowseOutput')?.addEventListener('click', browseOutput);

  // Custom CLI form
  $('#btnAddCli')?.addEventListener('click', () => {
    $('#cliForm').style.display = $('#cliForm').style.display === 'none' ? 'block' : 'none';
  });
  $('#btnSaveCli')?.addEventListener('click', saveCustomCli);
  $('#btnCancelCli')?.addEventListener('click', () => {
    $('#cliForm').style.display = 'none';
  });

  // Summarizer provider toggle
  $('#summarizerProvider')?.addEventListener('change', (e) => {
    $('#customUrlRow').style.display = e.target.value === 'custom' ? 'flex' : 'none';
  });

  // Save template
  $('#btnSaveTemplate')?.addEventListener('click', saveTemplate);
  $('#btnResetTemplate')?.addEventListener('click', resetTemplate);
  $('#btnTestProvider')?.addEventListener('click', testProvider);
});

// ── Initialization ────────────────────────────────────────────────

async function init() {
  await loadSettings();
  await detectCLIs();
  await refreshSessions();
  await checkEmberStatus();
  startAutoRefresh();
}

async function loadSettings() {
  const config = await callApi('get_config');
  if (!config) return;

  const checks = ['includeThinking', 'includeTools', 'autoDetect'];
  checks.forEach(key => {
    const el = document.getElementById(key.charAt(0).toLowerCase() + key.slice(1));
    if (el && typeof config[key] === 'boolean') el.checked = config[key];
  });

  const inputs = ['outputDirectory', 'userLabel', 'assistantLabel'];
  inputs.forEach(key => {
    const el = document.getElementById(key);
    if (el && config[key]) el.value = config[key];
  });

  const selects = { defaultFormat: 'default_export_format', htmlTheme: 'html_theme' };
  Object.entries(selects).forEach(([elId, configKey]) => {
    const el = document.getElementById(elId);
    if (el && config[configKey]) el.value = config[configKey];
  });

  if (config.summarizer_provider) $('#summarizerProvider').value = config.summarizer_provider;
  if (config.summarizer_model) $('#summarizerModel').value = config.summarizer_model;
  if (config.summarizer_api_key) $('#summarizerApiKey').value = config.summarizer_api_key;
  if (config.default_ember_collection) $('#emberCollection').value = config.default_ember_collection;
}

// ── Session Loading ────────────────────────────────────────────────

async function detectCLIs() {
  const clis = await callApi('get_cli_status');
  if (!clis) return;

  // Populate CLI filter
  const filter = $('#cliFilter');
  filter.innerHTML = '<option value="all">All CLIs</option>';
  clis.forEach(cli => {
    if (cli.available || cli.custom) {
      const opt = document.createElement('option');
      opt.value = cli.name;
      opt.textContent = cli.display_name;
      filter.appendChild(opt);
    }
  });

  // Render CLI status tab
  renderCliStatus(clis);
}

async function refreshSessions() {
  const sessions = await callApi('get_sessions');
  if (sessions) {
    allSessions = sessions;
    renderSessionList();
    renderProjects();
  }
  toast('Sessions refreshed', 'success');
}

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(async () => {
    const sessions = await callApi('get_sessions');
    if (sessions) {
      allSessions = sessions;
      renderSessionList();
    }
  }, 30000);
}

// ── Session List Rendering ────────────────────────────────────────

function filterSessions() {
  let filtered = allSessions;

  // Date range filter
  if (currentRange !== 'all') {
    const now = new Date();
    const cutoff = new Date();
    if (currentRange === 'today') cutoff.setHours(0, 0, 0, 0);
    else if (currentRange === 'week') cutoff.setDate(now.getDate() - 7);
    else if (currentRange === 'month') cutoff.setMonth(now.getMonth() - 1);

    filtered = filtered.filter(s => {
      if (!s.date) return true;  // Keep sessions without dates
      const d = new Date(s.date);
      if (isNaN(d.getTime())) return true;  // Keep if date is unparseable
      return d >= cutoff;
    });
  }

  // CLI filter
  if (currentCliFilter !== 'all') {
    filtered = filtered.filter(s => s.cli_source === currentCliFilter);
  }

  // Search filter
  if (searchQuery) {
    filtered = filtered.filter(s =>
      (s.title || '').toLowerCase().includes(searchQuery) ||
      (s.preview || '').toLowerCase().includes(searchQuery) ||
      (s.project || '').toLowerCase().includes(searchQuery)
    );
  }

  return filtered;
}

function renderSessionList() {
  const list = $('#sessionList');
  const empty = $('#sessionsEmpty');
  const sessions = filterSessions();

  if (sessions.length === 0) {
    list.innerHTML = '';
    empty.style.display = 'flex';
    empty.querySelector('.empty-text').textContent = 'No sessions found';
    return;
  }

  empty.style.display = 'none';
  list.innerHTML = sessions.map(s => `
    <div class="session-item ${currentSession && currentSession.filepath === s.filepath ? 'selected' : ''}"
         data-filepath="${encodeURIComponent(s.filepath)}" onclick="selectSession(decodeURIComponent(this.dataset.filepath))">
      <div class="session-title">${escapeHtml(s.title || s.project || 'Untitled')}</div>
      <div class="session-meta">
        <span class="cli-badge ${cliBadgeClass(s.cli_source)}">${cliDisplayName(s.cli_source)}</span>
        <span>${formatDate(s.date)}</span>
        <span>${formatSize(s.file_size)}</span>
        ${s.message_count ? `<span>${s.message_count} msgs</span>` : ''}
      </div>
      <div class="session-preview">${escapeHtml(s.preview || '')}</div>
    </div>
  `).join('');
}

// ── Session Selection & Preview ───────────────────────────────────

async function selectSession(filepath) {
  const detail = await callApi('get_session_detail', filepath);
  if (!detail) { toast('Failed to load session', 'error'); return; }

  currentSession = detail;
  renderSessionList();  // Re-render to update selection

  const previewPane = $('#sessionPreview');
  const empty = $('#previewEmpty');
  const content = $('#previewContent');
  const header = $('#previewHeader');
  const body = $('#previewBody');

  empty.style.display = 'none';
  content.style.display = 'block';
  header.innerHTML = `
    <strong>${escapeHtml(detail.meta.slug || detail.meta.session_id || 'Session')}</strong>
    <span style="color:var(--fg-muted);margin-left:8px">${formatDate(detail.meta.first_date)}</span>
    <span class="cli-badge ${cliBadgeClass(detail.cli_source)}" style="margin-left:8px">${cliDisplayName(detail.cli_source)}</span>
  `;

  // Render a quick markdown-like preview
  let previewText = '';
  const maxTurns = 20;
  const turns = detail.turns.slice(0, maxTurns);
  for (const turn of turns) {
    const role = turn.role === 'user' ? '👤' : '🤖';
    const text = turn.blocks
      .filter(b => b.type === 'text')
      .map(b => b.text || '')
      .join('\n')
      .trim();
    if (text) {
      previewText += `\n${role} ${turn.role === 'user' ? 'User' : 'Assistant'}:\n${text.substring(0, 500)}\n`;
    }
  }
  if (detail.turns.length > maxTurns) {
    previewText += `\n... and ${detail.turns.length - maxTurns} more turns`;
  }

  body.textContent = previewText;
}

// ── Export ──────────────────────────────────────────────────────────

async function exportSession() {
  if (!currentSession) { toast('Select a session first', 'error'); return; }
  const format = $('#exportFormat').value;
  const result = await callApi('export_session', currentSession.filepath, format);
  if (result) {
    toast(`Exported to ${result}`, 'success');
  } else {
    toast('Export failed', 'error');
  }
}

// ── ember-memory Ingest ─────────────────────────────────────────────

async function ingestSession() {
  if (!currentSession) { toast('Select a session first', 'error'); return; }
  const collection = $('#emberCollection')?.value || 'general';
  const result = await callApi('ingest_session', currentSession.filepath, collection);
  if (result) {
    toast('Ingested into ember-memory', 'success');
  } else {
    toast('Ingest failed — is ember-memory running?', 'error');
  }
}

// ── Projects ────────────────────────────────────────────────────────

function renderProjects() {
  const projects = {};
  for (const s of allSessions) {
    const key = s.project || 'unknown';
    if (!projects[key]) projects[key] = { name: key, sessions: [], clis: new Set() };
    projects[key].sessions.push(s);
    projects[key].clis.add(s.cli_source);
  }

  const list = $('#projectList');
  if (!list) return;

  const sorted = Object.values(projects).sort((a, b) => b.sessions[0].mtime - a.sessions[0].mtime);
  list.innerHTML = sorted.map(p => `
    <div class="project-item" data-project="${p.name}" onclick="selectProject('${p.name.replace(/'/g, "\\'")}')">
      <div class="project-name">${escapeHtml(p.name)}</div>
      <div class="project-meta">
        ${Array.from(p.clis).map(c => `<span class="cli-badge ${cliBadgeClass(c)}">${cliDisplayName(c)}</span>`).join(' ')}
        <span>${p.sessions.length} sessions</span>
      </div>
    </div>
  `).join('');
}

function selectProject(projectName) {
  const sessions = allSessions.filter(s => (s.project || 'unknown') === projectName);
  const container = $('#projectSessions');
  if (!container) return;

  container.innerHTML = sessions.map(s => `
    <div class="session-item" data-filepath="${encodeURIComponent(s.filepath)}" onclick="selectSession(decodeURIComponent(this.dataset.filepath))">
      <div class="session-title">${escapeHtml(s.title || 'Untitled')}</div>
      <div class="session-meta">
        <span class="cli-badge ${cliBadgeClass(s.cli_source)}">${cliDisplayName(s.cli_source)}</span>
        <span>${formatDate(s.date)}</span>
        <span>${formatSize(s.file_size)}</span>
      </div>
    </div>
  `).join('');
}

// ── CLI Status ──────────────────────────────────────────────────────

function renderCliStatus(clis) {
  const container = $('#cliStatusList');
  if (!container) return;

  container.innerHTML = clis.map(cli => `
    <div class="cli-status-card">
      <div class="cli-status-header">
        <span class="cli-status-name">
          <span class="cli-badge ${cliBadgeClass(cli.name)}">${cli.display_name}</span>
          ${cli.available
            ? '<span style="color:var(--success)">● Available</span>'
            : '<span style="color:var(--fg-muted)">○ Not found</span>'}
        </span>
        ${cli.custom ? '<span style="color:var(--fg-muted);font-size:11px">Custom</span>' : ''}
      </div>
      <div class="cli-status-meta">
        ${cli.directory ? `<div>Sessions: ${cli.directory}</div>` : ''}
        ${cli.custom ? `<div>Format: ${cli.format} | Color: ${cli.color}</div>` : ''}
      </div>
      <div class="cli-status-actions">
        <button class="action-btn" onclick="rescanCli('${cli.name}')">Rescan</button>
      </div>
    </div>
  `).join('');
}

// ── Settings ────────────────────────────────────────────────────────

async function saveSettings() {
  const settings = {
    output_directory: $('#outputDirectory')?.value || '',
    default_export_format: $('#defaultFormat')?.value || 'md',
    html_theme: $('#htmlTheme')?.value || 'ember',
    include_thinking: $('#includeThinking')?.checked ?? true,
    include_tools: $('#includeTools')?.checked ?? true,
    user_label: $('#userLabel')?.value || 'User',
    assistant_label: $('#assistantLabel')?.value || 'Assistant',
    auto_detect_on_launch: $('#autoDetect')?.checked ?? true,
    summarizer_provider: $('#summarizerProvider')?.value || '',
    summarizer_api_key: $('#summarizerApiKey')?.value || '',
    summarizer_model: $('#summarizerModel')?.value || '',
    summarizer_custom_url: $('#summarizerCustomUrl')?.value || '',
    default_ember_collection: $('#emberCollection')?.value || 'general',
  };

  const ok = await callApi('save_settings', settings);
  if (ok) {
    toast('Settings saved', 'success');
  } else {
    toast('Failed to save settings', 'error');
  }
}

async function browseOutput() {
  const path = await callApi('browse_directory');
  if (path) $('#outputDirectory').value = path;
}

// ── Custom CLI ────────────────────────────────────────────────────

async function saveCustomCli() {
  const name = $('#cliName')?.value;
  const directory = $('#cliDirectory')?.value;
  const format = $('#cliFormat')?.value;
  const color = $('#cliColor')?.value;

  if (!name || !directory) { toast('Name and directory required', 'error'); return; }

  const ok = await callApi('add_custom_cli', name, directory, format, color);
  if (ok) {
    toast('CLI added', 'success');
    $('#cliForm').style.display = 'none';
    await detectCLIs();
    await refreshSessions();
  } else {
    toast('Failed to add CLI (name exists?)', 'error');
  }
}

async function rescanCli(cliName) {
  await callApi('refresh_sessions');
  await detectCLIs();
  await refreshSessions();
  toast('Rescanned', 'success');
}

// ── ember-memory Status ─────────────────────────────────────────────

async function checkEmberStatus() {
  const status = await callApi('get_ember_status');
  const dot = $('#emberDot');
  const label = $('#emberStatusLabel');

  if (!status) {
    dot.className = 'engine-dot off';
    label.textContent = 'Not found';
    return;
  }

  dot.className = 'engine-dot live';
  label.textContent = status;  // 'library' or 'server'
}

// ── Summarizer ──────────────────────────────────────────────────────

async function testProvider() {
  const status = $('#providerStatus');
  status.textContent = 'Testing...';
  const result = await callApi('test_summarizer_connection');
  if (result) {
    status.textContent = '✓ Connected';
    status.style.color = 'var(--success)';
  } else {
    status.textContent = '✗ Failed';
    status.style.color = 'var(--error)';
  }
}

async function saveTemplate() {
  const name = $('#templateSelect')?.value || 'default';
  const content = $('#templateEditor')?.value || '';
  const ok = await callApi('save_template', name, content);
  if (ok) toast('Template saved', 'success');
  else toast('Failed to save template', 'error');
}

async function resetTemplate() {
  const content = await callApi('get_default_template');
  if (content) $('#templateEditor').value = content;
}

// ── Utility ─────────────────────────────────────────────────────────

function escapeHtml(text) {
  if (!text) return '';
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}