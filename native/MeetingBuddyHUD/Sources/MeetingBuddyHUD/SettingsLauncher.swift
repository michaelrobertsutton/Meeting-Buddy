import Foundation
import AppKit

enum SettingsLauncher {

    private static func bundledSettingsExecutables() -> [URL] {
        guard let hudExe = Bundle.main.executableURL else { return [] }
        let dir = hudExe.deletingLastPathComponent()
        // Try both plain name (bundled .app) and arch-suffixed name (dev sidecar)
        return [
            dir.appendingPathComponent("MeetingBuddySettings"),
            dir.appendingPathComponent("MeetingBuddySettings-aarch64-apple-darwin"),
        ]
    }

    static func launch() throws {
        let logMsg = "[SettingsLauncher] launch() called, cwd=\(FileManager.default.currentDirectoryPath)\n"
        try? logMsg.write(toFile: "/tmp/settings_launcher.log", atomically: false, encoding: .utf8)
        // Single-instance behavior: if Settings is already running, bring it to front.
        // Settings is a raw executable (not necessarily a .app bundle), so we match by executable name.
        let runningSettings = NSWorkspace.shared.runningApplications.filter { app in
            let exe = app.executableURL?.lastPathComponent
            let name = app.localizedName

            if let exe, (exe == "MeetingBuddySettings" || exe.hasPrefix("MeetingBuddySettings-")) {
                return true
            }

            // Fallback for app-bundle launches where executableURL may be different.
            if let name, (name == "MeetingBuddySettings" || name == "Meeting Buddy Settings") {
                return true
            }

            return false
        }

        if let existing = runningSettings.first {
            // Terminate any existing instance and relaunch so we always get a fresh window.
            // (SwiftUI WindowGroup keeps the process alive after the window is closed,
            //  so activate() alone won't reopen it.)
            existing.terminate()
            Thread.sleep(forTimeInterval: 0.25)
        }

        var candidates: [URL] = []

        candidates.append(contentsOf: bundledSettingsExecutables())

        // SwiftPM build output (local dev)
        candidates.append(
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent("..")
                .appendingPathComponent("MeetingBuddySettings")
                .appendingPathComponent(".build")
                .appendingPathComponent("release")
                .appendingPathComponent("MeetingBuddySettings")
        )

        // Legacy checked-in binary
        candidates.append(
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent("..")
                .appendingPathComponent("..")
                .appendingPathComponent("..")
                .appendingPathComponent("ui")
                .appendingPathComponent("src-tauri")
                .appendingPathComponent("MeetingBuddySettings-aarch64-apple-darwin")
        )

        NSLog("[SettingsLauncher] candidates: %@", candidates.map(\.path).joined(separator: ", "))
        if let exe = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }) {
            NSLog("[SettingsLauncher] found: %@", exe.path)
            // Launch the Settings binary as a subprocess. Do NOT use openApplication(at:configuration:)
            // — that API is for .app bundles; for a raw executable macOS opens a terminal.
            let process = Process()
            process.executableURL = exe
            process.arguments = []
            try process.run()
            return
        }

        throw NSError(
            domain: "MeetingBuddyHUD",
            code: 0,
            userInfo: [NSLocalizedDescriptionKey: "Could not find MeetingBuddySettings executable. Build it via: cd native/MeetingBuddySettings && swift build -c release"]
        )
    }
}
