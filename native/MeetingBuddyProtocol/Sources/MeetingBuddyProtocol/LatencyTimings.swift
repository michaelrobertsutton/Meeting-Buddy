import Foundation

public struct LatencyTimings: Codable, Hashable {
    public let question: String?
    public let ttft_ms: Double?
    public let total_ms: Double?
    public let mode: String?

    public init(question: String?, ttft_ms: Double?, total_ms: Double?, mode: String?) {
        self.question = question
        self.ttft_ms = ttft_ms
        self.total_ms = total_ms
        self.mode = mode
    }
}
