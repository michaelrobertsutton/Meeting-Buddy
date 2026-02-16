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
    private var toggleSignalSource: DispatchSourceSignal?
    private var hideSignalSource: DispatchSourceSignal?

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

        // Register global hotkey (Alt+Space) only when Accessibility is already granted.
        // Avoid triggering the macOS permission prompt on every app launch.
        let accessibilityGranted = AXIsProcessTrusted()
        if accessibilityGranted {
            hotkey = GlobalHotkey { [weak self] in
                self?.toggleHUD()
            }
            hotkey?.register()
        }

        // Listen for Unix signals from the Tauri tray host.
        // SIGUSR1 = toggle panel, SIGUSR2 = hide panel.
        signal(SIGUSR1, SIG_IGN)
        toggleSignalSource = DispatchSource.makeSignalSource(signal: SIGUSR1, queue: .main)
        toggleSignalSource?.setEventHandler { [weak self] in
            self?.toggleHUD()
        }
        toggleSignalSource?.resume()

        signal(SIGUSR2, SIG_IGN)
        hideSignalSource = DispatchSource.makeSignalSource(signal: SIGUSR2, queue: .main)
        hideSignalSource?.setEventHandler { [weak self] in
            self?.hudController.hide()
        }
        hideSignalSource?.resume()

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
        let floating = persistedFloatingState()
        if hudController.isVisible {
            hudController.orderFront()
        } else {
            hudController.show(initialFloating: floating) { ContentView(ws: self.ws) }
            ws.isWindowFloating = floating
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
        toggleSignalSource?.cancel()
        hideSignalSource?.cancel()
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
            DispatchQueue.main.async {
                try? SettingsLauncher.launch()
            }
            return nil
        }
        return event
    }

    private func handleSettingsHotkey(_ event: NSEvent) {
        // Global monitor fires when another app is active — only handle Cmd+,
        // (open settings). Never handle Cmd+H here: that would hide the HUD
        // every time the user presses Cmd+H in Safari, Finder, etc.
        guard event.modifierFlags.contains(.command),
              let chars = event.charactersIgnoringModifiers,
              chars == "," else { return }
        DispatchQueue.main.async {
            try? SettingsLauncher.launch()
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
}
