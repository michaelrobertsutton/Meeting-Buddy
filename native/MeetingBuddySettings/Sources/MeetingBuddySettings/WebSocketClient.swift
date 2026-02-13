import Foundation

/// Async/await WebSocket client backed by URLSessionWebSocketTask.
actor WebSocketClient {

    private let url: URL
    private var task: URLSessionWebSocketTask?
    private var continuations: [CheckedContinuation<[String: Any], Error>] = []
    private var streamContinuation: AsyncStream<[String: Any]>.Continuation?

    private(set) var isConnected = false

    init(url: URL = URL(string: "ws://localhost:8765")!) {
        self.url = url
    }

    // MARK: - Connect

    func connect() async {
        guard !isConnected else { return }
        let session = URLSession(configuration: .default)
        let t = session.webSocketTask(with: url)
        self.task = t
        t.resume()
        isConnected = true
        Task { await self.receiveLoop() }
    }

    func disconnect() {
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
        isConnected = false
        streamContinuation?.finish()
    }

    // MARK: - Send

    func send(command: String, params: [String: Any] = [:], id: String? = nil) async throws {
        guard let task else { throw URLError(.notConnectedToInternet) }
        var dict: [String: Any] = ["id": id ?? UUID().uuidString, "command": command]
        for (k, v) in params { dict[k] = v }
        let data = try JSONSerialization.data(withJSONObject: dict)
        let string = String(data: data, encoding: .utf8)!
        try await task.send(.string(string))
    }

    // MARK: - Receive stream

    func messages() -> AsyncStream<[String: Any]> {
        AsyncStream { continuation in
            self.streamContinuation = continuation
        }
    }

    // MARK: - Private

    private func receiveLoop() async {
        while isConnected, let task {
            do {
                let message = try await task.receive()
                var raw: String?
                switch message {
                case .string(let s): raw = s
                case .data(let d): raw = String(data: d, encoding: .utf8)
                @unknown default: break
                }
                if let raw, let data = raw.data(using: .utf8),
                   let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    streamContinuation?.yield(dict)
                }
            } catch {
                isConnected = false
                streamContinuation?.finish()
                break
            }
        }
    }
}
