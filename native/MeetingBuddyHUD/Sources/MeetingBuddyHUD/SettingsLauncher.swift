import Foundation
import AppKit

enum SettingsLauncher {
    private static let showWindowNotification = Notification.Name("MeetingBuddySettings.ShowWindow")

    private static func isSettingsApp(_ app: NSRunningApplication) -> Bool {
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

    private static func runningSettingsApps() -> [NSRunningApplication] {
        NSWorkspace.shared.runningApplications.filter(isSettingsApp(_:))
    }

    private static func dedupeRunningSettings(_ apps: [NSRunningApplication]) -> NSRunningApplication? {
        guard !apps.isEmpty else { return nil }
        let sorted = apps.sorted { $0.processIdentifier < $1.processIdentifier }
        let primary = sorted[0]
        for duplicate in sorted.dropFirst() {
            duplicate.terminate()
        }
        return primary
    }

    static func isSettingsFrontmost() -> Bool {
        guard let frontmost = NSWorkspace.shared.frontmostApplication else { return false }
        return isSettingsApp(frontmost)
    }

    private static func requestShowWindow() {
        DistributedNotificationCenter.default().postNotificationName(
            showWindowNotification,
            object: nil,
            userInfo: nil,
            deliverImmediately: true
        )
    }

    private static func bringToFront(_ app: NSRunningApplication) {
        requestShowWindow()
        app.activate(options: [.activateAllWindows, .activateIgnoringOtherApps])
    }

    private static func bundledSettingsExecutables() -> [URL] {
        guard let hudExe = Bundle.main.executableURL else { return [] }
        let dir = hudExe.deletingLastPathComponent()
        // Try both plain name (bundled .app) and arch-suffixed name (dev sidecar)
        return [
            dir.appendingPathComponent("MeetingBuddySettings"),
            dir.appendingPathComponent("MeetingBuddySettings-aarch64-apple-darwin"),
        ]
    }

    private static func candidateExecutables() -> [URL] {
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

        return candidates
    }

    static func launch() throws {
        if let existing = dedupeRunningSettings(runningSettingsApps()) {
            bringToFront(existing)
            return
        }

        let candidates = candidateExecutables()
        NSLog("[SettingsLauncher] candidates: %@", candidates.map(\.path).joined(separator: ", "))
        if let exe = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }) {
            NSLog("[SettingsLauncher] found: %@", exe.path)
            // Launch the Settings binary as a subprocess. Do NOT use openApplication(at:configuration:)
            // — that API is for .app bundles; for a raw executable macOS opens a terminal.
            let process = Process()
            process.executableURL = exe
            process.arguments = []
            try process.run()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                requestShowWindow()
            }
            return
        }

        throw NSError(
            domain: "MeetingBuddyHUD",
            code: 0,
            userInfo: [NSLocalizedDescriptionKey: "Could not find MeetingBuddySettings executable. Build it via: cd native/MeetingBuddySettings && swift build -c release"]
        )
    }
}
