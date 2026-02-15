import SwiftUI
import AppKit

final class SettingsAppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Suppress dock icon — Settings is a transient panel, not a standalone app.
        NSApp.setActivationPolicy(.accessory)
        // Bring to front after suppressing dock presence.
        NSApp.activate(ignoringOtherApps: true)
    }
}

@main
struct MeetingBuddySettingsApp: App {
    @NSApplicationDelegateAdaptor(SettingsAppDelegate.self) var appDelegate
    @StateObject private var store = SettingsStore()

    var body: some Scene {
        WindowGroup("Meeting Buddy Settings") {
            SettingsWindow()
                .environmentObject(store)
                .onAppear {
                    store.start()
                    Task {
                        await store.fetchSettings()
                        await store.fetchDocs()
                    }
                }
                .onDisappear {
                    store.stop()
                }
        }
        .windowResizability(.contentSize)
        .commandsRemoved()
    }
}
