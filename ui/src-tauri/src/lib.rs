use std::sync::Mutex;
use tauri::{Emitter, Manager};
use tauri_plugin_shell::ShellExt;

#[cfg(target_os = "macos")]
use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial};

/// Holds the backend sidecar child process so we can kill it on app exit.
struct BackendChild(Mutex<Option<tauri_plugin_shell::process::CommandChild>>);

#[tauri::command]
fn get_backend_url() -> String {
    "ws://localhost:8765".to_string()
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

            // --- macOS HUD styling: vibrancy (HUD window material) ---
            #[cfg(target_os = "macos")]
            {
                if let Some(window) = app.get_webview_window("overlay") {
                    // Glassy background behind the WebView. Border/radius are handled by CSS.
                    // High-contrast translucent background (UltraThinMaterial Dark-ish)
                    let _ = apply_vibrancy(&window, NSVisualEffectMaterial::UltraThin, None, None);
                }
            }

            // --- Spawn the Python backend sidecar ---
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
                                                log::info!("[backend] {}", s.trim());
                                            }
                                            CommandEvent::Stderr(line) => {
                                                let s = String::from_utf8_lossy(&line);
                                                // Log errors at error level, others at info
                                                let text = s.trim();
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
                                                // Emit event to UI that backend died
                                                if let Some(window) = app_handle_clone.get_webview_window("overlay") {
                                                    let _ = window.emit("backend-terminated", payload.code);
                                                }
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
                            app.manage(BackendChild(Mutex::new(None)));
                        }
                    }
                }
            }

            #[cfg(desktop)]
            {
                use tauri_plugin_global_shortcut::{
                    Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState,
                };

                let toggle_shortcut =
                    Shortcut::new(Some(Modifiers::ALT), Code::Space);
                let pin_shortcut =
                    Shortcut::new(Some(Modifiers::META | Modifiers::SHIFT), Code::KeyP);

                let settings_shortcut =
                    Shortcut::new(Some(Modifiers::META), Code::Comma);
                let clear_shortcut =
                    Shortcut::new(Some(Modifiers::META), Code::KeyK);

                let app_handle = app.handle().clone();

                app.handle().plugin(
                    tauri_plugin_global_shortcut::Builder::new()
                        .with_handler(move |_app, shortcut, event| {
                            if event.state() != ShortcutState::Pressed {
                                return;
                            }

                            if shortcut == &toggle_shortcut {
                                if let Some(window) = app_handle.get_webview_window("overlay") {
                                    if window.is_visible().unwrap_or(false) {
                                        let _ = window.hide();
                                    } else {
                                        let _ = window.show();
                                        // Intentionally do NOT focus the window (non-activating HUD behavior)
                                    }
                                }
                            } else if shortcut == &pin_shortcut {
                                if let Some(window) = app_handle.get_webview_window("overlay") {
                                    let _ = window.emit("toggle-pin", ());
                                }
                            } else if shortcut == &settings_shortcut {
                                if let Some(window) = app_handle.get_webview_window("overlay") {
                                    let _ = window.emit("open-settings", ());
                                }
                            } else if shortcut == &clear_shortcut {
                                if let Some(window) = app_handle.get_webview_window("overlay") {
                                    let _ = window.emit("clear-session", ());
                                }
                            }
                        })
                        .build(),
                )?;

                app.global_shortcut().register(toggle_shortcut)?;
                app.global_shortcut().register(pin_shortcut)?;
                app.global_shortcut().register(settings_shortcut)?;
                app.global_shortcut().register(clear_shortcut)?;
            }

            Ok(())
        })
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![get_backend_url])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            // Kill the backend sidecar on app exit
            if let Some(state) = app_handle.try_state::<BackendChild>() {
                if let Some(child) = state.0.lock().unwrap().take() {
                    log::info!("Killing backend sidecar");
                    let _ = child.kill();
                }
            }
        }
    });
}
