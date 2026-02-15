import Foundation

public struct TranscriptSegment: Codable, Hashable {
    public let start_time: Double?
    public let end_time: Double?
    public let text: String

    public init(start_time: Double?, end_time: Double?, text: String) {
        self.start_time = start_time
        self.end_time = end_time
        self.text = text
    }
}

public struct Citation: Codable, Hashable, Identifiable {
    public var id: String { "\(doc)-\(section ?? "")-\(page ?? 0)" }
    public let doc: String
    public let section: String?
    public let page: Int?
    public let quote: String?

    public init(doc: String, section: String?, page: Int?, quote: String?) {
        self.doc = doc
        self.section = section
        self.page = page
        self.quote = quote
    }
}

public struct ActiveAnswer: Codable, Hashable {
    public let one_liner: String?
    public let bullets: [String]?
    public let best_practice_bullets: [String]?
    public let clarifiers: [String]?
    public let citations: [Citation]?
    public let confidence: Double?

    public init(one_liner: String?, bullets: [String]?, best_practice_bullets: [String]?, clarifiers: [String]?, citations: [Citation]?, confidence: Double?) {
        self.one_liner = one_liner
        self.bullets = bullets
        self.best_practice_bullets = best_practice_bullets
        self.clarifiers = clarifiers
        self.citations = citations
        self.confidence = confidence
    }
}

public struct QAEntry: Codable, Identifiable {
    public var id: String { "\(timestamp)" }
    public let question: String
    public let answer: ActiveAnswer?
    public let timestamp: Double

    public init(question: String, answer: ActiveAnswer?, timestamp: Double) {
        self.question = question
        self.answer = answer
        self.timestamp = timestamp
    }
}

public struct PinnedAnswer: Codable, Identifiable {
    public let id: String
    public let question: String
    public let answer: ActiveAnswer?
    public let timestamp: Double

    public init(id: String, question: String, answer: ActiveAnswer?, timestamp: Double) {
        self.id = id
        self.question = question
        self.answer = answer
        self.timestamp = timestamp
    }
}

public struct BackendMessage: Codable {
    public let type: String?
    public let protocol_version: Int?
    public let version: Int?

    // Snapshot / update fields
    public let segments: [TranscriptSegment]?
    public let active_question: String?
    public let manual_question: Bool?
    public let synthesis_searching: Bool?
    public let active_answer: ActiveAnswer?
    public let qa_history: [QAEntry]?
    public let pinned: [PinnedAnswer]?
    public let listening: Bool?

    // answer_partial / answer_update fields
    public let partial_text: String?

    // Response fields
    public let id: String?
    public let success: Bool?
    public let error: String?
    public let data: AnyCodable?

    // Event fields
    public let question: String?

    public init(
        type: String?,
        protocol_version: Int?,
        version: Int?,
        segments: [TranscriptSegment]?,
        active_question: String?,
        manual_question: Bool?,
        synthesis_searching: Bool?,
        active_answer: ActiveAnswer?,
        qa_history: [QAEntry]?,
        pinned: [PinnedAnswer]?,
        listening: Bool?,
        partial_text: String?,
        id: String?,
        success: Bool?,
        error: String?,
        data: AnyCodable?,
        question: String?
    ) {
        self.type = type
        self.protocol_version = protocol_version
        self.version = version
        self.segments = segments
        self.active_question = active_question
        self.manual_question = manual_question
        self.synthesis_searching = synthesis_searching
        self.active_answer = active_answer
        self.qa_history = qa_history
        self.pinned = pinned
        self.listening = listening
        self.partial_text = partial_text
        self.id = id
        self.success = success
        self.error = error
        self.data = data
        self.question = question
    }
}

public struct AnyCodable: Codable {
    public let value: Any

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let dict = try? container.decode([String: String].self) {
            value = dict
        } else if let str = try? container.decode(String.self) {
            value = str
        } else {
            value = ""
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(value as? String ?? "")
    }
}
