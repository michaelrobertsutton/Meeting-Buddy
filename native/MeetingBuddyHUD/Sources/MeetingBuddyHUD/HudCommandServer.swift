import Foundation
import Darwin

enum HudIPCCommand: String {
    case toggleHUD = "toggle_hud"
    case hideHUD = "hide_hud"
    case restoreHUD = "restore_hud"
    case openSettings = "open_settings"
}

/// Receives explicit control commands from the Tauri host over a local FIFO.
/// This replaces signal-driven HUD control to make focus and window behavior deterministic.
final class HudCommandServer {
    private let onCommand: (HudIPCCommand) -> Void
    private var readSource: DispatchSourceRead?
    private var fifoFD: Int32 = -1
    private var buffer = Data()

    init(onCommand: @escaping (HudIPCCommand) -> Void) {
        self.onCommand = onCommand
    }

    deinit {
        stop()
    }

    func start() {
        stop()

        let path = Self.fifoPath
        _ = path.withCString { unlink($0) }
        let createResult = path.withCString { mkfifo($0, 0o600) }
        if createResult != 0 && errno != EEXIST {
            NSLog("[HUD IPC] mkfifo failed at %@ (errno=%d)", path, errno)
            return
        }

        fifoFD = path.withCString { open($0, O_RDWR | O_NONBLOCK) }
        guard fifoFD >= 0 else {
            NSLog("[HUD IPC] open failed at %@ (errno=%d)", path, errno)
            return
        }

        let source = DispatchSource.makeReadSource(fileDescriptor: fifoFD, queue: .main)
        source.setEventHandler { [weak self] in
            self?.drain()
        }
        source.setCancelHandler { [weak self] in
            guard let self else { return }
            if self.fifoFD >= 0 {
                close(self.fifoFD)
                self.fifoFD = -1
            }
        }
        readSource = source
        source.resume()
    }

    func stop() {
        readSource?.cancel()
        readSource = nil

        if fifoFD >= 0 {
            close(fifoFD)
            fifoFD = -1
        }

        let path = Self.fifoPath
        _ = path.withCString { unlink($0) }
        buffer.removeAll(keepingCapacity: false)
    }

    private func drain() {
        guard fifoFD >= 0 else { return }

        var chunk = [UInt8](repeating: 0, count: 1024)
        while true {
            let count = read(fifoFD, &chunk, chunk.count)
            if count > 0 {
                buffer.append(chunk, count: count)
                processBufferedCommands()
                continue
            }
            if count == 0 {
                // FIFO can report EOF when no external writers are attached.
                return
            }
            if errno == EAGAIN || errno == EWOULDBLOCK {
                return
            }
            NSLog("[HUD IPC] read failed (errno=%d)", errno)
            return
        }
    }

    private func processBufferedCommands() {
        while let newlineIndex = buffer.firstIndex(of: 0x0A) {
            let line = buffer.prefix(upTo: newlineIndex)
            buffer.removeSubrange(...newlineIndex)

            guard let raw = String(data: line, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines),
                  !raw.isEmpty else {
                continue
            }

            guard let command = HudIPCCommand(rawValue: raw) else {
                NSLog("[HUD IPC] unknown command: %@", raw)
                continue
            }
            onCommand(command)
        }

        // Guardrail for malformed writers that never emit newline delimiters.
        if buffer.count > 8192 {
            buffer.removeAll(keepingCapacity: true)
        }
    }

    static var fifoPath: String {
        "/tmp/meetingbuddy-hud-\(getuid()).fifo"
    }
}
