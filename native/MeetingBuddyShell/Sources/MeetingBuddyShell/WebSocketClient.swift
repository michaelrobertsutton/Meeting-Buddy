import Foundation
import Combine

final class WebSocketClient: ObservableObject {
    @Published var connected: Bool = false
    @Published var lastError: String? = nil

    @Published var segments: [TranscriptSegment] = []
    @Published var activeQuestion: String = ""
    @Published var oneLiner: String = ""

    private var task: URLSessionWebSocketTask?
    private let url: URL

    init(url: URL = URL(string: "ws://localhost:8765")!) {
        self.url = url
    }

    func connect() {
        disconnect()

        let session = URLSession(configuration: .default)
        let task = session.webSocketTask(with: url)
        self.task = task
        task.resume()
        connected = true
        lastError = nil

        receiveLoop()
    }

    func disconnect() {
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        connected = false
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
            case .success(let message):
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
        }
    }
}
