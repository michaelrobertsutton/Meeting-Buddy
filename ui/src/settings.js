const state = {
  ws: null,
  connected: false,
  settings: null,
  docs: [],
};

const WS_URL = 'ws://localhost:8765';

const dom = {};

let _cmdId = 0;
const _pending = new Map();

function sendCommand(command, params = {}) {
  return new Promise((resolve, reject) => {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
      reject(new Error('Not connected'));
      return;
    }
    const id = String(++_cmdId);
    _pending.set(id, { resolve, reject });
    state.ws.send(JSON.stringify({ id, command, ...params }));
    setTimeout(() => {
      if (_pending.has(id)) {
        _pending.delete(id);
        reject(new Error('Command timed out'));
      }
    }, 30000);
  });
}

function setBackendStatus(connected) {
  state.connected = connected;
  if (!dom.backendStatus) return;
  if (connected) {
    dom.backendStatus.textContent = 'Backend: Connected';
    dom.backendStatus.className = 'settings-status ok';
  } else {
    dom.backendStatus.textContent = 'Backend: Disconnected';
    dom.backendStatus.className = 'settings-status error';
  }
  if (dom.btnLogin) dom.btnLogin.disabled = !connected;
}

function showPage(page) {
  const pages = ['general', 'documents', 'account'];
  for (const p of pages) {
    const el = document.getElementById('page-' + p);
    if (el) el.classList.toggle('hidden', p !== page);
  }
  for (const btn of document.querySelectorAll('.settings-nav-item')) {
    btn.classList.toggle('active', btn.dataset.page === page);
  }
  dom.settingsTitle.textContent = page === 'general' ? 'General' : page === 'documents' ? 'Documents' : 'OpenAI Account';
}

async function loadSettings() {
  const data = await sendCommand('get_settings');
  state.settings = data;

  // Projects
  const projects = data.projects || [];
  dom.projectSelect.innerHTML = '<option value="">No project</option>';
  for (const p of projects) {
    const opt = document.createElement('option');
    opt.value = p.name;
    opt.textContent = p.name;
    if (p.name === (data.active_project || '')) opt.selected = true;
    dom.projectSelect.appendChild(opt);
  }

  // OAuth status
  const oauth = data.oauth_status || {};
  if (oauth.logged_in) {
    dom.oauthLoggedOut.classList.add('hidden');
    dom.oauthLoggedIn.classList.remove('hidden');
    dom.oauthEmail.textContent = oauth.email || 'Logged in';
  } else {
    dom.oauthLoggedOut.classList.remove('hidden');
    dom.oauthLoggedIn.classList.add('hidden');
  }

  // API key status
  if (data.has_api_key) {
    dom.apiKeyStatus.textContent = 'Key set: ' + data.openai_api_key_masked;
    dom.apiKeyStatus.className = 'settings-status ok';
  } else {
    dom.apiKeyStatus.textContent = 'No API key configured';
    dom.apiKeyStatus.className = 'settings-status error';
  }
}

async function refreshDocs() {
  const data = await sendCommand('list_docs');
  const docs = data.docs || [];
  state.docs = docs;
  dom.docsRows.innerHTML = '';

  for (const d of docs) {
    const row = document.createElement('div');
    row.className = 'docs-row';

    const status = document.createElement('div');
    status.className = 'col-status';
    const dot = document.createElement('span');
    dot.className = 'doc-status-dot ' + (d.indexed ? 'indexed' : 'missing');
    status.appendChild(dot);

    const name = document.createElement('div');
    name.className = 'col-name';
    name.textContent = d.title;

    const size = document.createElement('div');
    size.className = 'col-size';
    size.textContent = d.size_bytes ? (Math.round(d.size_bytes / 1024) + ' KB') : '—';

    const pr = document.createElement('div');
    pr.className = 'col-priority';
    const sel = document.createElement('select');
    sel.className = 'doc-priority';
    for (const v of ['high', 'normal', 'low']) {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      if ((d.priority || 'normal') === v) opt.selected = true;
      sel.appendChild(opt);
    }
    sel.addEventListener('change', async () => {
      try {
        await sendCommand('update_doc_meta', { title: d.title, priority: sel.value });
      } catch (e) {
        console.error(e);
      }
    });
    pr.appendChild(sel);

    const actions = document.createElement('div');
    actions.className = 'col-actions';
    const btnDel = document.createElement('button');
    btnDel.className = 'btn-danger';
    btnDel.textContent = 'Delete';
    btnDel.addEventListener('click', async () => {
      if (!confirm('Delete "' + d.title + '"?')) return;
      await sendCommand('delete_doc', { title: d.title });
      refreshDocs();
    });
    actions.appendChild(btnDel);

    row.appendChild(status);
    row.appendChild(name);
    row.appendChild(size);
    row.appendChild(pr);
    row.appendChild(actions);

    dom.docsRows.appendChild(row);
  }
}

async function connect() {
  setBackendStatus(false);
  const ws = new WebSocket(WS_URL);
  state.ws = ws;

  ws.onopen = async () => {
    setBackendStatus(true);
    try {
      await loadSettings();
      await refreshDocs();
    } catch (e) {
      console.error(e);
    }
  };

  ws.onclose = () => setBackendStatus(false);
  ws.onerror = () => setBackendStatus(false);

  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }

    if (msg.type === 'response') {
      const p = _pending.get(String(msg.id));
      if (!p) return;
      _pending.delete(String(msg.id));
      if (msg.success) p.resolve(msg.data || {});
      else p.reject(new Error(msg.error || 'Command failed'));
      return;
    }

    if (msg.type === 'ingest_progress') {
      dom.ingestProgress.classList.remove('hidden');
      const pct = Math.round((msg.current / msg.total) * 100);
      dom.progressFill.style.width = pct + '%';
      dom.progressText.textContent = 'Ingesting ' + msg.file + ' (' + msg.current + '/' + msg.total + ')';
      return;
    }

    if (msg.type === 'ingest_complete') {
      dom.progressFill.style.width = '100%';
      dom.progressText.textContent = 'Done: ' + msg.total_chunks + ' chunks';
      setTimeout(() => dom.ingestProgress.classList.add('hidden'), 1500);
      refreshDocs();
      return;
    }

    // If docs/prefs updated from backend snapshot/update, refresh our view.
    if (msg.type === 'snapshot' || msg.type === 'update') {
      if (msg.pinned || msg.qa_history) {
        // ignore
      }
    }
  };
}

async function pickFiles() {
  const { open } = window.__TAURI__.dialog;
  const selected = await open({
    multiple: true,
    filters: [{ name: 'Documents', extensions: ['pdf', 'docx', 'md', 'html', 'htm', 'txt'] }],
  });
  if (!selected) return;
  const paths = Array.isArray(selected) ? selected : [selected];
  await sendCommand('ingest_files', { paths });
}

async function pickFolder() {
  const { open } = window.__TAURI__.dialog;
  const selected = await open({ directory: true });
  if (!selected) return;
  await sendCommand('ingest_files', { paths: [selected] });
}

async function startLogin() {
  dom.loginStatus.textContent = 'Opening browser...';
  dom.loginStatus.className = 'settings-status';
  try {
    const data = await sendCommand('start_login');
    const { open } = window.__TAURI__.shell;
    await open(data.auth_url);
    dom.loginStatus.textContent = 'Waiting for login in browser...';
  } catch (e) {
    dom.loginStatus.textContent = 'Error: ' + e.message;
    dom.loginStatus.className = 'settings-status error';
  }
}

async function doLogout() {
  await sendCommand('logout');
  await loadSettings();
}

async function saveApiKey() {
  const key = dom.apiKeyInput.value.trim();
  if (!key) return;
  try {
    const data = await sendCommand('set_api_key', { key });
    dom.apiKeyInput.value = '';
    dom.apiKeyStatus.textContent = 'Key saved: ' + data.openai_api_key_masked;
    dom.apiKeyStatus.className = 'settings-status ok';
  } catch (e) {
    dom.apiKeyStatus.textContent = 'Error: ' + e.message;
    dom.apiKeyStatus.className = 'settings-status error';
  }
}

async function switchProject() {
  const name = dom.projectSelect.value;
  if (!name) return;
  await sendCommand('switch_project', { name });
  refreshDocs();
}

async function createProject() {
  const name = dom.newProjectName.value.trim();
  if (!name) return;
  const data = await sendCommand('create_project', { name });
  dom.createProjectForm.classList.add('hidden');
  dom.newProjectName.value = '';
  await loadSettings();
  await sendCommand('switch_project', { name });
  await loadSettings();
  refreshDocs();
}

async function deleteProject() {
  const name = dom.projectSelect.value;
  if (!name) return;
  if (!confirm('Delete project "' + name + '"?')) return;
  await sendCommand('delete_project', { name });
  await loadSettings();
  refreshDocs();
}

document.addEventListener('DOMContentLoaded', () => {
  dom.backendStatus = document.getElementById('backend-status');
  dom.settingsTitle = document.getElementById('settings-title');

  dom.projectSelect = document.getElementById('project-select');
  dom.btnNewProject = document.getElementById('btn-new-project');
  dom.btnDeleteProject = document.getElementById('btn-delete-project');
  dom.createProjectForm = document.getElementById('create-project-form');
  dom.newProjectName = document.getElementById('new-project-name');
  dom.btnCreateProject = document.getElementById('btn-create-project');
  dom.btnCancelCreate = document.getElementById('btn-cancel-create');

  dom.btnAddFiles = document.getElementById('btn-add-files');
  dom.btnAddFolder = document.getElementById('btn-add-folder');
  dom.btnReindex = document.getElementById('btn-reindex');
  dom.docsRows = document.getElementById('docs-rows');

  dom.ingestProgress = document.getElementById('ingest-progress');
  dom.progressFill = document.getElementById('progress-fill');
  dom.progressText = document.getElementById('progress-text');

  dom.btnLogin = document.getElementById('btn-login');
  dom.loginStatus = document.getElementById('login-status');
  dom.oauthLoggedOut = document.getElementById('oauth-logged-out');
  dom.oauthLoggedIn = document.getElementById('oauth-logged-in');
  dom.oauthEmail = document.getElementById('oauth-email');
  dom.btnLogout = document.getElementById('btn-logout');

  dom.apiKeyInput = document.getElementById('api-key-input');
  dom.btnSaveKey = document.getElementById('btn-save-key');
  dom.apiKeyStatus = document.getElementById('api-key-status');

  dom.btnClose = document.getElementById('btn-close-settings');

  // nav
  for (const btn of document.querySelectorAll('.settings-nav-item')) {
    btn.addEventListener('click', () => {
      showPage(btn.dataset.page);
      if (btn.dataset.page === 'documents') refreshDocs();
    });
  }

  dom.projectSelect.addEventListener('change', switchProject);
  dom.btnNewProject.addEventListener('click', () => {
    dom.createProjectForm.classList.remove('hidden');
    dom.newProjectName.focus();
  });
  dom.btnCancelCreate.addEventListener('click', () => {
    dom.createProjectForm.classList.add('hidden');
    dom.newProjectName.value = '';
  });
  dom.btnCreateProject.addEventListener('click', createProject);
  dom.btnDeleteProject.addEventListener('click', deleteProject);

  dom.btnAddFiles.addEventListener('click', pickFiles);
  dom.btnAddFolder.addEventListener('click', pickFolder);
  dom.btnReindex.addEventListener('click', () => alert('Re-index all not implemented yet'));

  dom.btnLogin.addEventListener('click', startLogin);
  dom.btnLogout.addEventListener('click', doLogout);
  dom.btnSaveKey.addEventListener('click', saveApiKey);

  dom.btnClose.addEventListener('click', async () => {
    const { getCurrentWindow } = window.__TAURI__.window;
    await getCurrentWindow().hide();
  });

  connect();
});
