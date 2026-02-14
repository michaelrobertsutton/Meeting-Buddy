import SwiftUI
import AppKit

extension Notification.Name {
    static let meetingBuddyHUDHide = Notification.Name("MeetingBuddyHUD.Hide")
}

@main
struct MeetingBuddyHUDApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        // No visible window from SwiftUI — NSPanel is managed by AppDelegate
        Settings {
            EmptyView()
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

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Hide dock icon (menu bar app / accessory)
        NSApp.setActivationPolicy(.accessory)

        // Connect to backend
        ws.connect()

        // Show HUD immediately
        hudController.show {
            ContentView(ws: ws)
        }

        // Toolbar "Hide" button posts this; we hide the panel
        hideObserver = NotificationCenter.default.addObserver(
            forName: .meetingBuddyHUDHide,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.hudController.hide()
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
            self?.handleSettingsHotkey(event)
            return event
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let observer = hideObserver {
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

    private func handleSettingsHotkey(_ event: NSEvent) {
        guard event.modifierFlags.contains(.command) else { return }
        guard let chars = event.charactersIgnoringModifiers else { return }
        guard chars == "," else { return }

        DispatchQueue.main.async {
            try? SettingsLauncher.launch()
        }
    }

    private func toggleHUD() {
        hudController.toggle {
            ContentView(ws: ws)
        }
    }
}
