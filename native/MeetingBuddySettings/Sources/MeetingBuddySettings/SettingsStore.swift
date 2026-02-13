import Foundation
import AppKit

@MainActor
class SettingsStore: ObservableObject {

    // MARK: - Published state

    @Published var isConnected = false
    @Published var activeProject: String = ""
    @Published var projects: [ProjectInfo] = []
    @Published var docs: [DocInfo] = []
    @Published var oauthEmail: String? = nil
    @Published var oauthExpiry: String? = nil
    @Published var hasApiKey: Bool = false
    @Published var isIngesting = false
    @Published var ingestProgress: String? = nil
    @Published var errorMessage: String? = nil
    @Published var toastMessage: String? = nil
    @Published var reconnecting: Bool = false

    // MARK: - Private

    private let client = WebSocketClient()
    private var pendingCommands: [String: CheckedContinuation<[String: Any], Error>] = [:]
    private var listenerTask: Task<Void, Never>?
    private var connectionPollTask: Task<Void, Never>?

    // MARK: - Lifecycle

    func start() {
        listenerTask = Task {
            await client.connect()

            let stream = await client.messages()
            for await msg in stream {
                await self.handleMessage(msg)
            }
        }

        connectionPollTask = Task {
            while !Task.isCancelled {
                let connected = await client.isConnected
                await MainActor.run {
                    if self.isConnected != connected {
                        self.isConnected = connected
                    }
                    self.reconnecting = (!connected)
                }
                try? await Task.sleep(nanoseconds: 500_000_000)
            }
        }
    }

    func stop() {
        listenerTask?.cancel()
        connectionPollTask?.cancel()
        Task { await client.disconnect() }
    }

    // MARK: - Command helpers

    @discardableResult
    private func sendCommand(_ command: String, params: [String: Any] = [:]) async throws -> [String: Any] {
        let id = UUID().uuidString
        return try await withCheckedThrowingContinuation { continuation in
            self.pendingCommands[id] = continuation
            Task {
                do {
                    try await self.client.send(command: command, params: params, id: id)
                } catch {
                    self.pendingCommands.removeValue(forKey: id)
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func handleMessage(_ msg: [String: Any]) async {
        // Response to a pending command
        if let type_ = msg["type"] as? String, type_ == "response",
           let id = msg["id"] as? String,
           let cont = pendingCommands.removeValue(forKey: id) {
            let success = msg["success"] as? Bool ?? false
            if success {
                let data = msg["data"] as? [String: Any] ?? [:]
                cont.resume(returning: data)
            } else {
                let err = msg["error"] as? String ?? "Unknown error"
                cont.resume(throwing: NSError(domain: "WS", code: 0, userInfo: [NSLocalizedDescriptionKey: err]))
            }
            return
        }

        // Unsolicited events
        let type_ = msg["type"] as? String ?? ""
        switch type_ {
        case "ingest_progress":
            ingestProgress = msg["message"] as? String
        case "ingest_complete":
            isIngesting = false
            ingestProgress = nil
            await fetchDocs()
        case "auth_complete":
            await fetchSettings()
        case "auth_error":
            errorMessage = msg["message"] as? String ?? "Auth failed"
        default:
            break
        }
    }

    // MARK: - Public API

    func fetchSettings() async {
        do {
            let data = try await sendCommand("get_settings")
            applySettings(data)
        } catch {
            // Treat as fatal: settings are required for the window to function.
            errorMessage = error.localizedDescription
        }
    }

    func fetchProjects() async {
        do {
            let data = try await sendCommand("list_projects")
            if let raw = data["projects"] as? [[String: Any]] {
                projects = raw.compactMap { decodeProject($0) }
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func switchProject(_ name: String) async {
        do {
            let data = try await sendCommand("switch_project", params: ["name": name])
            applySettings(data)
            await fetchDocs()
        } catch {
            showToast(error.localizedDescription)
        }
    }

    func createProject(_ name: String) async {
        do {
            let data = try await sendCommand("create_project", params: ["name": name])
            if let raw = data["projects"] as? [[String: Any]] {
                projects = raw.compactMap { decodeProject($0) }
            }
        } catch {
            showToast(error.localizedDescription)
        }
    }

    func deleteProject(_ name: String) async {
        do {
            let data = try await sendCommand("delete_project", params: ["name": name])
            if let raw = data["projects"] as? [[String: Any]] {
                projects = raw.compactMap { decodeProject($0) }
            }
            if activeProject == name {
                activeProject = projects.first?.name ?? ""
            }
        } catch {
            showToast(error.localizedDescription)
        }
    }

    func fetchDocs() async {
        do {
            let data = try await sendCommand("list_docs")
            if let raw = data["docs"] as? [[String: Any]] {
                docs = raw.compactMap { decodeDoc($0) }
            } else {
                docs = []
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func ingestFiles(_ paths: [String]) async {
        isIngesting = true
        ingestProgress = "Starting ingestion..."
        do {
            try await sendCommand("ingest_files", params: ["paths": paths])
        } catch {
            isIngesting = false
            ingestProgress = nil
            showToast(error.localizedDescription)
        }
    }

    func deleteDoc(_ title: String) async {
        do {
            try await sendCommand("delete_doc", params: ["title": title])
            await fetchDocs()
        } catch {
            showToast(error.localizedDescription)
        }
    }

    func startLogin() async {
        do {
            let data = try await sendCommand("start_login")
            if let urlString = data["url"] as? String, let url = URL(string: urlString) {
                NSWorkspace.shared.open(url)
            }
        } catch {
            // Treat as fatal: auth flows are user-visible and should be explicit.
            errorMessage = error.localizedDescription
        }
    }

    func logout() async {
        do {
            try await sendCommand("logout")
            oauthEmail = nil
            oauthExpiry = nil
            await fetchSettings()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func setApiKey(_ key: String) async {
        do {
            let data = try await sendCommand("set_api_key", params: ["key": key])
            applySettings(data)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Helpers

    private func showToast(_ msg: String) {
        toastMessage = msg
        Task {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            await MainActor.run {
                self.toastMessage = nil
            }
        }
    }

    private func applySettings(_ data: [String: Any]) {
        activeProject = data["active_project"] as? String ?? activeProject
        oauthEmail = data["oauth_email"] as? String
        oauthExpiry = data["oauth_expiry"] as? String
        hasApiKey = data["has_api_key"] as? Bool ?? false
        if let raw = data["projects"] as? [[String: Any]] {
            projects = raw.compactMap { decodeProject($0) }
        }
    }

    private func decodeProject(_ dict: [String: Any]) -> ProjectInfo? {
        guard let name = dict["name"] as? String else { return nil }
        let count = dict["chunk_count"] as? Int
        return ProjectInfo(name: name, chunkCount: count)
    }

    private func decodeDoc(_ dict: [String: Any]) -> DocInfo? {
        guard let title = dict["title"] as? String else { return nil }
        let count = dict["chunk_count"] as? Int
        let source = dict["source"] as? String
        return DocInfo(title: title, chunkCount: count, source: source)
    }
}
