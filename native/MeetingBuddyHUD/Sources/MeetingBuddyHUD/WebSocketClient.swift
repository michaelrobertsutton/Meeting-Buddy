import Foundation
import Combine

final class WebSocketClient: ObservableObject {

    private static func transcriptFingerprint(_ segs: [TranscriptSegment]) -> String {
        // Key idle detection off actual transcript advancement, not message receipt.
        // Use the last segment’s text plus count as a cheap fingerprint.
        let last = segs.last?.text ?? ""
        return "\(segs.count)|\(last)"
    }

    enum ConnectionState: Equatable {
        case connected
        case connecting
        case disconnected
    }

    @Published var connectionState: ConnectionState = .connecting
    @Published var lastError: String? = nil

    // UI state
    @Published var isPinned: Bool = false

    @Published var segments: [TranscriptSegment] = []
    @Published var lastTranscriptAt: Date? = nil
    private var lastTranscriptFingerprint: String = ""
    @Published var activeQuestion: String = ""
    @Published var oneLiner: String = ""
    @Published var activeAnswer: ActiveAnswer? = nil
    @Published var synthesisSearching: Bool = false
    @Published var synthesisError: String? = nil
    @Published var answerPartialText: String = ""

    // Projects
    @Published var availableProjects: [String] = []
    @Published var activeProject: String = ""

    // Pins
    @Published var pinned: [PinnedAnswer] = []

    private var task: URLSessionWebSocketTask?
    private let url: URL

    private var pending: [String: (Result<[String: Any], Error>) -> Void] = [:]
    private let pendingQueue = DispatchQueue(label: "ws.pending.queue")

    private var reconnectAttempt: Int = 0
    private var reconnectWorkItem: DispatchWorkItem?

    private var backendLaunchAttempted: Bool = false

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

        DispatchQueue.main.async {
            self.connectionState = .connecting
            self.lastError = nil
        }

        receiveLoop()
    }

    func disconnect() {
        reconnectWorkItem?.cancel()
        reconnectWorkItem = nil

        task?.cancel(with: .goingAway, reason: nil)
        task = nil

        DispatchQueue.main.async {
            self.connectionState = .disconnected
        }
    }

    private func scheduleReconnect() {
        reconnectWorkItem?.cancel()

        reconnectAttempt = min(reconnectAttempt + 1, 6)
        let delay = min(pow(2.0, Double(reconnectAttempt)) * 0.25, 8.0)

        let item = DispatchWorkItem { [weak self] in
            DispatchQueue.main.async {
                self?.connectionState = .connecting
            }
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
                    self.connectionState = .disconnected
                    self.lastError = err.localizedDescription
                }

                // If HUD is launched without the Tauri process manager, nothing may be
                // listening on localhost:8765. Try a best-effort backend launch once.
                if !self.backendLaunchAttempted {
                    self.backendLaunchAttempted = true
                    BackendLauncher.launchIfAvailable()
                }

                self.scheduleReconnect()

            case .success(let message):
                DispatchQueue.main.async {
                    if self.connectionState != .connected {
                        self.connectionState = .connected
                        self.reconnectAttempt = 0
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
                self.receiveLoop()
            }
        }
    }

    private func handle(text: String) {
        guard let data = text.data(using: .utf8) else { return }

        if let msg = try? JSONDecoder().decode(BackendMessage.self, from: data) {
            DispatchQueue.main.async {
                if let segs = msg.segments {
                    let fp = Self.transcriptFingerprint(segs)
                    if fp != self.lastTranscriptFingerprint {
                        self.lastTranscriptFingerprint = fp
                        self.lastTranscriptAt = Date()
                    }
                    self.segments = segs
                }
                // Synthesis / answer
                if let t = msg.type {
                    switch t {
                    case "synthesis_searching":
                        self.synthesisSearching = true
                        self.synthesisError = nil
                        self.answerPartialText = ""
                    case "synthesis_error":
                        self.synthesisSearching = false
                        self.synthesisError = msg.error ?? "Synthesis error"
                        self.answerPartialText = ""
                    case "answer_partial":
                        if let partial = msg.partial_text {
                            self.answerPartialText = partial
                        }
                    case "answer_update":
                        self.synthesisSearching = false
                        self.synthesisError = nil
                        self.answerPartialText = ""
                    case "pinned_update":
                        break
                    default:
                        break
                    }
                }

                self.activeQuestion = msg.active_question ?? self.activeQuestion
                self.oneLiner = msg.active_answer?.one_liner ?? self.oneLiner
                if let ans = msg.active_answer { self.activeAnswer = ans }

                // Some snapshots include synthesis_searching as a boolean.
                if let searching = msg.synthesis_searching { self.synthesisSearching = searching }

                if let pinned = msg.pinned {
                    self.pinned = pinned
                    self.isPinned = !pinned.isEmpty
                }
            }
            return
        }

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
            await listProjects()
        } catch {
            await MainActor.run {
                self.lastError = error.localizedDescription
            }
        }
    }

    func listProjects() async {
        do {
            let data = try await sendCommand("list_projects")
            if let raw = data["projects"] as? [[String: Any]] {
                let names = raw.compactMap { $0["name"] as? String }
                await MainActor.run {
                    self.availableProjects = names
                }
            }
        } catch {
            await MainActor.run {
                self.lastError = error.localizedDescription
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
                self.lastError = error.localizedDescription
            }
        }
    }

    func setQuestion(_ text: String) async {
        do {
            _ = try await sendCommand("set_question", params: ["text": text])
        } catch {
            await MainActor.run {
                self.lastError = error.localizedDescription
            }
        }
    }

    func clearQuestionOverride() async {
        do {
            // Backend treats empty text as clear.
            _ = try await sendCommand("set_question", params: ["text": ""]) 
        } catch {
            await MainActor.run {
                self.lastError = error.localizedDescription
            }
        }
    }

    func exportSession(format: String = "markdown") async {
        do {
            _ = try await sendCommand("export_session", params: ["format": format])
        } catch {
            await MainActor.run {
                self.lastError = error.localizedDescription
            }
        }
    }

    func refreshPinned() async {
        do {
            let data = try await sendCommand("get_pinned")
            if let raw = data["pinned"] as? [[String: Any]] {
                // Best-effort parse for UI state only.
                let pinned: [PinnedAnswer] = raw.compactMap { dict in
                    guard let id = dict["id"] as? String else { return nil }
                    let question = (dict["question"] as? String) ?? ""
                    let ts = (dict["timestamp"] as? Double) ?? 0
                    return PinnedAnswer(id: id, question: question, answer: nil, timestamp: ts)
                }
                await MainActor.run {
                    self.pinned = pinned
                    self.isPinned = !pinned.isEmpty
                }
            }
        } catch {
            await MainActor.run {
                self.lastError = error.localizedDescription
            }
        }
    }

    func togglePin() async {
        do {
            if let first = pinned.first {
                _ = try await sendCommand("unpin_answer", params: ["id": first.id])
            } else {
                var params: [String: Any] = [:]
                if !activeQuestion.isEmpty { params["question"] = activeQuestion }
                // Do NOT send a plain-string answer; let the backend pin its structured active_answer.
                _ = try await sendCommand("pin_answer", params: params)
            }
            await refreshPinned()
        } catch {
            await MainActor.run {
                self.lastError = error.localizedDescription
            }
        }
    }
}
