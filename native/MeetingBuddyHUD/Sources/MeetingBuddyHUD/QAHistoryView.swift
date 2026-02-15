import SwiftUI
import MeetingBuddyProtocol

// MARK: - Q&A History

struct QAHistoryView: View {
    @ObservedObject var ws: WebSocketClient
    /// How many entries to show before "Show all" is tapped.
    private let collapsedCount = 3

    @State private var expanded: Bool = false
    @State private var hoveringShowAll: Bool = false

    private var displayedEntries: [QAEntry] {
        let all = ws.qaHistory.reversed() as [QAEntry]
        return expanded ? all : Array(all.prefix(collapsedCount))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("RECENT Q&A")
                    .font(.caption2)
                    .textCase(.uppercase)
                    .kerning(0.5)
                    .foregroundStyle(AppTheme.accentBlue)

                Spacer(minLength: 0)

                if ws.qaHistory.count > collapsedCount {
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
                    } label: {
                        Text(expanded ? "Show less" : "Show all (\(ws.qaHistory.count))")
                            .font(.caption2)
                            .foregroundStyle(hoveringShowAll ? AppTheme.textPrimary : AppTheme.textSecondary)
                    }
                    .buttonStyle(.plain)
                    .onHover { hoveringShowAll = $0 }
                }
            }

            ForEach(displayedEntries) { entry in
                QAHistoryRow(entry: entry, isActive: entry.question == ws.activeQuestion) {
                    Task { await ws.setQuestion(entry.question) }
                }
            }
        }
    }
}

// MARK: - Row

private struct QAHistoryRow: View {
    let entry: QAEntry
    let isActive: Bool
    let onTap: () -> Void

    @State private var detailExpanded: Bool = false
    @State private var hovering: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Question + toggle
            HStack(alignment: .top, spacing: 6) {
                Image(systemName: "questionmark.circle")
                    .font(.caption)
                    .foregroundStyle(isActive ? AppTheme.accentBlue : AppTheme.textSecondary)
                    .frame(width: 14)

                Text(entry.question)
                    .font(.caption)
                    .foregroundStyle(isActive ? AppTheme.textPrimary : AppTheme.textSecondary)
                    .lineLimit(detailExpanded ? nil : 1)
                    .truncationMode(.tail)
                    .frame(maxWidth: .infinity, alignment: .leading)

                if entry.answer != nil {
                    Image(systemName: detailExpanded ? "chevron.up" : "chevron.down")
                        .font(.caption)
                        .foregroundStyle(AppTheme.textSecondary)
                        .frame(width: 24, height: 24)
                        .contentShape(Rectangle())
                }
            }
            .contentShape(Rectangle())
            .onTapGesture {
                if entry.answer != nil {
                    withAnimation(.easeInOut(duration: 0.15)) { detailExpanded.toggle() }
                }
                onTap()
            }
            .onHover { hovering = $0 }
            .opacity(hovering && !isActive ? 0.75 : 1.0)

            // Expanded one-liner + bullets
            if detailExpanded, let answer = entry.answer {
                VStack(alignment: .leading, spacing: 4) {
                    if let one = answer.one_liner, !one.isEmpty {
                        Text(one)
                            .font(.caption)
                            .foregroundStyle(AppTheme.textPrimary)
                    }

                    if let bullets = answer.bullets, !bullets.isEmpty {
                        ForEach(bullets.prefix(3), id: \.self) { bullet in
                            HStack(alignment: .top, spacing: 6) {
                                Image(systemName: "circle.fill")
                                    .font(.system(size: 4))
                                    .foregroundStyle(AppTheme.accentBlue)
                                    .padding(.top, 5)
                                Text(bullet)
                                    .font(.caption)
                                    .foregroundStyle(AppTheme.textPrimary)
                            }
                        }
                    }
                }
                .padding(.leading, 20)
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 10)
        .background(
            RoundedRectangle(cornerRadius: 7)
                .fill(isActive ? AppTheme.accentBlue.opacity(0.10) : Color.white.opacity(0.04))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 7)
                .strokeBorder(
                    isActive ? AppTheme.accentBlue.opacity(0.30) : Color.clear,
                    lineWidth: 0.5
                )
        )
    }
}
