import Foundation
import AppKit

enum SettingsLauncher {

    /// Best-effort launcher for the native MeetingBuddySettings sidecar.
    ///
    /// Dev-friendly behavior:
    /// - prefers the SwiftPM-built binary if present
    /// - falls back to the checked-in binary under ui/src-tauri/
    ///
    /// Note: this is intentionally best-effort for internal tooling.
    static func launch() throws {
        // Candidate locations (in priority order)
        let candidates: [URL] = [
            // SwiftPM build output (local dev)
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent("..")
                .appendingPathComponent("MeetingBuddySettings")
                .appendingPathComponent(".build")
                .appendingPathComponent("release")
                .appendingPathComponent("MeetingBuddySettings"),

            // Checked-in binary (from prior work)
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent("..")
                .appendingPathComponent("..")
                .appendingPathComponent("..")
                .appendingPathComponent("ui")
                .appendingPathComponent("src-tauri")
                .appendingPathComponent("MeetingBuddySettings-aarch64-apple-darwin"),
        ]

        if let exe = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }) {
            let config = NSWorkspace.OpenConfiguration()
            config.activates = true
            NSWorkspace.shared.openApplication(at: exe, configuration: config)
            return
        }

        throw NSError(
            domain: "MeetingBuddyShell",
            code: 0,
            userInfo: [NSLocalizedDescriptionKey: "Could not find MeetingBuddySettings executable. Build it via: cd native/MeetingBuddySettings && swift build -c release"]
        )
    }
}
