import SwiftUI
import AppKit

extension Notification.Name {
    static let meetingBuddyHUDHide = Notification.Name("MeetingBuddyHUD.Hide")
    /// Sent by the toolbar pin button to toggle the window's always-on-top state.
    static let meetingBuddyHUDToggleWindowPin = Notification.Name("MeetingBuddyHUD.ToggleWindowPin")
}

@main
struct MeetingBuddyHUDApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    init() {
        // Suppress dock icon before the app finishes launching — setting this in
        // applicationDidFinishLaunching is too late and causes a bounce.
        NSApplication.shared.setActivationPolicy(.accessory)
    }

    var body: some Scene {
        // No visible window from SwiftUI — NSPanel is managed by AppDelegate
        Settings {
            EmptyView()
        }
        .commands {
            CommandGroup(after: .appInfo) {
                Button("Hide Meeting Buddy") {
                    NotificationCenter.default.post(name: .meetingBuddyHUDHide, object: nil)
                }
                .keyboardShortcut("h", modifiers: .command)
            }
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let ws = WebSocketClient()
    private let hudController = HUDPanelController()
    private var hotkey: GlobalHotkey?
    private var settingsHotkeyGlobalMonitor: Any?
    private var settingsHotkeyLocalMonitor: Any?
    private var hideObserver: NSObjectProtocol?
    private var windowPinObserver: NSObjectProtocol?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Hide dock icon (menu bar app / accessory)
        NSApp.setActivationPolicy(.accessory)

        // Best-effort backend launch (no-op if backend already running or sidecar not found)
        BackendLauncher.launchIfAvailable()

        // Connect to backend
        ws.connect()

        // Show HUD immediately (unpinned by default; persist last pin state)
        let initialFloating = UserDefaults.standard.bool(forKey: HUDPanelController.windowFloatingKey)
        hudController.show(initialFloating: initialFloating) {
            ContentView(ws: ws)
        }
        ws.isWindowFloating = initialFloating

        // Toolbar "Hide" button posts this; we hide the panel
        hideObserver = NotificationCenter.default.addObserver(
            forName: .meetingBuddyHUDHide,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.hudController.hide()
        }

        // Toolbar pin button toggles window always-on-top state
        windowPinObserver = NotificationCenter.default.addObserver(
            forName: .meetingBuddyHUDToggleWindowPin,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self else { return }
            let newState = !self.ws.isWindowFloating
            self.hudController.setFloating(newState)
            self.ws.isWindowFloating = newState
            UserDefaults.standard.set(newState, forKey: HUDPanelController.windowFloatingKey)
        }

        // Register global hotkey (Alt+Space) to toggle HUD
        hotkey = GlobalHotkey { [weak self] in
            self?.toggleHUD()
        }
        hotkey?.register()

        // Cmd+, opens Settings (same as gear button)
        // Note: Global monitors do NOT receive events when this app is active.
        // Also, keyCode is layout-dependent; prefer charactersIgnoringModifiers.
        settingsHotkeyGlobalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            self?.handleSettingsHotkey(event)
        }
        settingsHotkeyLocalMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            self?.handleKeyDown(event) ?? event
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let observer = hideObserver {
            NotificationCenter.default.removeObserver(observer)
        }
        if let observer = windowPinObserver {
            NotificationCenter.default.removeObserver(observer)
        }
        hotkey?.unregister()
        if let monitor = settingsHotkeyGlobalMonitor {
            NSEvent.removeMonitor(monitor)
            settingsHotkeyGlobalMonitor = nil
        }
        if let monitor = settingsHotkeyLocalMonitor {
            NSEvent.removeMonitor(monitor)
            settingsHotkeyLocalMonitor = nil
        }
        ws.disconnect()
    }

    /// Handle key down; return nil to consume the event, or the event to pass through.
    private func handleKeyDown(_ event: NSEvent) -> NSEvent? {
        guard event.modifierFlags.contains(.command) else { return event }
        guard let chars = event.charactersIgnoringModifiers else { return event }

        if chars == "h" || chars == "H" {
            // Cmd+H — Hide (like standard Mac apps)
            DispatchQueue.main.async { [weak self] in
                self?.hudController.hide()
            }
            return nil
        }
        if chars == "," {
            DispatchQueue.main.async {
                try? SettingsLauncher.launch()
            }
            return nil
        }
        return event
    }

    private func handleSettingsHotkey(_ event: NSEvent) {
        _ = handleKeyDown(event)
    }

    private func toggleHUD() {
        let initialFloating = UserDefaults.standard.bool(forKey: HUDPanelController.windowFloatingKey)
        hudController.toggle(initialFloating: initialFloating) {
            ContentView(ws: ws)
        }
        if hudController.isVisible {
            ws.isWindowFloating = initialFloating
        }
    }
}
