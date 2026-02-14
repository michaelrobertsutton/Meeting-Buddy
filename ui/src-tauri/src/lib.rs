use std::sync::Mutex;

use tauri::{Emitter, Manager};

use tauri_plugin_shell::ShellExt;



/// Holds the settings sidecar child process so we can kill it before re-launching.

struct SettingsChild(Mutex<Option<tauri_plugin_shell::process::CommandChild>>);



/// Holds the native HUD sidecar child process so we can kill it to hide.

struct HudChild(Mutex<Option<tauri_plugin_shell::process::CommandChild>>);



#[cfg(target_os = "macos")]

use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial};



/// Holds the backend sidecar child process so we can kill it on app exit.

struct BackendChild(Mutex<Option<tauri_plugin_shell::process::CommandChild>>);



#[tauri::command]

fn get_backend_url() -> String {

    "ws://localhost:8765".to_string()

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

                                                // TODO: surface backend termination state to native HUD

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

                                                                let app_handle_drain = app_handle_restart.clone();

                                                                tauri::async_runtime::spawn(async move {

                                                                    use tauri_plugin_shell::process::CommandEvent;

                                                                    while let Some(event) = rx2.recv().await {

                                                                        match event {

                                                                            CommandEvent::Stdout(line) => {

                                                                                let s = String::from_utf8_lossy(&line);

                                                                                log::info!("[backend] {}", s.trim());

                                                                            }

                                                                            CommandEvent::Stderr(line) => {

                                                                                let s = String::from_utf8_lossy(&line);

                                                                                let text = s.trim();

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

                                                                                // TODO: surface backend termination state to native HUD

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



            // Register sidecar child states

            app.manage(SettingsChild(Mutex::new(None)));

            app.manage(HudChild(Mutex::new(None)));



            // Spawn native HUD sidecar on startup (best-effort)

            match app.handle().shell().sidecar("MeetingBuddyHUD") {

                Ok(cmd) => match cmd.spawn() {

                    Ok((_rx, child)) => {

                        if let Some(state) = app.handle().try_state::<HudChild>() {

                            *state.0.lock().unwrap() = Some(child);

                        }

                    }

                    Err(e) => log::error!("[hud] Failed to spawn: {e}"),

                },

                Err(e) => log::error!("[hud] Sidecar not found: {e}"),

            }



            #[cfg(desktop)]

            {

                use tauri_plugin_global_shortcut::{

                    Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState,

                };



                let toggle_shortcut = Shortcut::new(Some(Modifiers::ALT), Code::Space);

                let settings_shortcut = Shortcut::new(Some(Modifiers::META), Code::Comma);



                let app_handle = app.handle().clone();



                app.handle().plugin(

                    tauri_plugin_global_shortcut::Builder::new()

                        .with_handler(move |_app, shortcut, event| {

                            if event.state() != ShortcutState::Pressed {

                                return;

                            }



                            if shortcut == &toggle_shortcut {

                                // Toggle HUD sidecar visibility.

                                // For now, we model "hide" as kill and "show" as spawn.

                                if let Some(state) = app_handle.try_state::<HudChild>() {

                                    if let Some(old_child) = state.0.lock().unwrap().take() {

                                        let _ = old_child.kill();

                                    } else {

                                        match app_handle.shell().sidecar("MeetingBuddyHUD") {

                                            Ok(cmd) => match cmd.spawn() {

                                                Ok((_rx, child)) => {

                                                    *state.0.lock().unwrap() = Some(child);

                                                }

                                                Err(e) => log::error!("[hud] Failed to spawn: {e}"),

                                            },

                                            Err(e) => log::error!("[hud] Sidecar not found: {e}"),

                                        }

                                    }

                                }

                            } else if shortcut == &settings_shortcut {

                                // Launch native SwiftUI settings app as a sidecar

                                // Kill any existing instance first so only one runs at a time

                                if let Some(state) = app_handle.try_state::<SettingsChild>() {

                                    if let Some(old_child) = state.0.lock().unwrap().take() {

                                        let _ = old_child.kill();

                                        std::thread::sleep(std::time::Duration::from_millis(150));

                                    }

                                }

                                match app_handle.shell().sidecar("MeetingBuddySettings") {

                                    Ok(cmd) => match cmd.spawn() {

                                        Ok((_rx, child)) => {

                                            if let Some(state) = app_handle.try_state::<SettingsChild>() {

                                                *state.0.lock().unwrap() = Some(child);

                                            }

                                        }

                                        Err(e) => log::error!("[settings] Failed to spawn: {e}"),

                                    },

                                    Err(e) => log::error!("[settings] Sidecar not found: {e}"),

                                }

                            }

                        })

                        .build(),

                )?;



                app.global_shortcut().register(toggle_shortcut)?;

                app.global_shortcut().register(settings_shortcut)?;

            }



            // --- Menu bar tray icon (Issue #101) ---

            #[cfg(desktop)]

            {

                use tauri::menu::{Menu, MenuItem};

                use tauri::tray::TrayIconBuilder;



                let toggle_item = MenuItem::with_id(app, "toggle_hud", "Toggle HUD", true, Some("Alt+Space"))?;

                let settings_item = MenuItem::with_id(app, "open_settings", "Open Settings", true, Some("Cmd+,"))?;

                let export_item = MenuItem::with_id(app, "export", "Export", true, None::<&str>)?;

                let quit_item = MenuItem::with_id(app, "quit", "Quit Meeting Buddy", true, None::<&str>)?;



                let menu = Menu::with_items(app, &[&toggle_item, &settings_item, &export_item, &quit_item])?;



                let app_handle = app.handle().clone();

                let _tray = TrayIconBuilder::new()

                    .icon(app.default_window_icon().unwrap().clone())

                    .menu(&menu)

                    .menu_on_left_click(true)

                    .tooltip("Meeting Buddy")

                    .on_menu_event(move |app_handle, event| {

                        match event.id.as_ref() {

                            "toggle_hud" => {

                                if let Some(state) = app_handle.try_state::<HudChild>() {

                                    if let Some(old_child) = state.0.lock().unwrap().take() {

                                        let _ = old_child.kill();

                                    } else {

                                        match app_handle.shell().sidecar("MeetingBuddyHUD") {

                                            Ok(cmd) => match cmd.spawn() {

                                                Ok((_rx, child)) => {

                                                    *state.0.lock().unwrap() = Some(child);

                                                }

                                                Err(e) => log::error!("[hud] Failed to spawn: {e}"),

                                            },

                                            Err(e) => log::error!("[hud] Sidecar not found: {e}"),

                                        }

                                    }

                                }

                            }

                            "open_settings" => {

                                // Kill any existing settings sidecar, then spawn a fresh one

                                if let Some(state) = app_handle.try_state::<SettingsChild>() {

                                    if let Some(old_child) = state.0.lock().unwrap().take() {

                                        let _ = old_child.kill();

                                        std::thread::sleep(std::time::Duration::from_millis(150));

                                    }

                                }

                                match app_handle.shell().sidecar("MeetingBuddySettings") {

                                    Ok(cmd) => match cmd.spawn() {

                                        Ok((_rx, child)) => {

                                            if let Some(state) = app_handle.try_state::<SettingsChild>() {

                                                *state.0.lock().unwrap() = Some(child);

                                            }

                                        }

                                        Err(e) => log::error!("[settings] Failed to spawn: {e}"),

                                    },

                                    Err(e) => log::error!("[settings] Sidecar not found: {e}"),

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

        .invoke_handler(tauri::generate_handler![get_backend_url, check_screen_recording_permission, check_microphone_permission, dismiss_onboarding, open_system_settings_url])

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


