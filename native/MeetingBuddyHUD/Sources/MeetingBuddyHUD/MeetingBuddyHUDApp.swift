import SwiftUI
import AppKit

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

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Hide dock icon (menu bar app / accessory)
        NSApp.setActivationPolicy(.accessory)

        // Connect to backend
        ws.connect()

        // Show HUD immediately
        hudController.show {
            ContentView(ws: ws)
        }

        // Register global hotkey (Alt+Space)
        hotkey = GlobalHotkey { [weak self] in
            self?.toggleHUD()
        }
        hotkey?.register()
    }

    func applicationWillTerminate(_ notification: Notification) {
        hotkey?.unregister()
        ws.disconnect()
    }

    private func toggleHUD() {
        hudController.toggle {
            ContentView(ws: ws)
        }
    }
}
