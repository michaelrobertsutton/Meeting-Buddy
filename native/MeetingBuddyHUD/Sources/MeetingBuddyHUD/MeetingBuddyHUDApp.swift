import SwiftUI
import AppKit

extension Notification.Name {
    static let meetingBuddyHUDHide = Notification.Name("MeetingBuddyHUD.Hide")
    /// Sent by the toolbar pin button to toggle the window's always-on-top state.
    static let meetingBuddyHUDToggleWindowPin = Notification.Name("MeetingBuddyHUD.ToggleWindowPin")
    static let meetingBuddyHUDOpenSettings = Notification.Name("MeetingBuddyHUD.OpenSettings")
}

@main
struct MeetingBuddyHUDApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

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
    private var settingsHotkeyLocalMonitor: Any?
    private var hideObserver: NSObjectProtocol?
    private var windowPinObserver: NSObjectProtocol?
    private var openSettingsObserver: NSObjectProtocol?
    private var commandServer: HudCommandServer?

    private func persistedFloatingState() -> Bool {
        if UserDefaults.standard.object(forKey: HUDPanelController.windowFloatingKey) == nil {
            return true
        }
        return UserDefaults.standard.bool(forKey: HUDPanelController.windowFloatingKey)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Best-effort backend launch (no-op if backend already running or sidecar not found)
        BackendLauncher.launchIfAvailable()

        // Connect to backend
        ws.connect()

        // Show HUD immediately (pinned on first launch, then persist user pin state)
        let initialFloating = persistedFloatingState()
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

        openSettingsObserver = NotificationCenter.default.addObserver(
            forName: .meetingBuddyHUDOpenSettings,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.openSettings()
        }

        // Register global hotkey (Alt+Space) only when Accessibility is already granted.
        // Avoid triggering the macOS permission prompt on every app launch.
        let accessibilityGranted = AXIsProcessTrusted()
        if accessibilityGranted {
            hotkey = GlobalHotkey { [weak self] in
                self?.toggleHUD()
            }
            hotkey?.register()
        }

        commandServer = HudCommandServer { [weak self] command in
            self?.handleExternalCommand(command)
        }
        commandServer?.start()

        // Cmd+, opens Settings when this app is active.
        settingsHotkeyLocalMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            self?.handleKeyDown(event) ?? event
        }
    }

    // Re-show HUD when user clicks dock icon or re-opens the app.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        if !hasVisibleWindows || !hudController.isVisible {
            let initialFloating = persistedFloatingState()
            hudController.show(initialFloating: initialFloating) {
                ContentView(ws: ws)
            }
            ws.isWindowFloating = initialFloating
        }
        return true
    }

    /// Called when the user Cmd+Tabs to us or clicks the dock icon.
    func applicationDidBecomeActive(_ notification: Notification) {
        restoreHUD()
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let observer = hideObserver {
            NotificationCenter.default.removeObserver(observer)
        }
        if let observer = windowPinObserver {
            NotificationCenter.default.removeObserver(observer)
        }
        if let observer = openSettingsObserver {
            NotificationCenter.default.removeObserver(observer)
        }
        hotkey?.unregister()
        commandServer?.stop()
        commandServer = nil
        if let monitor = settingsHotkeyLocalMonitor {
            NSEvent.removeMonitor(monitor)
            settingsHotkeyLocalMonitor = nil
        }
        ws.disconnect()
    }

    private func handleExternalCommand(_ command: HudIPCCommand) {
        switch command {
        case .toggleHUD:
            toggleHUD()
        case .hideHUD:
            hudController.hide()
        case .restoreHUD:
            restoreHUD(externalRequest: true)
        case .openSettings:
            openSettings()
        }
    }

    /// Handle key down; return nil to consume the event, or the event to pass through.
    private func handleKeyDown(_ event: NSEvent) -> NSEvent? {
        // Alt+Space toggle — must check before the .command guard
        if event.keyCode == 49 && event.modifierFlags.contains(.option)
            && !event.modifierFlags.contains(.command) {
            DispatchQueue.main.async { [weak self] in
                self?.toggleHUD()
            }
            return nil
        }

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
            DispatchQueue.main.async { [weak self] in
                self?.openSettings()
            }
            return nil
        }
        return event
    }

    private func openSettings() {
        do {
            try SettingsLauncher.launch()
            hudController.hide()
        } catch {
            ws.lastError = error.localizedDescription
        }
    }

    private func toggleHUD() {
        let floating = persistedFloatingState()
        if hudController.isVisible {
            if NSApp.isActive && hudController.isKeyWindow {
                hudController.hide()
            } else {
                hudController.orderFront()
            }
        } else {
            hudController.show(initialFloating: floating) {
                ContentView(ws: ws)
            }
            ws.isWindowFloating = floating
        }
    }

    private func restoreHUD(externalRequest: Bool = false) {
        if externalRequest && SettingsLauncher.isSettingsFrontmost() {
            return
        }

        let floating = persistedFloatingState()
        if hudController.isVisible {
            hudController.orderFront()
        } else {
            hudController.show(initialFloating: floating) { ContentView(ws: self.ws) }
            ws.isWindowFloating = floating
        }
    }
}
