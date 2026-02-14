import Foundation
import AppKit

enum SettingsLauncher {

    private static func bundledSettingsExecutable() -> URL? {
        // For packaged installs, assume the Settings executable is alongside the HUD executable.
        // When run via SwiftPM/Xcode, Bundle.main.executableURL should still be available.
        guard let hudExe = Bundle.main.executableURL else { return nil }
        let dir = hudExe.deletingLastPathComponent()
        return dir.appendingPathComponent("MeetingBuddySettings")
    }

    /// Best-effort launcher for the native MeetingBuddySettings sidecar.
    ///
    /// Dev-friendly behavior:
    /// - prefers the SwiftPM-built binary if present
    /// - falls back to the checked-in binary under ui/src-tauri/
    ///
    /// Note: this is intentionally best-effort for internal tooling.
    static func launch() throws {
        // Single-instance behavior: if Settings is already running, bring it to front.
        // Settings may be launched as a raw executable (not necessarily a .app bundle), so match by executable name.
        let runningSettings = NSWorkspace.shared.runningApplications.filter { app in
            guard let exe = app.executableURL?.lastPathComponent else { return false }
            return exe == "MeetingBuddySettings" || exe.hasPrefix("MeetingBuddySettings-")
        }

        if let existing = runningSettings.first {
            existing.activate(options: [.activateAllWindows, .activateIgnoringOtherApps])
            return
        }

        // Candidate locations (in priority order)
        // 1) Packaged install: Settings sidecar next to the HUD executable.
        // 2) SwiftPM build output (local dev)
        // 3) Checked-in binary (legacy)

        var candidates: [URL] = []

        if let bundled = bundledSettingsExecutable() {
            candidates.append(bundled)
        }

        candidates.append(
            // SwiftPM build output (local dev)
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent("..")
                .appendingPathComponent("MeetingBuddySettings")
                .appendingPathComponent(".build")
                .appendingPathComponent("release")
                .appendingPathComponent("MeetingBuddySettings")
        )

        candidates.append(
            // Checked-in binary (legacy)
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent("..")
                .appendingPathComponent("..")
                .appendingPathComponent("..")
                .appendingPathComponent("ui")
                .appendingPathComponent("src-tauri")
                .appendingPathComponent("MeetingBuddySettings-aarch64-apple-darwin")
        )

        if let exe = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }) {
            // Launch the Settings binary as a subprocess. Do NOT use openApplication(at:configuration:)
            // — that API is for .app bundles; for a raw executable macOS opens a terminal.
            let process = Process()
            process.executableURL = exe
            process.arguments = []
            try process.run()
            return
        }

        throw NSError(
            domain: "MeetingBuddyShell",
            code: 0,
            userInfo: [NSLocalizedDescriptionKey: "Could not find MeetingBuddySettings executable. Build it via: cd native/MeetingBuddySettings && swift build -c release"]
        )
    }
}
