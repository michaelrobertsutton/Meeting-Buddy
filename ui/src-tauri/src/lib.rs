use std::sync::Mutex;

use serde::Serialize;
use tauri::Emitter;
use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

/// Holds the settings sidecar child process so we can kill it before re-launching.
struct SettingsChild(Mutex<Option<CommandChild>>);

/// Holds the native HUD sidecar child process so we can kill it to hide.
struct HudChild(Mutex<Option<CommandChild>>);

/// Holds the backend sidecar child process so we can kill it on app exit.
struct BackendChild(Mutex<Option<CommandChild>>);

#[derive(Debug, Clone, Serialize, Default)]
struct BackendDiagnostics {
    ready_seen: bool,
    last_exit_code: Option<i32>,
    last_exit_signal: Option<i32>,
    last_spawn_error: Option<String>,
    stderr_tail: Vec<String>,
}

/// In-memory diagnostics for the backend sidecar.
struct BackendDiagState(Mutex<BackendDiagnostics>);

#[tauri::command]
fn get_backend_diagnostics(state: tauri::State<'_, BackendDiagState>) -> BackendDiagnostics {
    state.0.lock().unwrap().clone()
}

/// Kill any existing sidecar in `state`, then spawn `name` and store the child.
/// Returns Ok(()) on success, Err with message on failure.
fn spawn_sidecar(
    app: &tauri::AppHandle,
    name: &str,
    state: &Mutex<Option<CommandChild>>,
) -> Result<(), String> {
    if let Some(old) = state.lock().unwrap().take() {
        let _ = old.kill();
        // Intentionally avoid sleeping here: this function may be called from UI event handlers.
        // If we need a delay to avoid races, handle it asynchronously at the call site.
    }
    match app.shell().sidecar(name) {
        Ok(cmd) => match cmd.spawn() {
            Ok((_rx, child)) => {
                *state.lock().unwrap() = Some(child);
                Ok(())
            }
            Err(e) => Err(format!("Failed to spawn {name}: {e}")),
        },
        Err(e) => Err(format!("Sidecar {name} not found: {e}")),
    }
}

/// Spawn a sidecar if it's not already running.
///
/// Used for Settings to avoid repeatedly launching additional instances.
fn ensure_sidecar_running(
    app: &tauri::AppHandle,
    name: &str,
    state: &Mutex<Option<CommandChild>>,
) -> Result<(), String> {
    if state.lock().unwrap().is_some() {
        // Best-effort: if it's already running, do nothing.
        // (No reliable "focus" API for raw sidecar executables.)
        return Ok(());
    }

    match app.shell().sidecar(name) {
        Ok(cmd) => match cmd.spawn() {
            Ok((_rx, child)) => {
                *state.lock().unwrap() = Some(child);
                Ok(())
            }
            Err(e) => Err(format!("Failed to spawn {name}: {e}")),
        },
        Err(e) => Err(format!("Sidecar {name} not found: {e}")),
    }
}

#[tauri::command]
fn get_backend_url() -> String {
    "ws://localhost:8765".to_string()
}

#[tauri::command]
fn open_settings_window(app: tauri::AppHandle) -> Result<(), String> {
    use tauri::WebviewWindowBuilder;
    // Close any existing settings window first
    if let Some(w) = app.get_webview_window("settings") {
        let _ = w.close();
    }
    WebviewWindowBuilder::new(&app, "settings", tauri::WebviewUrl::App("settings.html".into()))
        .title("Meeting Buddy Settings")
        .inner_size(860.0, 600.0)
        .resizable(true)
        .decorations(true)
        .build()
        .map_err(|e| {
            log::error!("[settings] failed to open window: {e}");
            e.to_string()
        })?;
    Ok(())
}

#[tauri::command]
fn dismiss_onboarding() -> Result<(), String> {
    // This command can be called from anywhere to dismiss the onboarding overlay

    Ok(())
}

/// Open a URL (e.g. System Settings deep link) via macOS `open` command.
/// Used for onboarding "Open System Settings" so it works reliably from native.

#[tauri::command]
fn open_system_settings_url(url: String) -> Result<(), String> {
    std::process::Command::new("open")
        .arg(&url)
        .status()
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[cfg(target_os = "macos")]
#[tauri::command]
fn check_screen_recording_permission() -> bool {
    // Use CoreGraphics API to check Screen Recording permission

    // Note: This may return false even after permission is granted until app restart

    // Returns true if permission is granted, false otherwise

    unsafe {
        #[link(name = "CoreGraphics", kind = "framework")]
        extern "C" {
            fn CGPreflightScreenCaptureAccess() -> bool;
        }

        CGPreflightScreenCaptureAccess()
    }
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
fn check_screen_recording_permission() -> bool {
    // Not macOS, assume permission granted (or not applicable)

    true
}

/// Microphone permission check (optional for onboarding).
/// On macOS we could use AVFoundation; for now return true so we don't block.

#[cfg(target_os = "macos")]
#[tauri::command]
fn check_microphone_permission() -> bool {
    // TODO: Use AVFoundation AVCaptureDevice::authorizationStatus(for: .audio)

    // For now assume granted so onboarding doesn't block; mic is optional.

    true
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
fn check_microphone_permission() -> bool {
    true
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()

        .setup(|app| {
            app.handle().plugin(

                tauri_plugin_log::Builder::default()

                    .level(log::LevelFilter::Info)

                    .build(),

            )?;

            // NOTE: The legacy Tauri overlay window has been retired in favor of the native

            // SwiftUI/AppKit HUD sidecar (MeetingBuddyHUD). Tauri acts as a headless process

            // manager and tray host.

            // --- Spawn the Python backend sidecar ---

            app.manage(BackendDiagState(Mutex::new(BackendDiagnostics::default())));

            let app_handle = app.handle().clone();

            let shell = app.shell();

            // Try to spawn with retry logic

            let mut retries = 3;

            let mut spawned = false;

            while retries > 0 && !spawned {
                match shell.sidecar("meeting-buddy-backend") {
                    Ok(command) => {
                        match command.spawn() {
                            Ok((mut rx, child)) => {
                                log::info!("Backend sidecar spawned successfully");

                                // Reset diagnostics on a fresh spawn.
                                if let Some(diag) = app.try_state::<BackendDiagState>() {
                                    let mut d = diag.0.lock().unwrap();
                                    *d = BackendDiagnostics::default();
                                }

                                app.manage(BackendChild(Mutex::new(Some(child))));

                                spawned = true;

                                // Drain stdout/stderr in a background task

                                let app_handle_clone = app_handle.clone();

                                tauri::async_runtime::spawn(async move {
                                    use tauri_plugin_shell::process::CommandEvent;

                                    while let Some(event) = rx.recv().await {
                                        match event {
                                            CommandEvent::Stdout(line) => {
                                                let s = String::from_utf8_lossy(&line);
                                                if s.contains("MEETING_BUDDY_READY") {
                                                    if let Some(diag) = app_handle_clone.try_state::<BackendDiagState>() {
                                                        let mut d = diag.0.lock().unwrap();
                                                        d.ready_seen = true;
                                                        d.last_spawn_error = None;
                                                    }
                                                    let _ = app_handle_clone.emit("backend-ready", ());
                                                }
                                                log::info!("[backend] {}", s.trim());
                                            }

                                            CommandEvent::Stderr(line) => {
                                                let s = String::from_utf8_lossy(&line);

                                                let text = s.trim().to_string();

                                                if let Some(diag) = app_handle_clone.try_state::<BackendDiagState>() {
                                                    let mut d = diag.0.lock().unwrap();
                                                    d.stderr_tail.push(text.clone());
                                                    let len = d.stderr_tail.len();
                                                    if len > 50 {
                                                        let _ = d.stderr_tail.drain(0..(len - 50));
                                                    }
                                                }

                                                // Log errors at error level, others at info
                                                if text.contains("ERROR") || text.contains("error:") {
                                                    log::error!("[backend:err] {}", text);
                                                } else {
                                                    log::info!("[backend:err] {}", text);
                                                }
                                            }

                                            CommandEvent::Terminated(payload) => {
                                                log::warn!(
                                                    "[backend] terminated (code={:?}, signal={:?})",
                                                    payload.code,
                                                    payload.signal
                                                );

                                                let snapshot = if let Some(diag) = app_handle_clone.try_state::<BackendDiagState>() {
                                                    let mut d = diag.0.lock().unwrap();
                                                    d.last_exit_code = payload.code;
                                                    d.last_exit_signal = payload.signal;
                                                    d.clone()
                                                } else {
                                                    BackendDiagnostics {
                                                        ready_seen: false,
                                                        last_exit_code: payload.code,
                                                        last_exit_signal: payload.signal,
                                                        last_spawn_error: None,
                                                        stderr_tail: vec![],
                                                    }
                                                };

                                                let _ = app_handle_clone.emit("backend-terminated", snapshot);
                                                
                                                // Optional restart: try once after short delay (let port release)

                                                let app_handle_restart = app_handle_clone.clone();

                                                tauri::async_runtime::spawn(async move {
                                                    let _ = tauri::async_runtime::spawn_blocking(|| {
                                                        std::thread::sleep(std::time::Duration::from_millis(500));

                                                    })

                                                    .await;

                                                    if let Ok(cmd) = app_handle_restart.shell().sidecar("meeting-buddy-backend") {
                                                        if let Ok((mut rx2, child2)) = cmd.spawn() {
                                                            if let Some(backend_state) = app_handle_restart.try_state::<BackendChild>() {
                                                                *backend_state.0.lock().unwrap() = Some(child2);

                                                                log::info!("Backend sidecar restarted after crash");

                                                                let _app_handle_drain = app_handle_restart.clone();

                                                                tauri::async_runtime::spawn(async move {
                                                                    use tauri_plugin_shell::process::CommandEvent;

                                                                    while let Some(event) = rx2.recv().await {
                                                                        match event {
                                                                            CommandEvent::Stdout(line) => {
                                                                                let s = String::from_utf8_lossy(&line);
                                                                                if s.contains("MEETING_BUDDY_READY") {
                                                                                    if let Some(diag) = _app_handle_drain.try_state::<BackendDiagState>() {
                                                                                        let mut d = diag.0.lock().unwrap();
                                                                                        d.ready_seen = true;
                                                                                        d.last_spawn_error = None;
                                                                                    }
                                                                                    let _ = _app_handle_drain.emit("backend-ready", ());
                                                                                }
                                                                                log::info!("[backend] {}", s.trim());
                                                                            }

                                                                            CommandEvent::Stderr(line) => {
                                                                                let s = String::from_utf8_lossy(&line);
                                                                                let text = s.trim().to_string();
                                                                                if let Some(diag) = _app_handle_drain.try_state::<BackendDiagState>() {
                                                                                    let mut d = diag.0.lock().unwrap();
                                                                                    d.stderr_tail.push(text.clone());
                                                                                    let len = d.stderr_tail.len();
                                                                                    if len > 50 {
                                                                                        let _ = d.stderr_tail.drain(0..(len - 50));
                                                                                    }
                                                                                }
                                                                                if text.contains("ERROR") || text.contains("error:") {
                                                                                    log::error!("[backend:err] {}", text);
                                                                                } else {
                                                                                    log::info!("[backend:err] {}", text);
                                                                                }
                                                                            }

                                                                            CommandEvent::Terminated(payload) => {
                                                                                log::warn!(
                                                                                    "[backend] terminated again (code={:?}, signal={:?})",
                                                                                    payload.code,
                                                                                    payload.signal
                                                                                );
                                                                                let snapshot = if let Some(diag) = _app_handle_drain.try_state::<BackendDiagState>() {
                                                                                    let mut d = diag.0.lock().unwrap();
                                                                                    d.last_exit_code = payload.code;
                                                                                    d.last_exit_signal = payload.signal;
                                                                                    d.clone()
                                                                                } else {
                                                                                    BackendDiagnostics {
                                                                                        ready_seen: false,
                                                                                        last_exit_code: payload.code,
                                                                                        last_exit_signal: payload.signal,
                                                                                        last_spawn_error: None,
                                                                                        stderr_tail: vec![],
                                                                                    }
                                                                                };
                                                                                let _ = _app_handle_drain.emit("backend-terminated", snapshot);
                                                                                break;
                                                                            }

                                                                            _ => {}
                                                                        }
                                                                    }
                                                                });
                                                            }
                                                        }
                                                    }
                                                });

                                                break;
                                            }

                                            _ => {}
                                        }
                                    }
                                });
                            }

                            Err(e) => {
                                retries -= 1;

                                if retries > 0 {
                                    log::warn!("[meeting-buddy] Failed to spawn backend sidecar (retries left: {}): {e}", retries);

                                    // Wait a bit before retrying

                                    std::thread::sleep(std::time::Duration::from_millis(500));

                                } else {
                                    log::error!("[meeting-buddy] Failed to spawn backend sidecar after retries: {e}");

                                    log::error!("[meeting-buddy] Check that:");

                                    log::error!("[meeting-buddy]   1. MEETINGBUDDY_PROJECT_ROOT is set to the repo root");

                                    log::error!("[meeting-buddy]   2. .venv directory exists at PROJECT_ROOT/.venv");

                                    log::error!("[meeting-buddy]   3. AudioCapture binary exists");

                                    if let Some(diag) = app.try_state::<BackendDiagState>() {
                                        let mut d = diag.0.lock().unwrap();
                                        d.last_spawn_error = Some(format!("Failed to spawn backend sidecar: {e}"));
                                    }

                                    if let Some(diag) = app.try_state::<BackendDiagState>() {
                                        let snapshot = diag.0.lock().unwrap().clone();
                                        let _ = app_handle.emit("backend-terminated", snapshot);
                                    }

                                    app.manage(BackendChild(Mutex::new(None)));
                                }
                            }
                        }
                    }

                    Err(e) => {
                        retries -= 1;

                        if retries > 0 {
                            log::warn!("[meeting-buddy] Backend sidecar binary not found (retries left: {}): {e}", retries);

                            std::thread::sleep(std::time::Duration::from_millis(500));

                        } else {
                            log::error!("[meeting-buddy] Backend sidecar binary not found after retries: {e}");

                            log::error!("[meeting-buddy] This usually means the app bundle is incomplete.");

                            log::error!("[meeting-buddy] Rebuild with: cd ui && npm run tauri build");

                            if let Some(diag) = app.try_state::<BackendDiagState>() {
                                let mut d = diag.0.lock().unwrap();
                                d.last_spawn_error = Some(format!("Backend sidecar binary not found: {e}"));
                            }

                            if let Some(diag) = app.try_state::<BackendDiagState>() {
                                let snapshot = diag.0.lock().unwrap().clone();
                                let _ = app_handle.emit("backend-terminated", snapshot);
                            }

                            app.manage(BackendChild(Mutex::new(None)));
                        }
                    }
                }
            }

            // Register sidecar child states

            app.manage(SettingsChild(Mutex::new(None)));

            app.manage(HudChild(Mutex::new(None)));

            // Spawn native HUD sidecar on startup (best-effort)
            let app_handle = app.handle();
            if let Some(state) = app_handle.try_state::<HudChild>() {
                #[allow(clippy::needless_borrow)]
                if let Err(e) = spawn_sidecar(&app_handle, "MeetingBuddyHUD", &state.0) {
                    log::error!("[hud] {e}");
                }
            }

            #[cfg(desktop)]
            {
                use tauri_plugin_global_shortcut::{
                    Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState,

                };

                let toggle_shortcut = Shortcut::new(Some(Modifiers::ALT), Code::Space);
                let focus_shortcut = Shortcut::new(Some(Modifiers::META), Code::KeyK);

                let app_handle = app.handle().clone();

                app.handle().plugin(

                    tauri_plugin_global_shortcut::Builder::new()

                        .with_handler(move |_app, shortcut, event| {
                            if event.state() != ShortcutState::Pressed {
                                return;
                            }

                            if shortcut == &toggle_shortcut {
                                // Alt+Space always brings HUD to front: kill any existing
                                // instance (buried or visible) and spawn fresh so the new
                                // window calls makeKeyAndOrderFront and appears on top.
                                if let Some(state) = app_handle.try_state::<HudChild>() {
                                    if let Some(old_child) = state.0.lock().unwrap().take() {
                                        let _ = old_child.kill();
                                    }
                                    #[allow(clippy::needless_borrow)]
                                    if let Err(e) = spawn_sidecar(&app_handle, "MeetingBuddyHUD", &state.0) {
                                        log::error!("[hud] {e}");
                                    }
                                }
                            } else if shortcut == &focus_shortcut {
                                // Cmd+K: focus the question input in all webview windows
                                for window in app_handle.webview_windows().values() {
                                    let _ = window.emit("focus-question", ());
                                }
                            }

                        })

                        .build(),

                )?;

                app.global_shortcut().register(toggle_shortcut)?;
                app.global_shortcut().register(focus_shortcut)?;

            }

            // --- Menu bar tray icon (Issue #101) ---

            #[cfg(desktop)]
            {
                use tauri::menu::{Menu, MenuItem};

                use tauri::tray::TrayIconBuilder;

                let toggle_item = MenuItem::with_id(app, "toggle_hud", "Toggle HUD", true, Some("Alt+Space"))?;

                let hide_item = MenuItem::with_id(app, "hide_hud", "Hide Meeting Buddy", true, Some("Cmd+H"))?;

                let settings_item = MenuItem::with_id(app, "open_settings", "Open Settings", true, Some("Cmd+,"))?;

                let export_item = MenuItem::with_id(app, "export", "Export", true, None::<&str>)?;

                let quit_item = MenuItem::with_id(app, "quit", "Quit Meeting Buddy", true, None::<&str>)?;

                let menu = Menu::with_items(app, &[&toggle_item, &hide_item, &settings_item, &export_item, &quit_item])?;

                let _app_handle = app.handle().clone();

                let _tray = TrayIconBuilder::new()

                    .icon(app.default_window_icon().unwrap().clone())

                    .menu(&menu)

                    .show_menu_on_left_click(true)

                    .tooltip("Meeting Buddy")

                    .on_menu_event(move |app_handle, event| {
                        match event.id.as_ref() {
                            "toggle_hud" => {
                                // Same as Alt+Space: kill-and-respawn to bring to front.
                                if let Some(state) = app_handle.try_state::<HudChild>() {
                                    if let Some(old_child) = state.0.lock().unwrap().take() {
                                        let _ = old_child.kill();
                                    }
                                    #[allow(clippy::needless_borrow)]
                                    if let Err(e) = spawn_sidecar(&app_handle, "MeetingBuddyHUD", &state.0) {
                                        log::error!("[hud] {e}");
                                    }
                                }
                            }
                            "open_settings" => {
                                if let Err(e) = open_settings_window(app_handle.clone()) {
                                    log::error!("[settings] tray: {e}");
                                }
                            }

                            "hide_hud" => {
                                if let Some(state) = app_handle.try_state::<HudChild>() {
                                    if let Some(child) = state.0.lock().unwrap().take() {
                                        let _ = child.kill();
                                    }
                                }
                            }

                            "export" => {
                                // TODO: implement export once native HUD exposes an IPC hook.

                                log::info!("[tray] export clicked (not yet implemented for native HUD)");
                            }

                            "quit" => {
                                app_handle.exit(0);
                            }

                            _ => {}
                        }

                    })

                    .build(app)?;
            }

            Ok(())

        })

        .plugin(tauri_plugin_dialog::init())

        .plugin(tauri_plugin_shell::init())

        .invoke_handler(tauri::generate_handler![get_backend_url, get_backend_diagnostics, check_screen_recording_permission, check_microphone_permission, dismiss_onboarding, open_system_settings_url, open_settings_window])

        .build(tauri::generate_context!())

        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            // Kill the backend sidecar on app exit and wait briefly so it can release the port

            if let Some(state) = app_handle.try_state::<BackendChild>() {
                if let Some(child) = state.0.lock().unwrap().take() {
                    log::info!("Killing backend sidecar");

                    let _ = child.kill();

                    std::thread::sleep(std::time::Duration::from_millis(300));
                }
            }

            // Kill settings sidecar on app exit

            if let Some(state) = app_handle.try_state::<SettingsChild>() {
                if let Some(child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();

                    std::thread::sleep(std::time::Duration::from_millis(150));
                }
            }

            // Kill HUD sidecar on app exit

            if let Some(state) = app_handle.try_state::<HudChild>() {
                if let Some(child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        }
    });
}
