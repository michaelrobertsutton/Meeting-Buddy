import Foundation

struct TranscriptSegment: Codable, Hashable {
    let start_time: Double?
    let end_time: Double?
    let text: String
}

struct ActiveAnswer: Codable, Hashable {
    let one_liner: String?
}

struct BackendMessage: Codable {
    let type: String?
    let protocol_version: Int?

    let version: Int?
    let segments: [TranscriptSegment]?
    let active_question: String?
    let active_answer: ActiveAnswer?
}
