import Foundation
import AppKit

enum SettingsLauncher {

    private static func bundledSettingsExecutable() -> URL? {
        guard let hudExe = Bundle.main.executableURL else { return nil }
        let dir = hudExe.deletingLastPathComponent()
        return dir.appendingPathComponent("MeetingBuddySettings")
    }

    static func launch() throws {
        var candidates: [URL] = []

        if let bundled = bundledSettingsExecutable() {
            candidates.append(bundled)
        }

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

        if let exe = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }) {
            let config = NSWorkspace.OpenConfiguration()
            config.activates = true
            NSWorkspace.shared.openApplication(at: exe, configuration: config)
            return
        }

        throw NSError(
            domain: "MeetingBuddyHUD",
            code: 0,
            userInfo: [NSLocalizedDescriptionKey: "Could not find MeetingBuddySettings executable. Build it via: cd native/MeetingBuddySettings && swift build -c release"]
        )
    }
}
