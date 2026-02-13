import Foundation

// MARK: - Settings response from get_settings

struct AppSettings: Codable {
    var activeProject: String?
    var projects: [ProjectInfo]?
    var oauthEmail: String?
    var oauthExpiry: String?
    var hasApiKey: Bool?

    enum CodingKeys: String, CodingKey {
        case activeProject = "active_project"
        case projects
        case oauthEmail = "oauth_email"
        case oauthExpiry = "oauth_expiry"
        case hasApiKey = "has_api_key"
    }
}

struct ProjectInfo: Codable, Identifiable, Hashable {
    var id: String { name }
    var name: String
    var chunkCount: Int?

    enum CodingKeys: String, CodingKey {
        case name
        case chunkCount = "chunk_count"
    }
}

// MARK: - Docs

struct DocInfo: Codable, Identifiable, Hashable {
    var id: String { title }
    var title: String
    var chunkCount: Int?
    var source: String?

    enum CodingKeys: String, CodingKey {
        case title
        case chunkCount = "chunk_count"
        case source
    }
}

// MARK: - WebSocket envelope

struct WSCommand: Encodable {
    let id: String
    let command: String
    var params: [String: AnyCodable]

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: DynamicKey.self)
        try container.encode(id, forKey: DynamicKey("id"))
        try container.encode(command, forKey: DynamicKey("command"))
        for (key, value) in params {
            try container.encode(value, forKey: DynamicKey(key))
        }
    }
}

// Helpers for encoding arbitrary JSON values

struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) { self.value = value }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let v as String: try container.encode(v)
        case let v as Int: try container.encode(v)
        case let v as Double: try container.encode(v)
        case let v as Bool: try container.encode(v)
        case let v as [String]: try container.encode(v)
        case is NSNull: try container.encodeNil()
        default: try container.encodeNil()
        }
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let v = try? c.decode(String.self) { value = v }
        else if let v = try? c.decode(Bool.self) { value = v }
        else if let v = try? c.decode(Int.self) { value = v }
        else if let v = try? c.decode(Double.self) { value = v }
        else { value = NSNull() }
    }
}

struct DynamicKey: CodingKey {
    var stringValue: String
    var intValue: Int?
    init(_ string: String) { self.stringValue = string }
    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { return nil }
}
