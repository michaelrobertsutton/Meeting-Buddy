use std::sync::Mutex;
use tauri::{Emitter, Manager};
use tauri_plugin_shell::ShellExt;

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

            // --- Spawn the Python backend sidecar ---
            match app.shell().sidecar("meeting-buddy-backend") {
                Ok(command) => match command.spawn() {
                    Ok((mut rx, child)) => {
                        log::info!("Backend sidecar spawned");
                        app.manage(BackendChild(Mutex::new(Some(child))));

                        // Drain stdout/stderr in a background task
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
                                        log::info!("[backend:err] {}", s.trim());
                                    }
                                    CommandEvent::Terminated(payload) => {
                                        log::info!(
                                            "[backend] terminated (code={:?}, signal={:?})",
                                            payload.code,
                                            payload.signal
                                        );
                                        break;
                                    }
                                    _ => {}
                                }
                            }
                        });
                    }
                    Err(e) => {
                        log::warn!("[meeting-buddy] Failed to spawn backend sidecar: {e}");
                        log::warn!("[meeting-buddy] Run the backend manually: python -m backend.main");
                        app.manage(BackendChild(Mutex::new(None)));
                    }
                },
                Err(e) => {
                    log::warn!("[meeting-buddy] Backend sidecar not found: {e}");
                    log::warn!("[meeting-buddy] Run the backend manually: python -m backend.main");
                    app.manage(BackendChild(Mutex::new(None)));
                }
            }

            #[cfg(desktop)]
            {
                use tauri_plugin_global_shortcut::{
                    Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState,
                };

                let toggle_shortcut =
                    Shortcut::new(Some(Modifiers::META | Modifiers::SHIFT), Code::KeyM);
                let pin_shortcut =
                    Shortcut::new(Some(Modifiers::META | Modifiers::SHIFT), Code::KeyP);

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
                                        let _ = window.set_focus();
                                    }
                                }
                            } else if shortcut == &pin_shortcut {
                                if let Some(window) = app_handle.get_webview_window("overlay") {
                                    let _ = window.emit("toggle-pin", ());
                                }
                            }
                        })
                        .build(),
                )?;

                app.global_shortcut().register(toggle_shortcut)?;
                app.global_shortcut().register(pin_shortcut)?;
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
