import Foundation

struct TranscriptSegment: Codable, Hashable {
    let start_time: Double?
    let end_time: Double?
    let text: String
}

struct Citation: Codable, Hashable, Identifiable {
    var id: String { "\(doc)-\(section ?? "")-\(page ?? 0)" }
    let doc: String
    let section: String?
    let page: Int?
    let quote: String?
}

struct ActiveAnswer: Codable, Hashable {
    let one_liner: String?
    let bullets: [String]?
    let best_practice_bullets: [String]?
    let clarifiers: [String]?
    let citations: [Citation]?
    let confidence: Double?
}

struct QAEntry: Codable, Identifiable {
    var id: String { "\(timestamp)" }
    let question: String
    let answer: ActiveAnswer?
    let timestamp: Double
}

struct PinnedAnswer: Codable, Identifiable {
    let id: String
    let question: String
    let answer: ActiveAnswer?
    let timestamp: Double
}

struct BackendMessage: Codable {
    let type: String?
    let protocol_version: Int?
    let version: Int?

    // Snapshot / update fields
    let segments: [TranscriptSegment]?
    let active_question: String?
    let manual_question: Bool?
    let synthesis_searching: Bool?
    let active_answer: ActiveAnswer?
    let qa_history: [QAEntry]?
    let pinned: [PinnedAnswer]?

    // answer_partial / answer_update fields
    let partial_text: String?

    // Response fields
    let id: String?
    let success: Bool?
    let error: String?
    let data: AnyCodable?

    // Event fields
    let question: String?   // synthesis_searching event
}

// Minimal type-erased Codable wrapper for response `data` field.
struct AnyCodable: Codable {
    let value: Any

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let dict = try? container.decode([String: String].self) {
            value = dict
        } else if let str = try? container.decode(String.self) {
            value = str
        } else {
            value = ""
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(value as? String ?? "")
    }
}
