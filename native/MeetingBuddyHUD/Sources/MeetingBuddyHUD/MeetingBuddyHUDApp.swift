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
    private var settingsHotkeyMonitor: Any?
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
        settingsHotkeyMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { event in
            // keyCode 43 = comma; Command modifier
            guard event.keyCode == 43, event.modifierFlags.contains(.command) else { return }
            DispatchQueue.main.async {
                try? SettingsLauncher.launch()
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let observer = hideObserver {
            NotificationCenter.default.removeObserver(observer)
        }
        hotkey?.unregister()
        if let monitor = settingsHotkeyMonitor {
            NSEvent.removeMonitor(monitor)
            settingsHotkeyMonitor = nil
        }
        ws.disconnect()
    }

    private func toggleHUD() {
        hudController.toggle {
            ContentView(ws: ws)
        }
    }
}
