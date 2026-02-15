import SwiftUI
import AppKit

final class SettingsAppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Bring to front (activation policy already set in App.init).
        NSApp.activate(ignoringOtherApps: true)
    }
}

// @main removed — entry point is main.swift, which sets activation policy
// before NSApplicationMain runs so the dock icon never appears.
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
