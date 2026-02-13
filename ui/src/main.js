// --- State ---
const state = {
    segments: [],
    version: -1,
    pinned: false,
    pinnedSegments: null,
    connected: false,
    ws: null,
    activeQuestion: null,
    activeAnswer: null,
    settingsOpen: false,
    questionHistory: [],
    historyOpen: false,
    manualQuestion: false,
    synthesisSearching: false,
    qaHistory: [],
    prepQuestions: [],
    prepResults: {},

    pinnedAnswers: [],

    streamingAnswer: null,  // Partial text being streamed

    lastTranscriptAtMs: 0,
};

const WS_URL = 'ws://localhost:8765';
const RECONNECT_DELAY_MS = 2000;
const MAX_RECONNECT_DELAY_MS = 30000;

// --- Command request/response ---
let _cmdId = 0;
const _pendingCommands = new Map(); // id -> {resolve, reject}

function sendCommand(command, params = {}) {
    return new Promise((resolve, reject) => {
        if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
            reject(new Error('Not connected'));
            return;
        }
        const id = String(++_cmdId);
        _pendingCommands.set(id, { resolve, reject });
        state.ws.send(JSON.stringify({ id, command, ...params }));

        // Timeout after 30s
        setTimeout(() => {
            if (_pendingCommands.has(id)) {
                _pendingCommands.delete(id);
                reject(new Error('Command timed out'));
            }
        }, 30000);
    });
}

async function ensureConnected(timeoutMs = 4000) {
    // If already open, done
    if (state.ws && state.ws.readyState === WebSocket.OPEN) return;

    // If no ws or it's closed, start a connection attempt
    if (!state.ws || state.ws.readyState === WebSocket.CLOSED) {
        connectWebSocket();
    }

    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) return;
        await new Promise((r) => setTimeout(r, 100));
    }
    throw new Error('Not connected');
}

// --- DOM References ---
const dom = {};

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    dom.questionText = document.getElementById('question-text');
    dom.answerText = document.getElementById('answer-text');
    dom.bulletList = document.getElementById('bullet-list');
    dom.btnBookmark = document.getElementById('btn-bookmark');
    dom.pinnedSection = document.getElementById('pinned');
    dom.pinnedList = document.getElementById('pinned-list');
    dom.bestPracticeSection = document.getElementById('best-practice');
    dom.bestPracticeList = document.getElementById('best-practice-list');
    dom.clarifierSection = document.getElementById('clarifiers');
    dom.clarifierList = document.getElementById('clarifier-list');
    dom.citationPills = document.getElementById('citation-pills');
    dom.citationPopover = document.getElementById('citation-popover');
    dom.transcriptContent = document.getElementById('transcript-content');
    dom.transcriptScroll = document.getElementById('transcript-scroll');
    dom.transcriptQuiet = document.getElementById('transcript-quiet');
    dom.connectionStatus = document.getElementById('connection-status');
    dom.pinStatus = document.getElementById('pin-status');
    dom.btnPin = document.getElementById('btn-pin');
    dom.btnClose = document.getElementById('btn-close');
    dom.btnSettings = document.getElementById('btn-settings');
    dom.settingsDrawer = document.getElementById('settings-drawer');
    dom.content = document.getElementById('content');

    // Onboarding modal
    dom.onboarding = document.getElementById('onboarding');
    dom.btnOpenScreen = document.getElementById('btn-open-screen');
    dom.btnOpenMic = document.getElementById('btn-open-mic');
    dom.btnOnboardingDone = document.getElementById('btn-onboarding-done');

    // Header project switcher
    dom.headerProject = document.getElementById('header-project');
    dom.quickQuestion = document.getElementById('quick-question');

    // Question history
    dom.btnAutoQuestion = document.getElementById('btn-auto-question');
    dom.btnQuestionHistory = document.getElementById('btn-question-history');
    dom.qhCount = document.getElementById('qh-count');
    dom.questionHistoryPanel = document.getElementById('question-history-panel');
    dom.questionHistoryList = document.getElementById('question-history-list');

    // Q&A history
    dom.qaHistoryList = document.getElementById('qa-history-list');

    // Answer section
    dom.answer = document.getElementById('answer');
    dom.answerSearching = document.getElementById('answer-searching');

    // Settings elements
    dom.apiKeyInput = document.getElementById('api-key-input');
    dom.btnSaveKey = document.getElementById('btn-save-key');
    dom.apiKeyStatus = document.getElementById('api-key-status');
    dom.projectSelect = document.getElementById('project-select');
    dom.btnNewProject = document.getElementById('btn-new-project');
    dom.btnDeleteProject = document.getElementById('btn-delete-project');
    dom.createProjectForm = document.getElementById('create-project-form');
    dom.newProjectName = document.getElementById('new-project-name');
    dom.btnCreateProject = document.getElementById('btn-create-project');
    dom.btnCancelCreate = document.getElementById('btn-cancel-create');
    dom.btnAddFiles = document.getElementById('btn-add-files');
    dom.btnAddFolder = document.getElementById('btn-add-folder');
    dom.urlInput = document.getElementById('url-input');
    dom.btnAddUrl = document.getElementById('btn-add-url');
    dom.ingestProgress = document.getElementById('ingest-progress');
    dom.progressFill = document.getElementById('progress-fill');
    dom.progressText = document.getElementById('progress-text');
    dom.docList = document.getElementById('doc-list');
    dom.btnCloseSettings = document.getElementById('btn-close-settings');
    dom.btnLogin = document.getElementById('btn-login');

    // Backend status
    dom.backendStatus = document.getElementById('backend-status');
    dom.backendHint = document.getElementById('backend-hint');

    // Prep mode
    dom.btnGeneratePrep = document.getElementById('btn-generate-prep');
    dom.prepQuestionInput = document.getElementById('prep-question-input');
    dom.btnAddPrep = document.getElementById('btn-add-prep');
    dom.prepList = document.getElementById('prep-list');
    dom.loginStatus = document.getElementById('login-status');
    dom.oauthLoggedOut = document.getElementById('oauth-logged-out');
    dom.oauthLoggedIn = document.getElementById('oauth-logged-in');
    dom.oauthEmail = document.getElementById('oauth-email');
    dom.btnLogout = document.getElementById('btn-logout');
    dom.apiKeyFallback = document.getElementById('api-key-fallback');

    // Export button
    dom.btnExport = document.getElementById('btn-export');

    // Event listeners
    dom.btnExport.addEventListener('click', exportSession);
    dom.btnPin.addEventListener('click', togglePin);
    dom.btnBookmark.addEventListener('click', bookmarkActiveAnswer);
    dom.btnClose.addEventListener('click', () => {
        const { getCurrentWindow } = window.__TAURI__.window;
        getCurrentWindow().hide();
    });
    dom.btnSettings.addEventListener('click', openSettingsWindow);
    dom.btnCloseSettings.addEventListener('click', toggleSettings);
    dom.btnSaveKey.addEventListener('click', saveApiKey);
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
    dom.projectSelect.addEventListener('change', switchProject);
    dom.btnAddFiles.addEventListener('click', pickFiles);
    dom.btnAddFolder.addEventListener('click', pickFolder);
    dom.btnAddUrl.addEventListener('click', addUrl);
    dom.urlInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') addUrl();
    });
    dom.btnLogin.addEventListener('click', startLogin);
    dom.btnLogout.addEventListener('click', doLogout);
    dom.headerProject.addEventListener('change', headerSwitchProject);
    dom.btnAutoQuestion.addEventListener('click', resumeAutoQuestion);
    dom.btnQuestionHistory.addEventListener('click', toggleQuestionHistory);

    // Prep mode
    dom.btnGeneratePrep.addEventListener('click', generatePrep);
    dom.btnAddPrep.addEventListener('click', addPrepQuestion);
    dom.prepQuestionInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') addPrepQuestion();
    });

    // Quick-type question override
    dom.quickQuestion.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            // Execute immediately on Enter (no debounce)
            await setManualQuestionFromInput(true);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            if (_quickQuestionTimer) clearTimeout(_quickQuestionTimer);
            dom.quickQuestion.value = '';
            await setManualQuestionFromInput(true);
            dom.quickQuestion.blur();
        }
    });
    dom.quickQuestion.addEventListener('blur', () => {
        // Commit whatever is in the box on blur (useful after paste)
        // Use debounce for blur to avoid firing on accidental clicks
        setManualQuestionFromInput(false);
    });

    // Enter key for inputs
    dom.apiKeyInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') saveApiKey();
    });
    dom.newProjectName.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') createProject();
    });

    // Listen for pin toggle from Rust global hotkey
    const { listen } = window.__TAURI__.event;
    listen('toggle-pin', () => {
        togglePin();
    });

    listen('open-settings', () => {
        openSettingsWindow();
    });

    listen('clear-session', () => {
        clearSession();
    });
    
    // Listen for backend termination event
    listen('backend-terminated', (event) => {
        console.error('[Backend] Sidecar terminated with code:', event.payload);
        setConnectionStatus('disconnected');
        if (dom.backendStatus) {
            dom.backendStatus.textContent = `Backend: Crashed (code ${event.payload})`;
            dom.backendStatus.className = 'error';
        }
    });

    // Onboarding actions
    function showOnboarding() {
        if (!dom.onboarding) {
            console.error('[Onboarding] DOM element not found!');
            return;
        }
        console.log('[Onboarding] Showing overlay');
        dom.onboarding.classList.remove('hidden');
    }
    
    function hideOnboarding() {
        if (!dom.onboarding) {
            console.error('[Onboarding] DOM element not found!');
            return;
        }
        console.log('[Onboarding] Hiding overlay');
        dom.onboarding.classList.add('hidden');
        try { 
            localStorage.setItem('mb_onboarding_done', '1');
            // Also set a flag to disable it entirely if user wants
        } catch (_) {}
    }
    
    function disableOnboardingPermanently() {
        console.log('[Onboarding] Disabling onboarding permanently');
        hideOnboarding();
        try {
            localStorage.setItem('mb_onboarding_disabled', '1');
        } catch (_) {}
    }
    
    // Make hideOnboarding globally accessible so Rust can call it
    window.__hideOnboarding = hideOnboarding;
    window.__disableOnboarding = disableOnboardingPermanently;

    // Attach button handlers with multiple fallbacks
    function attachOnboardingHandlers() {
        console.log('[Onboarding] Attaching handlers...');
        console.log('[Onboarding] btnOnboardingDone:', dom.btnOnboardingDone);
        console.log('[Onboarding] btnOpenScreen:', dom.btnOpenScreen);
        console.log('[Onboarding] btnOpenMic:', dom.btnOpenMic);
        
        // Done button - MUST work
        if (dom.btnOnboardingDone) {
            // Remove any existing listeners
            const newDoneBtn = dom.btnOnboardingDone.cloneNode(true);
            dom.btnOnboardingDone.parentNode.replaceChild(newDoneBtn, dom.btnOnboardingDone);
            dom.btnOnboardingDone = newDoneBtn;
            
            dom.btnOnboardingDone.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                console.log('[Onboarding] Done button clicked - handler fired!');
                hideOnboarding();
            });
            console.log('[Onboarding] Done button handler attached');
        } else {
            console.error('[Onboarding] Done button not found in DOM!');
        }
        
        // Screen Recording button
        if (dom.btnOpenScreen) {
            const newScreenBtn = dom.btnOpenScreen.cloneNode(true);
            dom.btnOpenScreen.parentNode.replaceChild(newScreenBtn, dom.btnOpenScreen);
            dom.btnOpenScreen = newScreenBtn;
            
            dom.btnOpenScreen.addEventListener('click', async function(e) {
                e.preventDefault();
                e.stopPropagation();
                console.log('[Onboarding] Screen Settings button clicked - handler fired!');
                try {
                    const { open } = window.__TAURI__.shell;
                    console.log('[Onboarding] Calling shell.open()...');
                    await open('x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture');
                    console.log('[Onboarding] Screen settings opened successfully');
                } catch (err) {
                    console.error('[Onboarding] shell.open() failed:', err);
                    // Fallback: try opening System Preferences directly
                    try {
                        const { open } = window.__TAURI__.shell;
                        await open('x-apple.systempreferences:');
                    } catch (fallbackErr) {
                        console.error('[Onboarding] Fallback also failed:', fallbackErr);
                        alert('Failed to open System Settings. Please manually go to System Settings > Privacy & Security > Screen Recording');
                    }
                }
            });
            console.log('[Onboarding] Screen button handler attached');
        } else {
            console.error('[Onboarding] Screen button not found in DOM!');
        }
        
        // Microphone button
        if (dom.btnOpenMic) {
            const newMicBtn = dom.btnOpenMic.cloneNode(true);
            dom.btnOpenMic.parentNode.replaceChild(newMicBtn, dom.btnOpenMic);
            dom.btnOpenMic = newMicBtn;
            
            dom.btnOpenMic.addEventListener('click', async function(e) {
                e.preventDefault();
                e.stopPropagation();
                console.log('[Onboarding] Mic Settings button clicked - handler fired!');
                try {
                    const { open } = window.__TAURI__.shell;
                    console.log('[Onboarding] Calling shell.open()...');
                    await open('x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone');
                    console.log('[Onboarding] Mic settings opened successfully');
                } catch (err) {
                    console.error('[Onboarding] shell.open() failed:', err);
                    // Fallback: try opening System Preferences directly
                    try {
                        const { open } = window.__TAURI__.shell;
                        await open('x-apple.systempreferences:');
                    } catch (fallbackErr) {
                        console.error('[Onboarding] Fallback also failed:', fallbackErr);
                        alert('Failed to open System Settings. Please manually go to System Settings > Privacy & Security > Microphone');
                    }
                }
            });
            console.log('[Onboarding] Mic button handler attached');
        } else {
            console.error('[Onboarding] Mic button not found in DOM!');
        }
    }
    
    // Attach handlers immediately
    attachOnboardingHandlers();
    
    // CRITICAL: Add keyboard shortcuts as fallback
    // Escape key = dismiss overlay
    // Cmd+S = open Screen Recording settings
    // Cmd+M = open Microphone settings
    document.addEventListener('keydown', async (e) => {
        // Only handle if onboarding is visible
        if (!dom.onboarding || dom.onboarding.classList.contains('hidden')) {
            return;
        }
        
        if (e.key === 'Escape') {
            e.preventDefault();
            e.stopPropagation();
            console.log('[Onboarding] Escape key pressed - dismissing overlay');
            hideOnboarding();
        } else if ((e.metaKey || e.ctrlKey) && e.key === 's') {
            e.preventDefault();
            e.stopPropagation();
            console.log('[Onboarding] Cmd+S pressed - opening Screen Recording settings');
            try {
                const { open } = window.__TAURI__.shell;
                await open('x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture');
            } catch (err) {
                console.error('[Onboarding] Failed:', err);
            }
        } else if ((e.metaKey || e.ctrlKey) && e.key === 'm') {
            e.preventDefault();
            e.stopPropagation();
            console.log('[Onboarding] Cmd+M pressed - opening Microphone settings');
            try {
                const { open } = window.__TAURI__.shell;
                await open('x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone');
            } catch (err) {
                console.error('[Onboarding] Failed:', err);
            }
        }
    });
    
    // Also try direct button access via onclick attribute as absolute fallback
    if (dom.btnOnboardingDone) {
        dom.btnOnboardingDone.setAttribute('onclick', 'if(window.__hideOnboarding) window.__hideOnboarding(); return false;');
    }
    if (dom.btnOpenScreen) {
        dom.btnOpenScreen.setAttribute('onclick', 'window.__openScreenSettings && window.__openScreenSettings()');
        window.__openScreenSettings = async () => {
            try {
                const { open } = window.__TAURI__.shell;
                await open('x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture');
            } catch (err) {
                console.error('[Onboarding] Failed:', err);
            }
        };
    }
    if (dom.btnOpenMic) {
        dom.btnOpenMic.setAttribute('onclick', 'window.__openMicSettings && window.__openMicSettings()');
        window.__openMicSettings = async () => {
            try {
                const { open } = window.__TAURI__.shell;
                await open('x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone');
            } catch (err) {
                console.error('[Onboarding] Failed:', err);
            }
        };
    }

    // Check permissions and show onboarding if needed
    async function checkAndShowOnboarding() {
        try {
            // Check Screen Recording permission first
            let hasPermission = false;
            try {
                const { invoke } = window.__TAURI__.core;
                hasPermission = await invoke('check_screen_recording_permission');
                console.log('[Onboarding] Screen Recording permission status:', hasPermission);
            } catch (err) {
                console.warn('[Onboarding] Failed to check permission:', err);
                // If we cannot reliably check, don't show the overlay (avoid false positives).
                return;
            }

            // If permission is granted, skip overlay entirely
            if (hasPermission) {
                console.log('[Onboarding] Permission already granted, skipping overlay');
                hideOnboarding();
                return;
            }
            
            // Check if user has manually dismissed onboarding before
            // Only respect this if permission is still missing
            if (localStorage.getItem('mb_onboarding_done')) {
                console.log('[Onboarding] User previously dismissed, but permission still missing - showing again');
            }
            
            // Permission not granted, show overlay
            console.log('[Onboarding] Showing overlay - permission not granted');
            showOnboarding();
        } catch (err) {
            console.error('[Onboarding] Error checking permissions:', err);
            // If permission check fails (invoke not available, etc.), do NOT block the user.
            // They can still open Settings and resolve permissions as needed.
            return;
        }
    }
    
    // Check permissions on startup (after DOM is ready)
    // Delay slightly to ensure Tauri APIs are available
    setTimeout(() => {
        checkAndShowOnboarding();
    }, 100);

    connectWebSocket();
});

// --- Pin Logic ---
function togglePin() {
    state.pinned = !state.pinned;

    if (state.pinned) {
        state.pinnedSegments = [...state.segments];
        document.body.classList.add('pinned');
        dom.pinStatus.classList.remove('hidden');
        dom.btnPin.classList.add('active');
    } else {
        state.pinnedSegments = null;
        document.body.classList.remove('pinned');
        dom.pinStatus.classList.add('hidden');
        dom.btnPin.classList.remove('active');
        renderTranscript();
    }
}

// --- Settings Panel ---
async function openSettingsWindow() {
    // Prefer the separate Settings window (Phase UI). Fall back to the drawer.
    try {
        const { WebviewWindow } = window.__TAURI__.webviewWindow;
        let w = WebviewWindow.getByLabel('settings');
        if (!w) {
            w = new WebviewWindow('settings', {
                url: 'settings.html',
                title: 'Meeting Buddy Settings',
                width: 860,
                height: 600,
                transparent: true,
            });
        }
        await w.show();
        await w.setFocus();
        return;
    } catch (err) {
        console.debug('[Settings] Falling back to drawer:', err.message);
        toggleSettings();
    }
}

function toggleSettings() {
    state.settingsOpen = !state.settingsOpen;
    dom.settingsDrawer.classList.toggle('hidden', !state.settingsOpen);
    dom.content.classList.toggle('hidden', state.settingsOpen);
    dom.btnSettings.classList.toggle('active', state.settingsOpen);

    if (state.settingsOpen) {
        // Ensure backend status is immediately accurate
        setConnectionStatus(state.connected ? 'connected' : 'disconnected');
        // Load settings asynchronously - don't block UI if backend isn't connected
        loadSettings().catch(err => {
            console.error('[Settings] Failed to load settings:', err);
            // Still show the settings panel even if loading fails
        });
    }
}

function clearSession() {
    // Local UI reset (backend retains transcript unless restarted)
    state.segments = [];
    state.version = -1;
    state.activeQuestion = null;
    state.activeAnswer = null;
    state.qaHistory = [];
    state.pinned = false;
    state.pinnedSegments = null;
    state.lastTranscriptAtMs = 0;

    renderQuestion(null);
    dom.answerText.textContent = 'Waiting for question...';
    dom.answerText.classList.add('placeholder');
    dom.bulletList.innerHTML = '<li class="placeholder">Bullets will appear here</li>';
    renderTranscript();
    renderQAHistory();
}

async function exportSession() {
    try {
        const { save } = window.__TAURI__.dialog;
        const savePath = await save({
            defaultPath: 'meeting-export.md',
            filters: [
                { name: 'Markdown', extensions: ['md'] },
                { name: 'JSON', extensions: ['json'] },
            ],
        });
        if (!savePath) return; // user cancelled

        const fmt = savePath.endsWith('.json') ? 'json' : 'markdown';
        await sendCommand('export_session', { format: fmt, path: savePath });

        // Brief feedback
        const origText = dom.btnExport.textContent;
        dom.btnExport.textContent = 'Exported!';
        dom.btnExport.classList.add('active');
        setTimeout(() => {
            dom.btnExport.textContent = origText;
            dom.btnExport.classList.remove('active');
        }, 2000);
    } catch (err) {
        console.error('[Export] Failed:', err);
        dom.btnExport.textContent = 'Error';
        setTimeout(() => { dom.btnExport.textContent = 'Export'; }, 2000);
    }
}

async function loadSettings() {
    try {
        // Don't block if backend isn't connected - show settings panel anyway
        if (!state.connected) {
            console.warn('[Settings] Backend not connected, skipping load');
            return;
        }
        
        const data = await sendCommand('get_settings');
        // API key status
        if (data.has_api_key) {
            dom.apiKeyStatus.textContent = 'Key set: ' + data.openai_api_key_masked;
            dom.apiKeyStatus.className = 'settings-status ok';
        } else {
            dom.apiKeyStatus.textContent = 'No API key configured';
            dom.apiKeyStatus.className = 'settings-status error';
        }
        dom.apiKeyInput.value = '';

        // OAuth status
        const oauth = data.oauth_status || {};
        if (oauth.logged_in) {
            dom.oauthLoggedOut.classList.add('hidden');
            dom.oauthLoggedIn.classList.remove('hidden');
            dom.oauthEmail.textContent = oauth.email || 'Logged in';
            dom.loginStatus.textContent = '';
        } else {
            dom.oauthLoggedOut.classList.remove('hidden');
            dom.oauthLoggedIn.classList.add('hidden');
            dom.loginStatus.textContent = '';
        }

        // Projects
        renderProjectList(data.projects || [], data.active_project || '');

        // Docs
        refreshDocList();

        // Prep mode (best-effort)
        refreshPrep();
    } catch (err) {
        console.error('[Settings] Load failed:', err);
        // Don't prevent settings panel from showing if load fails
    }
}

async function saveApiKey() {
    const key = dom.apiKeyInput.value.trim();
    if (!key) return;

    try {
        const data = await sendCommand('set_api_key', { key });
        dom.apiKeyInput.value = '';
        dom.apiKeyStatus.textContent = 'Key saved: ' + data.openai_api_key_masked;
        dom.apiKeyStatus.className = 'settings-status ok';
    } catch (err) {
        dom.apiKeyStatus.textContent = 'Error: ' + err.message;
        dom.apiKeyStatus.className = 'settings-status error';
    }
}

async function startLogin() {
    dom.btnLogin.disabled = true;
    dom.loginStatus.textContent = 'Opening browser...';
    dom.loginStatus.className = 'settings-status';

    try {
        await ensureConnected();
        const data = await sendCommand('start_login');
        // Open auth URL in default browser via Tauri shell plugin
        const { open } = window.__TAURI__.shell;
        await open(data.auth_url);
        dom.loginStatus.textContent = 'Waiting for login in browser...';
    } catch (err) {
        if (err.message === 'Not connected') {
            dom.loginStatus.textContent = 'Backend not connected. Start the backend (python -m backend.main) and try again.';
        } else {
            dom.loginStatus.textContent = 'Error: ' + err.message;
        }
        dom.loginStatus.className = 'settings-status error';
        dom.btnLogin.disabled = false;
    }
}

async function doLogout() {
    try {
        await sendCommand('logout');
        dom.oauthLoggedOut.classList.remove('hidden');
        dom.oauthLoggedIn.classList.add('hidden');
        dom.loginStatus.textContent = 'Logged out';
        dom.loginStatus.className = 'settings-status';
    } catch (err) {
        console.error('[Settings] Logout failed:', err);
    }
}

function renderProjectList(projects, activeProject) {
    // Settings dropdown (full detail with chunk counts)
    dom.projectSelect.innerHTML = '<option value="">No project</option>';
    for (const p of projects) {
        const opt = document.createElement('option');
        opt.value = p.name;
        opt.textContent = p.name + (p.chunk_count != null ? ' (' + p.chunk_count + ' chunks)' : '');
        if (p.name === activeProject) opt.selected = true;
        dom.projectSelect.appendChild(opt);
    }

    // Header dropdown (compact)
    dom.headerProject.innerHTML = '<option value="">No project</option>';
    for (const p of projects) {
        const opt = document.createElement('option');
        opt.value = p.name;
        opt.textContent = p.name;
        if (p.name === activeProject) opt.selected = true;
        dom.headerProject.appendChild(opt);
    }
    dom.headerProject.classList.toggle('no-project', !activeProject);
}

async function switchProject() {
    const name = dom.projectSelect.value;
    if (!name) return;

    try {
        await sendCommand('switch_project', { name });
        // Sync header dropdown
        dom.headerProject.value = name;
        dom.headerProject.classList.toggle('no-project', !name);
        refreshDocList();
    } catch (err) {
        console.error('[Settings] Switch project failed:', err);
    }
}

async function headerSwitchProject() {
    const name = dom.headerProject.value;
    try {
        await sendCommand('switch_project', { name });
        // Sync settings dropdown
        dom.projectSelect.value = name;
        dom.headerProject.classList.toggle('no-project', !name);
    } catch (err) {
        console.error('[Header] Switch project failed:', err);
    }
}

async function createProject() {
    const name = dom.newProjectName.value.trim();
    if (!name) return;

    try {
        const data = await sendCommand('create_project', { name });
        dom.newProjectName.value = '';
        dom.createProjectForm.classList.add('hidden');

        // Refresh list and select new project
        renderProjectList(data.projects || [], name);

        // Auto-switch to it
        await sendCommand('switch_project', { name });
        refreshDocList();
    } catch (err) {
        console.error('[Settings] Create project failed:', err);
    }
}

async function deleteProject() {
    const name = dom.projectSelect.value;
    if (!name) return;

    if (!confirm('Delete project "' + name + '" and all its documents?')) return;

    try {
        const data = await sendCommand('delete_project', { name });
        renderProjectList(data.projects || [], '');
        refreshDocList();
    } catch (err) {
        console.error('[Settings] Delete project failed:', err);
    }
}

// --- Document Management ---
async function refreshDocList() {
    try {
        const data = await sendCommand('list_docs');
        dom.docList.innerHTML = '';
        const docs = data.docs || [];
        if (docs.length === 0) {
            const li = document.createElement('li');
            li.className = 'empty-msg';
            li.textContent = 'No documents ingested';
            dom.docList.appendChild(li);
        } else {
            for (const d of docs) {
                // Back-compat: server used to return string titles
                const title = (typeof d === 'string') ? d : d.title;
                const description = (typeof d === 'string') ? '' : (d.description || '');
                const priority = (typeof d === 'string') ? 'normal' : (d.priority || 'normal');

                const li = document.createElement('li');

                const titleSpan = document.createElement('span');
                titleSpan.className = 'doc-title';
                titleSpan.textContent = title;

                const sizeSpan = document.createElement('span');
                sizeSpan.className = 'doc-size';
                if (typeof d !== 'string' && d.size_bytes) {
                    const kb = Math.round(d.size_bytes / 1024);
                    sizeSpan.textContent = kb + ' KB';
                } else {
                    sizeSpan.textContent = '—';
                }

                const statusDot = document.createElement('span');
                statusDot.className = 'doc-status-dot ' + ((typeof d !== 'string' && d.indexed) ? 'indexed' : 'missing');
                statusDot.title = (typeof d !== 'string' && d.indexed) ? 'Indexed' : 'Not indexed';

                const descInput = document.createElement('input');
                descInput.className = 'doc-desc';
                descInput.type = 'text';
                descInput.placeholder = 'Description (one line)';
                descInput.value = description;

                const prSelect = document.createElement('select');
                prSelect.className = 'doc-priority';
                for (const pr of ['high', 'normal', 'low']) {
                    const opt = document.createElement('option');
                    opt.value = pr;
                    opt.textContent = pr;
                    if (pr === priority) opt.selected = true;
                    prSelect.appendChild(opt);
                }

                // Debounced save helper
                let saveTimer = null;
                function scheduleSave() {
                    if (saveTimer) clearTimeout(saveTimer);
                    saveTimer = setTimeout(async () => {
                        try {
                            await sendCommand('update_doc_meta', {
                                title,
                                description: descInput.value,
                                priority: prSelect.value,
                            });
                        } catch (err) {
                            console.error('[Settings] update_doc_meta failed:', err);
                        }
                    }, 400);
                }

                descInput.addEventListener('input', scheduleSave);
                prSelect.addEventListener('change', scheduleSave);

                const btn = document.createElement('button');
                btn.textContent = 'Delete';
                btn.className = 'btn-danger';
                btn.addEventListener('click', () => deleteDoc(title));

                li.appendChild(statusDot);
                li.appendChild(titleSpan);
                li.appendChild(sizeSpan);
                li.appendChild(descInput);
                li.appendChild(prSelect);
                li.appendChild(btn);
                dom.docList.appendChild(li);
            }
        }
    } catch (err) {
        console.error('[Settings] List docs failed:', err);
    }
}

async function deleteDoc(title) {
    if (!confirm('Delete "' + title + '" from the project?')) return;

    try {
        await sendCommand('delete_doc', { title });
        // Server response shape changed (strings -> objects). Re-use the canonical renderer.
        refreshDocList();
    } catch (err) {
        console.error('[Settings] Delete doc failed:', err);
    }
}

// --- Prep Mode ---
async function refreshPrep() {
    if (!dom.prepList) return;
    try {
        const data = await sendCommand('get_prep_results');
        state.prepQuestions = data.questions || [];
        state.prepResults = data.results || {};
        renderPrepList();
    } catch (err) {
        // Quietly ignore if backend doesn't support yet
        console.debug('[Prep] refresh failed:', err.message);
    }
}

function renderPrepList() {
    dom.prepList.innerHTML = '';
    const qs = state.prepQuestions || [];
    if (qs.length === 0) {
        const li = document.createElement('li');
        li.className = 'empty-msg';
        li.textContent = 'No prep questions yet';
        dom.prepList.appendChild(li);
        return;
    }

    for (const q of qs) {
        const li = document.createElement('li');
        li.className = 'prep-item';

        const qSpan = document.createElement('span');
        qSpan.className = 'prep-q';
        qSpan.textContent = q;

        const btnAsk = document.createElement('button');
        btnAsk.textContent = 'Ask';
        btnAsk.className = 'btn-secondary';
        btnAsk.addEventListener('click', async () => {
            // Push into manual override and trigger synthesis
            if (dom.quickQuestion) dom.quickQuestion.value = q;
            try {
                await sendCommand('set_question', { text: q });
            } catch (err) {
                console.error('[Prep] Ask failed:', err);
            }
        });

        li.appendChild(qSpan);
        li.appendChild(btnAsk);

        const ans = state.prepResults ? state.prepResults[q] : null;
        if (ans && ans.one_liner) {
            const a = document.createElement('div');
            a.className = 'prep-a';
            a.textContent = ans.one_liner;
            li.appendChild(a);
        }

        dom.prepList.appendChild(li);
    }
}

async function generatePrep() {
    dom.btnGeneratePrep.disabled = true;
    dom.btnGeneratePrep.textContent = 'Generating...';
    try {
        const data = await sendCommand('generate_prep_questions', { count: 12 });
        state.prepQuestions = data.questions || [];
        state.prepResults = {};
        renderPrepList();
    } catch (err) {
        console.error('[Prep] generate failed:', err);
    } finally {
        dom.btnGeneratePrep.disabled = false;
        dom.btnGeneratePrep.textContent = 'Generate Prep Questions';
    }
}

async function addPrepQuestion() {
    const text = (dom.prepQuestionInput.value || '').trim();
    if (!text) return;
    dom.btnAddPrep.disabled = true;
    try {
        const data = await sendCommand('add_prep_question', { text });
        state.prepQuestions = data.questions || [];
        state.prepResults = data.results || {};
        dom.prepQuestionInput.value = '';
        renderPrepList();
    } catch (err) {
        console.error('[Prep] add failed:', err);
    } finally {
        dom.btnAddPrep.disabled = false;
    }
}

// --- File Picker ---
async function pickFiles() {
    try {
        const { open } = window.__TAURI__.dialog;
        const selected = await open({
            multiple: true,
            filters: [{
                name: 'Documents',
                extensions: ['pdf', 'docx', 'md', 'html', 'htm', 'txt'],
            }],
        });
        if (selected) {
            const paths = Array.isArray(selected) ? selected : [selected];
            if (paths.length > 0) startIngestion(paths);
        }
    } catch (err) {
        console.error('[Settings] File picker failed:', err);
    }
}

async function pickFolder() {
    try {
        const { open } = window.__TAURI__.dialog;
        const selected = await open({ directory: true });
        if (selected) {
            startIngestion([selected]);
        }
    } catch (err) {
        console.error('[Settings] Folder picker failed:', err);
    }
}

async function addUrl() {
    const url = (dom.urlInput.value || '').trim();
    if (!url) return;
    
    // Basic URL validation
    if (!url.match(/^https?:\/\/.+/)) {
        alert('Please enter a valid URL starting with http:// or https://');
        return;
    }
    
    try {
        dom.urlInput.value = '';
        startIngestion([url]);
    } catch (err) {
        console.error('[Settings] Add URL failed:', err);
        alert('Failed to add URL: ' + err.message);
    }
}

async function startIngestion(paths) {
    dom.ingestProgress.classList.remove('hidden');
    dom.progressFill.style.width = '0%';
    dom.progressText.textContent = 'Starting ingestion...';
    dom.btnAddFiles.disabled = true;
    dom.btnAddFolder.disabled = true;

    try {
        await sendCommand('ingest_files', { paths });
    } catch (err) {
        dom.progressText.textContent = 'Error: ' + err.message;
        dom.btnAddFiles.disabled = false;
        dom.btnAddFolder.disabled = false;
    }
}

function renderIngestProgress(data) {
    dom.ingestProgress.classList.remove('hidden');
    const pct = Math.round((data.current / data.total) * 100);
    dom.progressFill.style.width = pct + '%';
    dom.progressText.textContent = 'Ingesting ' + data.file + ' (' + data.current + '/' + data.total + ')';
}

function renderIngestComplete(data) {
    dom.progressFill.style.width = '100%';
    const errCount = (data.errors || []).length;
    if (errCount > 0) {
        dom.progressText.textContent = 'Done: ' + data.total_chunks + ' chunks, ' + errCount + ' errors';
    } else {
        dom.progressText.textContent = 'Done: ' + data.total_chunks + ' chunks from ' + data.file_count + ' files';
    }
    dom.btnAddFiles.disabled = false;
    dom.btnAddFolder.disabled = false;

    // Hide progress after 3s
    setTimeout(() => {
        dom.ingestProgress.classList.add('hidden');
    }, 3000);

    // Refresh doc list and project list
    refreshDocList();
    loadSettings();
    refreshPrep();
}

// --- WebSocket ---
let reconnectDelay = RECONNECT_DELAY_MS;
let reconnectTimer = null;

let _reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;

function connectWebSocket() {
    setConnectionStatus('connecting');

    const ws = new WebSocket(WS_URL);
    state.ws = ws;

    ws.onopen = async () => {
        console.log('[WS] Connected');
        setConnectionStatus('connected');
        reconnectDelay = RECONNECT_DELAY_MS;
        // Load project list into header dropdown on connect
        try {
            const data = await sendCommand('get_settings');
            renderProjectList(data.projects || [], data.active_project || '');
        } catch (err) {
            console.error('[WS] Failed to load projects on connect:', err);
        }

        // Best-effort: load pinned answers
        try {
            const data = await sendCommand('get_pinned');
            state.pinnedAnswers = data.pinned || [];
            renderPinnedAnswers();
        } catch (err) {
            console.debug('[Pinned] get_pinned not available:', err.message);
        }
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleMessage(msg);
        } catch (err) {
            console.error('[WS] Parse error:', err);
        }
    };

    ws.onclose = () => {
        setConnectionStatus('disconnected');
        state.connected = false;
        state.ws = null;

        // Reject all pending commands
        for (const [id, { reject }] of _pendingCommands) {
            reject(new Error('Connection lost'));
        }
        _pendingCommands.clear();

        scheduleReconnect();
    };

    ws.onerror = () => {
        ws.close();
    };
}

function scheduleReconnect() {
    if (reconnectTimer) return;

    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectWebSocket();
        reconnectDelay = Math.min(reconnectDelay * 1.5, MAX_RECONNECT_DELAY_MS);
    }, reconnectDelay);
}

function handleMessage(msg) {
    // Route command responses
    if (msg.type === 'response' && msg.id) {
        const pending = _pendingCommands.get(msg.id);
        if (pending) {
            _pendingCommands.delete(msg.id);
            if (msg.success) {
                pending.resolve(msg.data || {});
            } else {
                pending.reject(new Error(msg.error || 'Command failed'));
            }
        }
        return;
    }

    // Ingestion progress events
    if (msg.type === 'ingest_progress') {
        renderIngestProgress(msg);
        return;
    }
    if (msg.type === 'ingest_complete') {
        renderIngestComplete(msg);
        return;
    }

    // OAuth events
    if (msg.type === 'auth_complete') {
        dom.oauthLoggedOut.classList.add('hidden');
        dom.oauthLoggedIn.classList.remove('hidden');
        dom.oauthEmail.textContent = (msg.oauth_status && msg.oauth_status.email) || 'Logged in';
        dom.loginStatus.textContent = '';
        dom.btnLogin.disabled = false;
        return;
    }
    if (msg.type === 'auth_error') {
        dom.loginStatus.textContent = msg.error || 'Login failed';
        dom.loginStatus.className = 'settings-status error';
        dom.btnLogin.disabled = false;
        return;
    }
    if (msg.type === 'auth_logout') {
        dom.oauthLoggedOut.classList.remove('hidden');
        dom.oauthLoggedIn.classList.add('hidden');
        return;
    }

    // Handle synthesis searching event
    if (msg.type === 'synthesis_searching') {
        state.synthesisSearching = true;
        state.streamingAnswer = null;
        renderSearchingState(true);
        return;
    }
    if (msg.type === 'synthesis_error') {
        state.synthesisSearching = false;
        state.streamingAnswer = null;
        renderSearchingState(false);
        return;
    }

    // Handle streaming partial answer updates
    if (msg.type === 'answer_partial') {
        if (!state.pinned) {
            state.streamingAnswer = msg.partial_text || '';
            renderStreamingAnswer(state.streamingAnswer);
        }
        return;
    }

    // Handle answer_update independently (no version check)
    if (msg.type === 'answer_update') {
        state.synthesisSearching = false;
        state.streamingAnswer = null;
        renderSearchingState(false);
        if (msg.active_answer && !state.pinned) {
            state.activeAnswer = msg.active_answer;
            renderAnswer(msg.active_answer);
        }
        return;
    }

    if (msg.version <= state.version && msg.type !== 'snapshot') {
        return;
    }

    state.version = msg.version;
    state.segments = msg.segments || [];
    if (state.segments.length > 0) {
        state.lastTranscriptAtMs = Date.now();
    }

    // Update question history
    if (msg.question_history) {
        state.questionHistory = msg.question_history;
        dom.qhCount.textContent = msg.question_history.length;
        if (state.historyOpen) {
            renderQuestionHistory();
        }
    }

    // Update Q&A history (question + answer pairs)
    if (msg.qa_history) {
        state.qaHistory = msg.qa_history;
        renderQaHistory();
    }

    // Track manual mode
    state.manualQuestion = !!msg.manual_question;
    dom.btnAutoQuestion.classList.toggle('active', !state.manualQuestion);
    document.body.classList.toggle('manual-question', state.manualQuestion);

    // If manual mode turned off by server (e.g., timeout), clear the quick input
    if (!state.manualQuestion && dom.quickQuestion && dom.quickQuestion.value) {
        dom.quickQuestion.value = '';
    }

    // Pinned answers
    if (msg.pinned) {
        state.pinnedAnswers = msg.pinned;
        renderPinnedAnswers();
    }

    // Update synthesis searching state
    if (msg.synthesis_searching !== undefined) {
        state.synthesisSearching = msg.synthesis_searching;
        renderSearchingState(msg.synthesis_searching);
    }

    // Update active question if changed
    const question = msg.active_question || null;
    if (question !== state.activeQuestion) {
        state.activeQuestion = question;
        if (!state.pinned) {
            renderQuestion(question);
        }
    }

    // Update answer if present in message
    if (msg.active_answer) {
        state.activeAnswer = msg.active_answer;
        if (!state.pinned) {
            renderAnswer(msg.active_answer);
        }
        // Refresh bookmark button state
        renderPinnedAnswers();
    }

    if (!state.pinned) {
        renderTranscript();
    }
}

function escapeHtml(s) {
    return String(s || '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

// --- Rendering ---
function _splitSentences(text) {
    if (!text) return [];
    // Simple heuristic split; good enough for display anchoring.
    return text
        .split(/(?<=[.!?])\s+/)
        .map((s) => s.trim())
        .filter(Boolean);
}

function renderTranscript() {
    const segments = state.pinned ? state.pinnedSegments : state.segments;
    if (!segments) return;

    // Flatten segments to sentences
    const sentences = [];
    for (const seg of segments) {
        for (const s of _splitSentences(seg.text)) sentences.push(s);
    }

    // Quiet state
    const now = Date.now();
    const last = state.lastTranscriptAtMs || 0;
    const quiet = sentences.length === 0 || (now - last) > 3000;
    if (dom.transcriptQuiet) dom.transcriptQuiet.classList.toggle('hidden', !quiet);

    // Render as stacked lines with recency-based opacity
    dom.transcriptContent.innerHTML = '';
    const total = sentences.length;
    for (let i = 0; i < total; i++) {
        const line = document.createElement('div');
        line.className = 'transcript-line';
        line.textContent = sentences[i];

        // Last 2–3 sentences at full opacity, older fade toward ~0.4.
        const age = total - 1 - i;
        let opacity = 1.0;
        if (age >= 3) {
            // Map older lines to [0.4..0.9] range
            const t = Math.min(1, (age - 3) / 14);
            opacity = 0.9 - 0.5 * t;
            opacity = Math.max(0.4, opacity);
        }
        line.style.opacity = String(opacity);

        dom.transcriptContent.appendChild(line);
    }

    if (!state.pinned) {
        requestAnimationFrame(() => {
            dom.transcriptScroll.scrollTop = dom.transcriptScroll.scrollHeight;
        });
    }
}

function setConnectionStatus(status) {
    state.connected = status === 'connected';
    dom.connectionStatus.textContent =
        status === 'connected'
            ? 'Connected'
            : status === 'connecting'
              ? 'Connecting...'
              : 'Disconnected';
    dom.connectionStatus.className = status;

    // Settings drawer: backend status indicator
    if (dom.backendStatus) {
        if (state.connected) {
            dom.backendStatus.textContent = 'Backend: Connected';
            dom.backendStatus.className = 'settings-status ok';
            if (dom.backendHint) dom.backendHint.classList.add('hidden');
        } else if (status === 'connecting') {
            dom.backendStatus.textContent = 'Backend: Starting...';
            dom.backendStatus.className = 'settings-status';
            if (dom.backendHint) dom.backendHint.classList.add('hidden');
        } else {
            dom.backendStatus.textContent = 'Backend: Disconnected';
            dom.backendStatus.className = 'settings-status error';
            if (dom.backendHint) dom.backendHint.classList.remove('hidden');
        }
    }

    // Disable login when backend isn't reachable
    if (dom.btnLogin) {
        dom.btnLogin.disabled = !state.connected;
        if (!state.connected && state.settingsOpen && dom.loginStatus && !dom.loginStatus.textContent) {
            dom.loginStatus.textContent = 'Backend not connected.';
            dom.loginStatus.className = 'settings-status error';
        }
    }
}

function renderQuestion(questionText) {
    dom.questionText.textContent = questionText || 'Listening...';
    dom.questionText.classList.toggle('placeholder', !questionText);
    document.body.classList.toggle('has-question', !!questionText);
}

function renderSearchingState(searching) {
    dom.answerSearching.classList.toggle('hidden', !searching);
    if (searching && !state.streamingAnswer) {
        dom.answerText.classList.add('hidden');
    } else {
        dom.answerText.classList.remove('hidden');
    }
}

function renderStreamingAnswer(partialText) {
    if (!partialText) return;
    dom.answerText.textContent = partialText;
    dom.answerText.classList.remove('placeholder');
    dom.answerText.classList.add('streaming');
    // Show searching indicator while streaming
    dom.answerSearching.classList.remove('hidden');
}

function toggleQuestionHistory() {
    state.historyOpen = !state.historyOpen;
    dom.questionHistoryPanel.classList.toggle('hidden', !state.historyOpen);
    dom.btnQuestionHistory.classList.toggle('active', state.historyOpen);
    if (state.historyOpen) {
        renderQuestionHistory();
    }
}

function renderQuestionHistory() {
    dom.questionHistoryList.innerHTML = '';
    // Show ranked questions (already sorted by score from backend, top-N)
    const items = state.questionHistory || [];
    if (items.length === 0) {
        const li = document.createElement('li');
        li.textContent = 'No questions detected yet';
        li.style.color = '#555';
        li.style.fontStyle = 'italic';
        li.style.cursor = 'default';
        dom.questionHistoryList.appendChild(li);
        return;
    }
    for (const q of items) {
        const li = document.createElement('li');
        
        // Add rank indicator (1, 2, 3...)
        const rankSpan = document.createElement('span');
        rankSpan.className = 'qh-rank';
        rankSpan.textContent = (items.indexOf(q) + 1) + '.';
        li.appendChild(rankSpan);
        
        const textSpan = document.createElement('span');
        textSpan.textContent = q.text;
        if (q.text === state.activeQuestion) {
            li.classList.add('selected');
        }
        if (q.stale) {
            li.classList.add('stale');
        }
        li.appendChild(textSpan);
        
        // Show score if available
        if (q.score != null) {
            const scoreSpan = document.createElement('span');
            scoreSpan.className = 'qh-score';
            scoreSpan.textContent = q.score.toFixed(1);
            li.appendChild(scoreSpan);
        }
        
        li.addEventListener('click', () => selectQuestion(q.text));
        dom.questionHistoryList.appendChild(li);
    }
}

function renderQaHistory() {
    if (!dom.qaHistoryList) return;
    dom.qaHistoryList.innerHTML = '';

    const items = [...state.qaHistory].reverse();
    if (items.length === 0) {
        const li = document.createElement('li');
        li.textContent = 'No Q&A yet';
        li.style.color = '#555';
        li.style.fontStyle = 'italic';
        li.style.cursor = 'default';
        dom.qaHistoryList.appendChild(li);
        return;
    }

    for (const item of items) {
        const li = document.createElement('li');

        const qDiv = document.createElement('div');
        qDiv.className = 'qa-question';
        qDiv.textContent = item.question || 'Unknown question';

        const aDiv = document.createElement('div');
        aDiv.className = 'qa-answer-preview';
        const preview = item.answer && item.answer.one_liner
            ? item.answer.one_liner
            : (item.answer && item.answer.bullets && item.answer.bullets[0]) || '';
        aDiv.textContent = preview;

        li.appendChild(qDiv);
        li.appendChild(aDiv);

        li.addEventListener('click', () => {
            if (item.question) {
                renderQuestion(item.question);
            }
            if (item.answer) {
                renderAnswer(item.answer);
            }
        });

        dom.qaHistoryList.appendChild(li);
    }
}

async function selectQuestion(text) {
    try {
        await sendCommand('select_question', { text });
        state.manualQuestion = true;
        document.body.classList.add('manual-question');
        dom.btnAutoQuestion.classList.remove('active');
        // Sync quick input
        if (dom.quickQuestion) dom.quickQuestion.value = text || '';
        renderQuestion(text);
        renderQuestionHistory();
    } catch (err) {
        console.error('[Question] Select failed:', err);
    }
}

let _quickQuestionTimer = null;
async function setManualQuestionFromInput(immediate = false) {
    if (!dom.quickQuestion) {
        console.warn('[Question] quickQuestion DOM element not found');
        return;
    }
    const text = dom.quickQuestion.value.trim();

    // Don't send empty questions (unless explicitly clearing)
    if (!text) {
        // If empty, clear manual override
        try {
            await sendCommand('set_question', { text: '' });
            state.manualQuestion = false;
            document.body.classList.remove('manual-question');
            dom.btnAutoQuestion.classList.add('active');
        } catch (err) {
            console.error('[Question] set_question failed:', err);
        }
        return;
    }

    // Clear any pending debounce
    if (_quickQuestionTimer) {
        clearTimeout(_quickQuestionTimer);
        _quickQuestionTimer = null;
    }
    
    // Immediate UI feedback - show the question right away
    renderQuestion(text);
    state.manualQuestion = true;
    document.body.classList.add('manual-question');
    dom.btnAutoQuestion.classList.remove('active');
    
    // If immediate (Enter key), send right away; otherwise debounce (blur)
    const sendCommandNow = async () => {
        try {
            console.log('[Question] Sending set_question command:', text);
            const result = await sendCommand('set_question', { text });
            console.log('[Question] set_question succeeded:', result);
            // Server will send update message with synthesis results
        } catch (err) {
            console.error('[Question] set_question failed:', err);
            // Revert UI state on error
            state.manualQuestion = false;
            document.body.classList.remove('manual-question');
            dom.btnAutoQuestion.classList.add('active');
            renderQuestion(null);
        }
    };
    
    if (immediate) {
        await sendCommandNow();
    } else {
        // Debounce for blur events to avoid rapid-fire requests
        _quickQuestionTimer = setTimeout(sendCommandNow, 150);
    }
}

async function resumeAutoQuestion() {
    if (!state.manualQuestion) return;
    try {
        await sendCommand('select_question', {});
        state.manualQuestion = false;
        document.body.classList.remove('manual-question');
        dom.btnAutoQuestion.classList.add('active');
        if (dom.quickQuestion) dom.quickQuestion.value = '';
    } catch (err) {
        console.error('[Question] Resume auto failed:', err);
    }
}

function isActiveAnswerPinned() {
    const q = state.activeQuestion;
    if (!q) return false;
    return (state.pinnedAnswers || []).some((p) => p.question === q);
}

async function bookmarkActiveAnswer() {
    const question = state.activeQuestion;
    const answer = state.activeAnswer;
    if (!question || !answer) return;

    try {
        const data = await sendCommand('pin_answer', { question, answer });
        state.pinnedAnswers = data.pinned || [];
        renderPinnedAnswers();
    } catch (err) {
        console.error('[Pinned] pin_answer failed:', err);
    }
}

async function unbookmarkAnswer(id) {
    try {
        const data = await sendCommand('unpin_answer', { id });
        state.pinnedAnswers = data.pinned || [];
        renderPinnedAnswers();
    } catch (err) {
        console.error('[Pinned] unpin_answer failed:', err);
    }
}

function renderPinnedAnswers() {
    if (!dom.pinnedSection || !dom.pinnedList) return;

    const items = state.pinnedAnswers || [];
    dom.pinnedSection.classList.toggle('hidden', items.length === 0);
    dom.pinnedList.innerHTML = '';

    for (const p of items) {
        const li = document.createElement('li');
        li.className = 'pinned-item';

        const q = document.createElement('div');
        q.className = 'pinned-q';
        q.textContent = p.question || '';

        const a = document.createElement('div');
        a.className = 'pinned-a';
        a.textContent = (p.answer && p.answer.one_liner) ? p.answer.one_liner : '';

        const row = document.createElement('div');
        row.className = 'pinned-actions';

        const btnRecall = document.createElement('button');
        btnRecall.className = 'btn-secondary';
        btnRecall.textContent = 'Recall';
        btnRecall.addEventListener('click', async () => {
            // Set manual question and render answer immediately from cached pinned data
            if (dom.quickQuestion) dom.quickQuestion.value = p.question || '';
            try {
                await sendCommand('set_question', { text: p.question || '' });
            } catch (err) {
                console.error('[Pinned] recall set_question failed:', err);
            }
            if (p.answer) {
                state.activeAnswer = p.answer;
                renderAnswer(p.answer);
            }
        });

        const btnUnpin = document.createElement('button');
        btnUnpin.className = 'btn-danger';
        btnUnpin.textContent = 'Unpin';
        btnUnpin.addEventListener('click', () => unbookmarkAnswer(p.id));

        row.appendChild(btnRecall);
        row.appendChild(btnUnpin);

        li.appendChild(q);
        if (a.textContent) li.appendChild(a);
        li.appendChild(row);

        dom.pinnedList.appendChild(li);
    }

    // Update bookmark button state
    if (dom.btnBookmark) {
        dom.btnBookmark.classList.toggle('active', isActiveAnswerPinned());
        dom.btnBookmark.textContent = isActiveAnswerPinned() ? 'Bookmarked' : 'Bookmark';
    }
}

function renderAnswer(data) {
    if (!data) return;

    // Clear streaming state
    state.streamingAnswer = null;
    dom.answerText.classList.remove('streaming');
    dom.answerSearching.classList.add('hidden');

    // Apply confidence-based styling
    const confidence = data.confidence || 0.0;
    dom.answer.classList.remove('confidence-high', 'confidence-medium', 'confidence-low');
    if (confidence > 0.6) {
        dom.answer.classList.add('confidence-high');
    } else if (confidence >= 0.3) {
        dom.answer.classList.add('confidence-medium');
    } else {
        dom.answer.classList.add('confidence-low');
    }

    // Show "not found" hint when confidence is 0 and no evidence bullets
    const noResults = !data.one_liner && (data.bullets || []).length === 0;
    const lowConfidence = data.confidence === 0 && (data.bullets || []).length === 0;

    // Render one-liner
    if (lowConfidence && data.one_liner) {
        dom.answerText.textContent = data.one_liner;
        dom.answerText.classList.remove('placeholder');
    } else {
        dom.answerText.textContent = data.one_liner || 'Waiting for question...';
        dom.answerText.classList.toggle('placeholder', !data.one_liner);
    }
    
    // Add confidence warning label if confidence is low
    let warningLabel = dom.answer.querySelector('.confidence-warning');
    if (confidence < 0.3 && data.one_liner) {
        if (!warningLabel) {
            warningLabel = document.createElement('span');
            warningLabel.className = 'confidence-warning';
            warningLabel.textContent = 'Low Confidence';
            // Insert after the answer text paragraph
            dom.answerText.parentNode.insertBefore(warningLabel, dom.answerText.nextSibling);
        }
    } else if (warningLabel) {
        warningLabel.remove();
    }

    // Evidence-backed bullets
    dom.bulletList.innerHTML = '';
    if (lowConfidence) {
        const li = document.createElement('li');
        li.className = 'not-found-hint';
        li.textContent = 'No matching information found in project sources';
        dom.bulletList.appendChild(li);
    }
    (data.bullets || []).forEach((b) => {
        const li = document.createElement('li');
        li.textContent = b;
        dom.bulletList.appendChild(li);
    });

    // Best practice bullets (not from sources)
    const bpBullets = data.best_practice_bullets || [];
    dom.bestPracticeList.innerHTML = '';
    bpBullets.forEach((b) => {
        const li = document.createElement('li');
        li.textContent = b;
        dom.bestPracticeList.appendChild(li);
    });
    dom.bestPracticeSection.classList.toggle('hidden', bpBullets.length === 0);

    // Clarifiers
    dom.clarifierList.innerHTML = '';
    (data.clarifiers || []).forEach((c) => {
        const li = document.createElement('li');
        li.textContent = c;
        dom.clarifierList.appendChild(li);
    });
    dom.clarifierSection.classList.toggle('hidden', (data.clarifiers || []).length === 0);

    // Citations as pills with hover popover
    if (dom.citationPills) {
        dom.citationPills.innerHTML = '';
        (data.citations || []).forEach((c, idx) => {
            const pill = document.createElement('button');
            pill.className = 'citation-pill';
            pill.type = 'button';

            const labelParts = [c.doc, c.page ? 'p.' + c.page : ''].filter(Boolean);
            pill.textContent = labelParts.join(' · ') || ('Citation ' + (idx + 1));

            pill.addEventListener('mouseenter', (e) => {
                if (!dom.citationPopover) return;
                const parts = [c.doc, c.section, c.page ? 'p.' + c.page : ''].filter(Boolean);
                const header = parts.join(' — ');
                const quote = c.quote ? ('"' + c.quote + '"') : '';
                dom.citationPopover.innerHTML = `<div class="cp-title">${escapeHtml(header)}</div><div class="cp-quote">${escapeHtml(quote)}</div>`;
                dom.citationPopover.classList.remove('hidden');

                const rect = e.target.getBoundingClientRect();
                dom.citationPopover.style.left = Math.max(12, rect.left) + 'px';
                dom.citationPopover.style.top = (rect.top - 10) + 'px';
            });
            pill.addEventListener('mouseleave', () => {
                if (!dom.citationPopover) return;
                dom.citationPopover.classList.add('hidden');
            });

            dom.citationPills.appendChild(pill);
        });
    }
}