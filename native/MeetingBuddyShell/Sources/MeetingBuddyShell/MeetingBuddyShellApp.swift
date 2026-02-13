import SwiftUI

@main
struct MeetingBuddyShellApp: App {
    @StateObject private var ws = WebSocketClient()
    private let hud = HUDPanelController()

    var body: some Scene {
        // No default window; we show an NSPanel HUD.
        Settings {
            EmptyView()
        }
        .commands {
            CommandGroup(replacing: .appInfo) {
                Button("Show HUD") {
                    hud.show {
                        ContentView(ws: ws)
                    }
                }
            }
        }

        // Start connection when app launches
        // (SwiftUI doesn't give a simple "didFinishLaunching" here; keep it simple.)
        WindowGroup {
            EmptyView()
                .onAppear {
                    ws.connect()
                    hud.show { ContentView(ws: ws) }
                }
        }
    }
}
