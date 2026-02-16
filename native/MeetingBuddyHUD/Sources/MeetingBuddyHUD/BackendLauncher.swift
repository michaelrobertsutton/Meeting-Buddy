import Foundation

enum BackendLauncher {

    /// Best-effort backend launcher for cases where the native HUD/Settings is started
    /// without the Tauri process manager.
    static func launchIfAvailable(forceRestart: Bool = false) {
        guard let url = findBackendSidecar() else { return }

        let proc = Process()
        proc.executableURL = url
        proc.standardOutput = FileHandle.nullDevice
        proc.standardError = FileHandle.nullDevice
        if forceRestart {
            var env = ProcessInfo.processInfo.environment
            env["MEETINGBUDDY_FORCE_RESTART"] = "1"
            proc.environment = env
        }
        do {
            try proc.run()
        } catch {
            // best-effort
        }
    }

    private static func findBackendSidecar() -> URL? {
        let fm = FileManager.default

        var candidates: [URL] = []

        // Packaged install: if the Tauri app is managing, backend is spawned there.
        // For direct-launch scenarios, try to find the checked-in sidecar script/binary.

        // 1) Alongside this executable
        if let exe = Bundle.main.executableURL {
            candidates.append(exe.deletingLastPathComponent().appendingPathComponent("meeting-buddy-backend"))
            candidates.append(exe.deletingLastPathComponent().appendingPathComponent("meeting-buddy-backend-aarch64-apple-darwin"))
        }

        // 2) Repo dev path (from SwiftPM run cwd)
        let cwd = URL(fileURLWithPath: fm.currentDirectoryPath)
        candidates.append(cwd.appendingPathComponent("..")
            .appendingPathComponent("..")
            .appendingPathComponent("ui")
            .appendingPathComponent("src-tauri")
            .appendingPathComponent("meeting-buddy-backend-aarch64-apple-darwin"))

        // 3) Same directory as ui/src-tauri packaged externalBin (if copied)
        candidates.append(cwd.appendingPathComponent("ui")
            .appendingPathComponent("src-tauri")
            .appendingPathComponent("meeting-buddy-backend-aarch64-apple-darwin"))

        for c in candidates {
            if fm.isExecutableFile(atPath: c.path) {
                return c
            }
        }
        return nil
    }
}
