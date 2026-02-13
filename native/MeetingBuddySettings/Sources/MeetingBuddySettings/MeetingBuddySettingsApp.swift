import SwiftUI

@main
struct MeetingBuddySettingsApp: App {

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
