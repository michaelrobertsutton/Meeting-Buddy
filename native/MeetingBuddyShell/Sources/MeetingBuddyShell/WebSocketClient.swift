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
        guard let msg = try? JSONDecoder().decode(BackendMessage.self, from: data) else { return }

        DispatchQueue.main.async {
            if let segs = msg.segments { self.segments = segs }
            self.activeQuestion = msg.active_question ?? self.activeQuestion
            self.oneLiner = msg.active_answer?.one_liner ?? self.oneLiner

            // Opportunistic: if we ever include these fields in snapshot/update, wire them.
            // (Safe no-ops today.)
            // self.activeProject = msg.active_project ?? self.activeProject
            // self.availableProjects = msg.projects ?? self.availableProjects
        }
    }
}
