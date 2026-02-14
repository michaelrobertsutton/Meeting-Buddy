import SwiftUI
import MeetingBuddyProtocol

// MARK: - Synthesis Card

struct SynthesisCardView: View {
    let question: String
    let answer: ActiveAnswer?
    let searching: Bool
    let partialText: String
    let error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("DIRECT ANSWER")
                .font(.caption2)
                .textCase(.uppercase)
                .kerning(0.5)
                .foregroundStyle(AppTheme.accentBlue)

            if searching {
                HStack(spacing: 8) {
                    ProgressView()
                        .tint(AppTheme.accentBlue)
                    Text("Searching sources…")
                        .font(.caption)
                        .foregroundStyle(AppTheme.textSecondary)
                }
            }

            let hasError = (error?.isEmpty == false)
            if let err = error, !err.isEmpty {
                Text(err)
                    .font(.body)
                    .foregroundStyle(Color(hex: "#F44336"))
            }

            let isStreaming = !partialText.isEmpty

            if isStreaming {
                Text(partialText)
                    .font(.body)
                    .italic()
                    .foregroundStyle(AppTheme.accentBlue)
            } else if !hasError {
                if let one = answer?.one_liner, !one.isEmpty {
                    Text(one)
                        .font(.body)
                        .foregroundStyle(AppTheme.textPrimary)
                }

                if let bullets = answer?.bullets, !bullets.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(bullets, id: \.self) { bullet in
                            HStack(alignment: .top, spacing: 8) {
                                Image(systemName: "circle.fill")
                                    .font(.system(size: 5, weight: .semibold))
                                    .foregroundStyle(AppTheme.accentBlue)
                                    .padding(.top, 6)

                                Text(bullet)
                                    .font(.body)
                                    .foregroundStyle(AppTheme.textPrimary)
                            }
                        }
                    }
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(.ultraThinMaterial)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color.white.opacity(0.04))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(confidenceColor.opacity(0.6), lineWidth: 1)
        )
    }

    private var confidenceColor: Color {
        let c = answer?.confidence ?? 0
        if c > 0.6 { return Color(hex: "#4CAF50") }
        if c >= 0.3 { return Color(hex: "#FFC107") }
        return Color(hex: "#F44336")
    }
}
