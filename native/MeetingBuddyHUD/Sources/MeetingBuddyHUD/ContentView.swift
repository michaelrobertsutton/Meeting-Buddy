import SwiftUI

struct ContentView: View {
    @ObservedObject var ws: WebSocketClient

    var body: some View {
        VStack(spacing: 0) {
            // Header / Toolbar
            ToolbarView(ws: ws)

            Divider()
                .background(AppTheme.glassEdge)

            // Main content area
            VStack(spacing: AppTheme.spacing) {
                // Transcript section
                TranscriptView(segments: ws.segments)

                // Answer card (when active)
                if !ws.oneLiner.isEmpty || ws.synthesisSearching {
                    AnswerCard(
                        question: ws.activeQuestion,
                        answer: ws.activeAnswer,
                        searching: ws.synthesisSearching
                    )
                }
            }
            .padding(AppTheme.margin)

            Spacer(minLength: 0)

            // Footer / Status bar
            StatusBar(connected: ws.connected, error: ws.lastError)
        }
        .frame(width: AppTheme.windowWidth, height: AppTheme.windowHeight)
        .fontDesign(.rounded)
    }
}

// MARK: - Toolbar

struct ToolbarView: View {
    @ObservedObject var ws: WebSocketClient
    @State private var query: String = ""

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Meeting Buddy")
                    .font(.headline)
                    .foregroundStyle(AppTheme.textPrimary)

                if !ws.availableProjects.isEmpty {
                    Picker("Project", selection: $ws.activeProject) {
                        ForEach(ws.availableProjects, id: \.self) { p in
                            Text(p).tag(p)
                        }
                    }
                    .pickerStyle(.menu)
                    .font(.caption)
                    .foregroundStyle(AppTheme.textSecondary)
                }
            }

            Spacer(minLength: 0)

            // Search / question input
            TextField("Ask a question…", text: $query)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 240)
                .onSubmit {
                    guard !query.isEmpty else { return }
                    Task {
                        await ws.askQuestion(query)
                        query = ""
                    }
                }
        }
        .padding(.horizontal, AppTheme.margin)
        .padding(.vertical, 10)
    }
}

// MARK: - Transcript

struct TranscriptView: View {
    let segments: [TranscriptSegment]

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(segments.enumerated()), id: \.offset) { idx, seg in
                        Text(seg.text)
                            .font(.body)
                            .foregroundStyle(idx == segments.count - 1 ? AppTheme.textPrimary : AppTheme.textSecondary)
                            .id(idx)
                    }
                }
                .padding(.horizontal, AppTheme.margin)
            }
            .onChange(of: segments.count) { _ in
                withAnimation {
                    proxy.scrollTo(segments.count - 1, anchor: .bottom)
                }
            }
        }
        .frame(maxHeight: 200)
    }
}

// MARK: - Answer Card

struct AnswerCard: View {
    let question: String
    let answer: ActiveAnswer?
    let searching: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.spacing) {
            // Question
            if !question.isEmpty {
                Text(question)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppTheme.accentBlue)
            }

            // Searching indicator
            if searching {
                HStack(spacing: 6) {
                    ProgressView()
                        .scaleEffect(0.7)
                    Text("Searching…")
                        .font(.caption)
                        .foregroundStyle(AppTheme.textSecondary)
                }
            }

            // One-liner
            if let ans = answer, let oneLiner = ans.one_liner, !oneLiner.isEmpty {
                Text(oneLiner)
                    .font(.body)
                    .foregroundStyle(AppTheme.textPrimary)
            }

            // Bullets
            if let bullets = answer?.bullets, !bullets.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(bullets, id: \.self) { bullet in
                        HStack(alignment: .top, spacing: 6) {
                            Text("•")
                                .foregroundStyle(AppTheme.accentBlue)
                            Text(bullet)
                                .foregroundStyle(AppTheme.textSecondary)
                        }
                        .font(.callout)
                    }
                }
            }
        }
        .padding(AppTheme.margin)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.2))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Status Bar

struct StatusBar: View {
    let connected: Bool
    let error: String?

    var body: some View {
        HStack {
            Circle()
                .fill(connected ? Color.green : Color.red)
                .frame(width: 6, height: 6)

            Text(connected ? "Connected" : (error ?? "Disconnected"))
                .font(.caption2)
                .foregroundStyle(AppTheme.textSecondary)

            Spacer()

            Text("Alt+Space to toggle")
                .font(.caption2)
                .foregroundStyle(AppTheme.textSecondary.opacity(0.5))
        }
        .padding(.horizontal, AppTheme.margin)
        .padding(.vertical, 6)
        .background(Color.black.opacity(0.15))
    }
}
