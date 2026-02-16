import SwiftUI
import AppKit

extension Notification.Name {
    static let meetingBuddySettingsShowWindow = Notification.Name("MeetingBuddySettings.ShowWindow")
}

@MainActor
final class SettingsAppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private let store = SettingsStore()
    private var window: NSWindow?
    private var showObserver: NSObjectProtocol?

    func applicationDidFinishLaunching(_ notification: Notification) {
        showObserver = DistributedNotificationCenter.default().addObserver(
            forName: .meetingBuddySettingsShowWindow,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.showSettingsWindow()
            }
        }

        ensureWindow()
        showSettingsWindow()

        store.start()
        Task {
            await store.fetchSettings()
            await store.fetchDocs()
            await store.fetchAudioStatus()
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let observer = showObserver {
            DistributedNotificationCenter.default().removeObserver(observer)
            showObserver = nil
        }
        store.stop()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showSettingsWindow()
        return true
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        // Keep a single settings window instance alive; close behaves like hide.
        sender.orderOut(nil)
        return false
    }

    private func ensureWindow() {
        if window != nil {
            return
        }

        let settingsWindow = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 860, height: 600),
            styleMask: [.titled, .closable, .resizable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        settingsWindow.title = "Meeting Buddy Settings"
        settingsWindow.minSize = NSSize(width: 700, height: 500)
        settingsWindow.isReleasedWhenClosed = false
        settingsWindow.delegate = self
        settingsWindow.setFrameAutosaveName("MeetingBuddySettings.MainWindow")
        settingsWindow.contentView = NSHostingView(
            rootView: SettingsWindow()
                .environmentObject(store)
        )

        window = settingsWindow
    }

    private func showSettingsWindow() {
        ensureWindow()
        guard let window else { return }
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }
}

// @main removed — entry point is main.swift, which sets activation policy
// before NSApplicationMain runs so the dock icon never appears.
struct MeetingBuddySettingsApp: App {
    @NSApplicationDelegateAdaptor(SettingsAppDelegate.self) var appDelegate

    var body: some Scene {
        // No SwiftUI-managed WindowGroup: AppDelegate owns a single NSWindow instance
        // so show/hide behavior is deterministic and relaunch is never required.
        Settings {
            EmptyView()
        }
        .commandsRemoved()
    }
}
