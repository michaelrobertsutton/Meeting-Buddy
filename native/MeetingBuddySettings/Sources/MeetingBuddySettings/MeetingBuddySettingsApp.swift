import SwiftUI
import AppKit

@main
struct MeetingBuddySettingsApp: App {

    @StateObject private var store = SettingsStore()

    var body: some Scene {
        WindowGroup("Meeting Buddy Settings") {
            SettingsWindow()
                .environmentObject(store)
                .onAppear {
                    store.start()
                    // When launched via Process.run() the app is not the active foreground app.
                    // Activate here (window is already created) so it comes to front.
                    NSApp?.activate(ignoringOtherApps: true)
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
