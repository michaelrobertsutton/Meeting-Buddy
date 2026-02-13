import Foundation
import Combine

final class WebSocketClient: ObservableObject {
    @Published var connected: Bool = false
    @Published var lastError: String? = nil

    @Published var settingsError: String? = nil

    @Published var segments: [TranscriptSegment] = []
    @Published var activeQuestion: String = ""
    @Published var oneLiner: String = ""

    // For Issue #120 header controls (stubbed until backend supports projects list via snapshot)
    @Published var availableProjects: [String] = []
    @Published var activeProject: String = ""

    private var task: URLSessionWebSocketTask?
    private let url: URL

    private var pending: [String: (Result<[String: Any], Error>) -> Void] = [:]
    private let pendingQueue = DispatchQueue(label: "ws.pending.queue")

    private var reconnectAttempt: Int = 0
    private var reconnectWorkItem: DispatchWorkItem?

    init(url: URL = URL(string: "ws://localhost:8765")!) {
        self.url = url
    }

    func connect() {
        reconnectWorkItem?.cancel()
        reconnectWorkItem = nil

        disconnect()

        let session = URLSession(configuration: .default)
        let task = session.webSocketTask(with: url)
        self.task = task
        task.resume()

        // We don't get an explicit "open" callback; treat first successful receive as connected.
        DispatchQueue.main.async {
            self.connected = false
            self.lastError = nil
            self.settingsError = nil
        }

        receiveLoop()
    }

    func disconnect() {
        reconnectWorkItem?.cancel()
        reconnectWorkItem = nil

        task?.cancel(with: .goingAway, reason: nil)
        task = nil

        DispatchQueue.main.async {
            self.connected = false
        }
    }

    private func scheduleReconnect() {
        reconnectWorkItem?.cancel()

        // backoff: 0.5s, 1s, 2s, 4s… capped
        reconnectAttempt = min(reconnectAttempt + 1, 6)
        let delay = min(pow(2.0, Double(reconnectAttempt)) * 0.25, 8.0)

        let item = DispatchWorkItem { [weak self] in
            self?.connect()
        }
        reconnectWorkItem = item
        DispatchQueue.global().asyncAfter(deadline: .now() + delay, execute: item)
    }

    private func receiveLoop() {
        guard let task else { return }

        task.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .failure(let err):
                DispatchQueue.main.async {
                    self.connected = false
                    self.lastError = err.localizedDescription
                }
                self.scheduleReconnect()

            case .success(let message):
                // Mark connected on first successfully received frame.
                DispatchQueue.main.async {
                    if self.connected == false {
                        self.connected = true
                        self.reconnectAttempt = 0
                        // Fetch settings once connected so toolbar can populate projects.
                        Task { await self.bootstrapSettings() }
                    }
                }

                switch message {
                case .string(let s):
                    self.handle(text: s)
                case .data(let data):
                    if let s = String(data: data, encoding: .utf8) {
                        self.handle(text: s)
                    }
                @unknown default:
                    break
                }
                // keep receiving
                self.receiveLoop()
            }
        }
    }

    private func handle(text: String) {
        guard let data = text.data(using: .utf8) else { return }

        // First try the strongly-typed decoder (snapshot/update events).
        if let msg = try? JSONDecoder().decode(BackendMessage.self, from: data) {
            DispatchQueue.main.async {
                if let segs = msg.segments { self.segments = segs }
                self.activeQuestion = msg.active_question ?? self.activeQuestion
                self.oneLiner = msg.active_answer?.one_liner ?? self.oneLiner
            }
            return
        }

        // Fallback: handle command responses with dynamic decoding.
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        guard let type = obj["type"] as? String, type == "response", let id = obj["id"] as? String else { return }

        let success = (obj["success"] as? Bool) ?? false
        if success {
            let payload = (obj["data"] as? [String: Any]) ?? [:]
            pendingQueue.async {
                if let cb = self.pending.removeValue(forKey: id) {
                    cb(.success(payload))
                }
            }
        } else {
            let errMsg = (obj["error"] as? String) ?? "Unknown error"
            let err = NSError(domain: "WebSocketClient", code: 0, userInfo: [NSLocalizedDescriptionKey: errMsg])
            pendingQueue.async {
                if let cb = self.pending.removeValue(forKey: id) {
                    cb(.failure(err))
                }
            }
        }
    }

    // MARK: - Commands

    private func send(command: String, params: [String: Any] = [:], id: String) throws {
        guard let task else { throw URLError(.notConnectedToInternet) }
        let dict: [String: Any] = [
            "id": id,
            "command": command,
            "params": params,
        ]
        let data = try JSONSerialization.data(withJSONObject: dict)
        let string = String(data: data, encoding: .utf8)!
        task.send(.string(string)) { _ in }
    }

    private func sendCommand(_ command: String, params: [String: Any] = [:]) async throws -> [String: Any] {
        let id = UUID().uuidString
        return try await withCheckedThrowingContinuation { cont in
            pendingQueue.async {
                self.pending[id] = { result in
                    switch result {
                    case .success(let dict): cont.resume(returning: dict)
                    case .failure(let err): cont.resume(throwing: err)
                    }
                }
            }
            do {
                try self.send(command: command, params: params, id: id)
            } catch {
                self.pendingQueue.async {
                    self.pending.removeValue(forKey: id)
                }
                cont.resume(throwing: error)
            }
        }
    }

    @MainActor
    private func applySettings(_ data: [String: Any]) {
        if let active = data["active_project"] as? String {
            activeProject = active
        }
        if let raw = data["projects"] as? [[String: Any]] {
            availableProjects = raw.compactMap { $0["name"] as? String }
        }
    }

    func bootstrapSettings() async {
        do {
            let data = try await sendCommand("get_settings")
            await MainActor.run {
                self.applySettings(data)
            }
        } catch {
            await MainActor.run {
                self.settingsError = error.localizedDescription
            }
        }
    }

    func switchProject(name: String) async {
        do {
            let data = try await sendCommand("switch_project", params: ["name": name])
            await MainActor.run {
                self.applySettings(data)
            }
        } catch {
            await MainActor.run {
                self.settingsError = error.localizedDescription
            }
        }
    }
}
