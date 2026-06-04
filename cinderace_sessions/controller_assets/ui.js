/* CinderACE Sessions v2 — Controller UI JavaScript */

let api = window.pywebview ? window.pywebview.api : null;
let allSessions = [];
let currentSession = null;
let currentRange = 'all';
let currentCliFilter = 'all';
let searchQuery = '';
let refreshTimer = null;
let savedModelValue = '';  // Restore after models are fetched
let groupedByProject = true;  // Default to project-grouped view

// ── Helpers ──────────────────────────────────────────────────────

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function callApi(method, ...args) {
  if (api) {
    try {
      const result = api[method](...args);
      // Handle both sync returns and promise returns
      if (result && typeof result.catch === 'function') {
        return result.catch(err => {
          console.error(`API error: ${method}`, err);
          toast(`Error: ${method} — ${err.message || err}`, 'error');
          return null;
        });
      }
      return result;
    } catch (err) {
      console.error(`API error: ${method}`, err);
      toast(`Error: ${method} — ${err.message || err}`, 'error');
      return Promise.resolve(null);
    }
  }
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
  if (source.startsWith('forge-')) return 'fire-forge';
  return 'custom';
}

function cliDisplayName(source) {
  if (source === 'claude-code') return 'Claude Code';
  if (source === 'codex') return 'Codex';
  if (source === 'gemini-cli') return 'Gemini CLI';
  if (source === 'forge-seren') return 'Fire Forge (Seren)';
  if (source === 'forge-kael') return 'Fire Forge (Kael)';
  if (source === 'forge-solace') return 'Fire Forge (Solace)';
  if (source.startsWith('forge-')) return 'Fire Forge';
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

      // Load data when switching to summarizer tab
      if (btn.dataset.tab === 'summarizer') {
        initSummarizerTab();
      }
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

  // Group toggle
  const btnToggleGroup = $('#btnToggleGroup');
  if (btnToggleGroup) {
    btnToggleGroup.classList.toggle('active', groupedByProject);
    btnToggleGroup.addEventListener('click', () => {
      groupedByProject = !groupedByProject;
      btnToggleGroup.classList.toggle('active', groupedByProject);
      renderSessionList();
    });
  }

  // Refresh button
  $('#btnRefresh')?.addEventListener('click', refreshSessions);

  // Export button
  $('#btnExport')?.addEventListener('click', exportSession);

  // Summarize button — switch to summarizer tab and pre-select session
  $('#btnSummarize')?.addEventListener('click', () => {
    // Switch to summarizer tab
    $$('.tab-btn').forEach(b => b.classList.remove('active'));
    $$('.tab-panel').forEach(p => p.classList.remove('active'));
    $$('[data-tab="summarizer"]').forEach(b => b.classList.add('active'));
    $('#tab-summarizer')?.classList.add('active');
    populateSummarizeDropdown();
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
    const provider = e.target.value;
    $('#customUrlRow').style.display = provider === 'custom' ? 'flex' : 'none';
    // Hide API key row for Ollama
    const apiKeyRow = $('#summarizerApiKey')?.closest('.form-row');
    if (apiKeyRow) apiKeyRow.style.display = provider === 'ollama' ? 'none' : 'flex';
    // Fetch models for new provider
    fetchModels(provider);
  });

  // Template management
  $('#templateSelect')?.addEventListener('change', loadTemplateContent);
  $('#btnSaveTemplate')?.addEventListener('click', saveTemplate);
  $('#btnResetTemplate')?.addEventListener('click', resetTemplate);
  $('#btnNewTemplate')?.addEventListener('click', newTemplate);
  $('#btnDeleteTemplate')?.addEventListener('click', deleteTemplate);

  // Summarize controls
  $('#btnTestProvider')?.addEventListener('click', testProvider);
  $('#btnRunSummarize')?.addEventListener('click', summarizeCurrentSession);
  $('#btnCopySummary')?.addEventListener('click', copySummary);
  $('#btnExportSummary')?.addEventListener('click', exportSummary);
  $('#btnIngestSummary')?.addEventListener('click', ingestSummary);
});

// ── Initialization ────────────────────────────────────────────────

async function init() {
  await loadSettings();
  await detectCLIs();
  await refreshSessions();
  await checkEmberStatus();
  // Fetch models for current provider (applies savedModelValue after dropdown is populated)
  const provider = $('#summarizerProvider')?.value || 'openai';
  await fetchModels(provider);
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

  if (config.summarizer_provider) {
    $('#summarizerProvider').value = config.summarizer_provider;
    // Trigger visibility toggles for the new provider
    const provider = config.summarizer_provider;
    $('#customUrlRow').style.display = provider === 'custom' ? 'flex' : 'none';
    const apiKeyRow = $('#summarizerApiKey')?.closest('.form-row');
    if (apiKeyRow) apiKeyRow.style.display = provider === 'ollama' ? 'none' : 'flex';
    if (provider === 'custom') {
      $('#summarizerModel').style.display = 'none';
      const manual = $('#summarizerModelManual');
      if (manual) manual.style.display = '';
    }
  }
  if (config.has_api_key) $('#summarizerApiKey').value = '••••••••';
  // Set model value after fetching models (dropdown may not be populated yet)
  if (config.summarizer_model) savedModelValue = config.summarizer_model;
  if (config.default_ember_collection) $('#emberCollection').value = config.default_ember_collection;
  if (config.ember_memory_url) $('#emberMemoryUrl').value = config.ember_memory_url;
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
  // Render Custom CLIs in Settings
  renderCustomClis(clis);
}

async function refreshSessions() {
  const sessions = await callApi('get_sessions');
  if (sessions) {
    allSessions = sessions;
    renderSessionList();
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
    // Forge detector produces sessions with cli_source like "forge-seren", "forge-kael", "forge-solace"
    // but the detector name is "fire-forge". Match by prefix for consistency.
    if (currentCliFilter === 'fire-forge') {
      filtered = filtered.filter(s => s.cli_source.startsWith('forge-'));
    } else {
      filtered = filtered.filter(s => s.cli_source === currentCliFilter);
    }
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
  const sessions = filterSessions();

  if (sessions.length === 0) {
    list.innerHTML = `
      <div class="empty-state" id="sessionsEmpty">
        <div class="empty-icon">📂</div>
        <div class="empty-text">No sessions found</div>
      </div>`;
    return;
  }

  if (groupedByProject) {
    renderGroupedView(list, sessions);
  } else {
    renderFlatView(list, sessions);
  }
}

function renderFlatView(list, sessions) {
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

function renderGroupedView(list, sessions) {
  // Group sessions by project
  const groups = {};
  for (const s of sessions) {
    const key = s.project || 'unknown';
    if (!groups[key]) groups[key] = { name: key, sessions: [], clis: new Set() };
    groups[key].sessions.push(s);
    groups[key].clis.add(s.cli_source);
  }

  // Sort groups by most recent session
  const sorted = Object.values(groups).sort(
    (a, b) => b.sessions[0].mtime - a.sessions[0].mtime
  );

  let html = '';
  for (const group of sorted) {
    const isExpanded = expandedGroups.has(group.name);
    const cliBadges = Array.from(group.clis)
      .map(c => `<span class="cli-badge ${cliBadgeClass(c)}">${cliDisplayName(c)}</span>`).join(' ');

    html += `
      <div class="project-group-header ${isExpanded ? 'expanded' : ''}" data-project="${escapeHtml(group.name)}" onclick="toggleProjectGroup(this, this.dataset.project)">
        <span class="project-group-chevron">▶</span>
        <span class="project-group-name">${escapeHtml(group.name)}</span>
        <span class="project-group-count">${group.sessions.length} session${group.sessions.length !== 1 ? 's' : ''}</span>
        ${cliBadges}
      </div>
      <div class="project-group-sessions ${isExpanded ? 'expanded' : ''}" data-project-sessions="${escapeHtml(group.name)}">
        ${group.sessions.map(s => `
          <div class="session-item ${currentSession && currentSession.filepath === s.filepath ? 'selected' : ''}"
               data-filepath="${encodeURIComponent(s.filepath)}" onclick="selectSession(decodeURIComponent(this.dataset.filepath))" style="padding-left:24px">
            <div class="session-title">${escapeHtml(s.title || 'Untitled')}</div>
            <div class="session-meta">
              <span class="cli-badge ${cliBadgeClass(s.cli_source)}">${cliDisplayName(s.cli_source)}</span>
              <span>${formatDate(s.date)}</span>
              <span>${formatSize(s.file_size)}</span>
              ${s.message_count ? `<span>${s.message_count} msgs</span>` : ''}
            </div>
            <div class="session-preview">${escapeHtml(s.preview || '')}</div>
          </div>
        `).join('')}
      </div>`;
  }
  list.innerHTML = html;
}

let expandedGroups = new Set();

function toggleProjectGroup(headerEl, projectName) {
  const sessionsDiv = document.querySelector(`[data-project-sessions="${CSS.escape(projectName)}"]`);
  if (expandedGroups.has(projectName)) {
    expandedGroups.delete(projectName);
    headerEl.classList.remove('expanded');
    if (sessionsDiv) sessionsDiv.classList.remove('expanded');
  } else {
    expandedGroups.add(projectName);
    headerEl.classList.add('expanded');
    if (sessionsDiv) sessionsDiv.classList.add('expanded');
  }
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
  if (result && !result.startsWith('Error:')) {
    toast(`Exported to ${result}`, 'success');
  } else {
    toast(result || 'Export failed', 'error');
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
        <button class="action-btn" data-cli-scan="${escapeHtml(cli.name)}" onclick="rescanCli(this.dataset.cliScan)">Rescan</button>
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
    // Preserve existing API key if the user didn't change the masked field.
    // The masked value '••••••••' means "unchanged" — don't overwrite.
    // An empty field means "clear the key". Any other value is a new key.
    summarizer_api_key: $('#summarizerApiKey')?.value === '••••••••'
      ? ''   // Masked = unchanged, send empty so backend preserves the real key
      : ($('#summarizerApiKey')?.value || ''),
    summarizer_model: getModelValue(),
    summarizer_custom_url: $('#summarizerCustomUrl')?.value || '',
    default_ember_collection: $('#emberCollection')?.value || 'general',
    ember_memory_url: $('#emberMemoryUrl')?.value || '',
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

async function removeCustomCli(name) {
  if (!confirm(`Remove custom CLI "${name}"?`)) return;
  const ok = await callApi('remove_custom_cli', name);
  if (ok) {
    toast('CLI removed', 'success');
    await detectCLIs();
    await refreshSessions();
  } else {
    toast('Failed to remove CLI', 'error');
  }
}

function renderCustomClis(clis) {
  const container = $('#customCliList');
  if (!container) return;
  const custom = clis.filter(c => c.custom);
  if (custom.length === 0) {
    container.innerHTML = '<div class="empty-state">No custom CLIs configured</div>';
    return;
  }
  container.innerHTML = custom.map(cli => `
    <div class="cli-status-card" style="margin-bottom:10px; border-left:3px solid ${cli.color}">
      <div class="cli-status-header">
        <span class="cli-status-name">${escapeHtml(cli.display_name)}</span>
        <button class="action-btn" data-cli-name="${escapeHtml(cli.display_name)}" onclick="removeCustomCli(this.dataset.cliName)" style="padding:2px 8px">Remove</button>
      </div>
      <div class="cli-status-meta">
        <div>Dir: ${escapeHtml(cli.directory)}</div>
        <div>Format: ${escapeHtml(cli.format)}</div>
      </div>
    </div>
  `).join('');
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

// ── Summarizer Tab Init ──────────────────────────────────────────────

async function initSummarizerTab() {
  populateSummarizeDropdown();
  await fetchModels($('#summarizerProvider')?.value || 'openai');
  await loadTemplates();
  await loadSummaryHistory();
}

// ── Summarizer ──────────────────────────────────────────────────────

let currentSummary = null;  // Store last summary result for copy/export
let modelCache = {};  // Cache fetched models per provider

function populateSummarizeDropdown() {
  const sel = $('#summarizeSessionSelect');
  if (!sel) return;
  sel.innerHTML = '<option value="">— Select a session —</option>';
  for (const s of allSessions) {
    const label = `${s.title || s.project || 'Untitled'} (${formatDate(s.date)})`;
    const opt = document.createElement('option');
    opt.value = s.filepath;
    opt.textContent = label;
    sel.appendChild(opt);
  }
  // Pre-select if a session is currently selected in the Sessions tab
  if (currentSession && currentSession.filepath) {
    sel.value = currentSession.filepath;
  }
}

// ── Model Fetching ───────────────────────────────────────────────────

async function fetchModels(provider) {
  const sel = $('#summarizerModel');
  const manual = $('#summarizerModelManual');
  const statusEl = $('#modelFetchStatus');
  if (!sel) return;

  // For custom provider, show manual input instead of dropdown
  if (provider === 'custom') {
    sel.style.display = 'none';
    if (manual) manual.style.display = '';
    if (statusEl) statusEl.textContent = '';
    return;
  }
  sel.style.display = '';
  if (manual) manual.style.display = 'none';

  // Check cache first (keyed by provider + api key)
  const apiKey = $('#summarizerApiKey')?.value || '';
  const cacheKey = provider + ':' + (apiKey ? btoa(apiKey).slice(0, 8) : 'nokey');
  if (modelCache[cacheKey]) {
    populateModelDropdown(sel, modelCache[cacheKey]);
    if (statusEl) statusEl.textContent = modelCache[cacheKey].live ? '' : modelCache[cacheKey].msg || 'Built-in models';
    return;
  }

  // Show loading
  sel.innerHTML = '<option value="">Loading models...</option>';
  if (statusEl) statusEl.textContent = 'Fetching models...';

  const result = await callApi('get_provider_models', provider, apiKey);

  if (result && result.ok) {
    modelCache[cacheKey] = result;
    populateModelDropdown(sel, result);
    if (statusEl) {
      if (result.live) {
        statusEl.textContent = `${result.models.length} models available`;
        statusEl.style.color = 'var(--success)';
      } else {
        statusEl.textContent = result.msg || 'Built-in models';
        statusEl.style.color = 'var(--fg-muted)';
      }
    }
  } else {
    sel.innerHTML = '<option value="">No models found</option>';
    if (statusEl) {
      statusEl.textContent = result?.msg || 'Failed to fetch models';
      statusEl.style.color = 'var(--error)';
    }
  }
}

function populateModelDropdown(sel, result) {
  // Use savedModelValue if set, otherwise current selection
  const current = savedModelValue || sel.value || $('#summarizerModelManual')?.value || '';
  savedModelValue = '';  // Clear after applying

  sel.innerHTML = '';
  if (!result.models || result.models.length === 0) {
    sel.innerHTML = '<option value="">No models available</option>';
    return;
  }

  // Add a blank option
  const blankOpt = document.createElement('option');
  blankOpt.value = '';
  blankOpt.textContent = '— Select model —';
  sel.appendChild(blankOpt);

  for (const m of result.models) {
    const opt = document.createElement('option');
    opt.value = m.id;
    const suffix = m.free ? ' (free)' : '';
    opt.textContent = m.name + suffix;
    opt.title = m.description || '';
    sel.appendChild(opt);
  }

  // Restore selection if it exists
  if (current) {
    sel.value = current;
    // If not in the list, add it as a custom option
    if (sel.value !== current) {
      const custom = document.createElement('option');
      custom.value = current;
      custom.textContent = current + ' (saved)';
      sel.appendChild(custom);
      sel.value = current;
    }
  }
}

async function testProvider() {
  const status = $('#providerStatus');
  if (!status) return;

  // Save settings first so the backend has current provider/key
  await saveSettings();

  status.textContent = 'Testing...';
  status.style.color = 'var(--fg-muted)';
  const result = await callApi('test_summarizer_connection');
  if (result && result.success) {
    status.textContent = `✓ Connected (${result.model || 'OK'})`;
    status.style.color = 'var(--success)';
  } else {
    status.textContent = `✗ ${result?.error || 'Failed'}`;
    status.style.color = 'var(--error)';
  }
}

async function loadTemplates() {
  const names = await callApi('list_templates');
  const sel = $('#templateSelect');
  if (!sel || !names) return;
  sel.innerHTML = '';
  for (const name of names) {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name === 'default' ? 'Default Summary Template' : name;
    sel.appendChild(opt);
  }
  // Load the currently selected template content
  await loadTemplateContent();
}

async function loadTemplateContent() {
  const name = $('#templateSelect')?.value || 'default';
  const content = await callApi('load_template', name);
  if (content && $('#templateEditor')) {
    $('#templateEditor').value = content;
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
  if (content && $('#templateEditor')) $('#templateEditor').value = content;
}

async function deleteTemplate() {
  const name = $('#templateSelect')?.value;
  if (!name || name === 'default') {
    toast('Cannot delete the default template', 'error');
    return;
  }
  const ok = await callApi('delete_template', name);
  if (ok) {
    toast('Template deleted', 'success');
    await loadTemplates();
  } else {
    toast('Failed to delete template', 'error');
  }
}

async function newTemplate() {
  const name = prompt('Template name:');
  if (!name) return;
  const sel = $('#templateSelect');
  const opt = document.createElement('option');
  opt.value = name;
  opt.textContent = name;
  sel.appendChild(opt);
  sel.value = name;
  $('#templateEditor').value = '';
  $('#templateEditor').focus();
}

async function summarizeCurrentSession() {
  const filepath = $('#summarizeSessionSelect')?.value;
  if (!filepath) {
    toast('Select a session first', 'error');
    return;
  }

  const templateName = $('#templateSelect')?.value || 'default';

  // Show progress
  const progressDiv = $('#summarizeProgress');
  const progressFill = $('#summarizeProgressFill');
  const progressText = $('#summarizeProgressText');
  if (progressDiv) progressDiv.style.display = 'block';
  if (progressFill) progressFill.classList.add('indeterminate');
  if (progressText) progressText.textContent = 'Generating summary...';

  // Disable button during request
  const btn = $('#btnRunSummarize');
  if (btn) btn.disabled = true;

  try {
    const result = await callApi('summarize_session', filepath, templateName);

    if (progressFill) progressFill.classList.remove('indeterminate');

    if (result && result.success) {
      if (progressFill) progressFill.style.width = '100%';
      if (progressText) progressText.textContent = 'Done!';

      currentSummary = result;

      // Display the result
      const resultSection = $('#summaryResultSection');
      const resultDiv = $('#summaryResult');
      const metaDiv = $('#summaryMeta');
      if (resultSection) resultSection.style.display = 'block';
      if (metaDiv) {
        metaDiv.innerHTML = `
          <span>🤖 ${escapeHtml(result.model || 'Unknown')}</span>
          <span>🔢 ${result.tokens_used || 0} tokens</span>
          <span>📄 ${escapeHtml(pathBasename(filepath))}</span>
        `;
      }
      if (resultDiv) resultDiv.textContent = result.content || 'No content returned';

      // Refresh history
      await loadSummaryHistory();

      toast('Summary generated', 'success');
    } else {
      if (progressDiv) progressDiv.style.display = 'none';
      toast(result?.error || 'Summarization failed', 'error');
    }
  } catch (err) {
    if (progressDiv) progressDiv.style.display = 'none';
    toast('Summarization error: ' + err.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
    setTimeout(() => {
      if (progressDiv) progressDiv.style.display = 'none';
    }, 2000);
  }
}

function pathBasename(filepath) {
  // Simple basename extraction
  return filepath.split('/').pop().replace(/\.[^.]+$/, '');
}

function copySummary() {
  if (!currentSummary || !currentSummary.content) {
    toast('No summary to copy', 'error');
    return;
  }
  navigator.clipboard.writeText(currentSummary.content).then(() => {
    toast('Summary copied to clipboard', 'success');
  }).catch(() => {
    // Fallback for pywebview
    toast('Copy not supported in this environment', 'error');
  });
}

async function exportSummary() {
  if (!currentSummary || !currentSummary.content) {
    toast('No summary to export', 'error');
    return;
  }
  const result = await callApi('export_summary_markdown', currentSummary.content, currentSummary.model || '');
  if (result && !result.startsWith('Error:')) {
    toast(`Exported to ${result}`, 'success');
  } else {
    toast(result || 'Export failed', 'error');
  }
}

async function ingestSummary() {
  if (!currentSummary || !currentSummary.content) {
    toast('No summary to ingest', 'error');
    return;
  }
  const filepath = $('#summarizeSessionSelect')?.value || '';
  const collection = $('#emberCollection')?.value || 'general';
  const result = await callApi('ingest_summary', currentSummary.content, collection, filepath);
  if (result) {
    toast('Summary ingested into ember-memory', 'success');
  } else {
    toast('Ingest failed — is ember-memory running?', 'error');
  }
}

async function loadSummaryHistory() {
  const history = await callApi('get_summary_history');
  const container = $('#summaryHistory');
  if (!container) return;

  if (!history || history.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📝</div>
        <div class="empty-text">No summaries yet</div>
      </div>`;
    return;
  }

  container.innerHTML = history.reverse().map((h, i) => `
    <div class="history-item" onclick="viewHistoryEntry(${i})" data-index="${i}">
      <div class="history-item-date">${formatDate(h.timestamp)} · ${escapeHtml(h.provider || '')} / ${escapeHtml(h.model || '')}</div>
      <div class="history-item-preview">${escapeHtml(h.session_slug || '')}</div>
      <div class="history-item-summary">${escapeHtml(h.summary_preview || '')}</div>
    </div>
  `).join('');
}

function viewHistoryEntry(index) {
  // Fetch history again and show the entry — stored in local cache
  // We rely on the backend storing the full summary
  callApi('get_summary_history').then(history => {
    if (!history || !history[index]) return;
    const entry = history[history.length - 1 - index]; // reverse order
    currentSummary = { content: entry.full_summary, model: entry.model, tokens_used: entry.tokens_used };

    const resultSection = $('#summaryResultSection');
    const resultDiv = $('#summaryResult');
    const metaDiv = $('#summaryMeta');
    if (resultSection) resultSection.style.display = 'block';
    if (metaDiv) {
      metaDiv.innerHTML = `
        <span>🤖 ${escapeHtml(entry.model || 'Unknown')}</span>
        <span>🔢 ${entry.tokens_used || 0} tokens</span>
        <span>📄 ${escapeHtml(entry.session_slug || '')}</span>
        <span>🕐 ${formatDate(entry.timestamp)}</span>
      `;
    }
    if (resultDiv) resultDiv.textContent = entry.full_summary || entry.summary_preview || '';

    // Switch to summarizer tab to show it
    $$('.tab-btn').forEach(b => b.classList.remove('active'));
    $$('.tab-panel').forEach(p => p.classList.remove('active'));
    $$('[data-tab="summarizer"]').forEach(b => b.classList.add('active'));
    const panel = $('#tab-summarizer');
    if (panel) panel.classList.add('active');
  });
}

// ── Global error handling ─────────────────────────────────────────────

window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled promise rejection:', event.reason);
  toast('An unexpected error occurred', 'error');
});

window.addEventListener('error', (event) => {
  console.error('Uncaught error:', event.error || event.message);
});

// ── Utility ─────────────────────────────────────────────────────────

function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/\//g, '&#x2F;');
}

function getModelValue() {
  const provider = $('#summarizerProvider')?.value || '';
  if (provider === 'custom') {
    return $('#summarizerModelManual')?.value || '';
  }
  return $('#summarizerModel')?.value || '';
}

// ── Custom Context Menu ──────────────────────────────────────────────
// pywebview suppresses native right-click menus on some backends.
// We enable debug=True + OPEN_DEVTOOLS_IN_DEBUG=False so the DOM
// contextmenu event fires, then show our own menu for editable fields
// and text selections.

let contextMenu = null;

function buildContextMenu() {
  if (contextMenu) return contextMenu;

  contextMenu = document.createElement('div');
  contextMenu.id = 'casContextMenu';
  contextMenu.style.cssText =
    'position:fixed; z-index:10000; background:var(--bg-elevated,#211c14);' +
    'border:1px solid var(--border-em,rgba(255,120,32,0.18)); border-radius:6px;' +
    'padding:4px 0; min-width:140px; box-shadow:0 8px 24px rgba(0,0,0,0.6);' +
    'display:none; font-size:12px; font-family:var(--font-ui,sans-serif);';

  const actions = [
    { label: 'Copy', cmd: 'copy' },
    { label: 'Cut', cmd: 'cut', editable: true },
    { label: 'Paste', cmd: 'paste', editable: true },
    { label: 'Select All', cmd: 'selectAll' },
  ];

  actions.forEach(({ label, cmd, editable }) => {
    const item = document.createElement('div');
    item.textContent = label;
    item.dataset.cmd = cmd;
    item.dataset.editableOnly = editable ? '1' : '0';
    item.style.cssText =
      'padding:6px 16px; cursor:pointer; color:var(--fg,#e8ddd0); transition:background 0.1s;';
    item.addEventListener('mouseenter', () => {
      item.style.background = 'rgba(255,120,32,0.15)';
    });
    item.addEventListener('mouseleave', () => {
      item.style.background = '';
    });
    item.addEventListener('click', () => {
      document.execCommand(cmd);
      hideContextMenu();
    });
    contextMenu.appendChild(item);
  });

  document.body.appendChild(contextMenu);
  return contextMenu;
}

function showContextMenu(x, y, isEditable) {
  const menu = buildContextMenu();

  // Show/hide edit-only items based on context
  menu.querySelectorAll('[data-editable-only="1"]').forEach(item => {
    item.style.display = isEditable ? '' : 'none';
  });

  // Show menu briefly offscreen to measure, then position
  menu.style.left = '-9999px';
  menu.style.top = '-9999px';
  menu.style.display = 'block';
  const rect = menu.getBoundingClientRect();
  menu.style.display = 'none';

  // Clamp position to viewport
  let left = x;
  let top = y;
  if (left + rect.width > window.innerWidth) left = window.innerWidth - rect.width - 5;
  if (top + rect.height > window.innerHeight) top = window.innerHeight - rect.height - 5;

  menu.style.left = left + 'px';
  menu.style.top = top + 'px';
  menu.style.display = 'block';
}

function hideContextMenu() {
  if (contextMenu) contextMenu.style.display = 'none';
}

function isEditableTarget(el) {
  const tag = (el.tagName || '').toLowerCase();
  return tag === 'input' || tag === 'textarea' || el.isContentEditable;
}

function hasSelection() {
  const sel = window.getSelection();
  return sel && sel.toString().trim().length > 0;
}

document.addEventListener('contextmenu', function(e) {
  const target = e.target;

  // Show custom menu on editable fields, OR when text is selected anywhere.
  if (!isEditableTarget(target) && !hasSelection()) {
    hideContextMenu();
    return;
  }
  e.preventDefault();
  e.stopPropagation();
  showContextMenu(e.clientX, e.clientY, isEditableTarget(target));
}, true);

// Close context menu on click elsewhere or scroll
document.addEventListener('click', hideContextMenu);
document.addEventListener('scroll', hideContextMenu, true);