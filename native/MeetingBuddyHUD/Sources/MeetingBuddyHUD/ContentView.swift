import SwiftUI

struct ContentView: View {
    @ObservedObject var ws: WebSocketClient

    var body: some View {
        VStack(spacing: 0) {
            // Header / Toolbar
            HUDToolbarView(ws: ws)

            Divider()
                .background(Color.white.opacity(0.10))

            // Main content area — single continuous material (no inner rounded box; avoids double-corner/notch)
            VStack(spacing: AppTheme.spacing) {
                // Transcript section — tap a segment to set it as the active question
                TranscriptView(segments: ws.segments, lastSegmentAt: ws.lastTranscriptAt, isListening: ws.isListening) { text in
                    Task { await ws.setQuestion(text) }
                }

                // Synthesis card (when active)
                if ws.synthesisSearching || !ws.answerPartialText.isEmpty || ws.activeAnswer != nil || ws.synthesisError != nil {
                    SynthesisCardView(
                        question: ws.activeQuestion,
                        answer: ws.activeAnswer,
                        searching: ws.synthesisSearching,
                        partialText: ws.answerPartialText,
                        error: ws.synthesisError
                    )
                    .transition(.asymmetric(insertion: .move(edge: .top).combined(with: .opacity), removal: .opacity))
                }

                // Q&A history (when at least one answer has accumulated)
                if !ws.qaHistory.isEmpty {
                    QAHistoryView(ws: ws)
                        .transition(.opacity)
                }
            }
            .padding(AppTheme.margin)
            .animation(.spring(response: 0.4, dampingFraction: 0.7), value: ws.synthesisSearching)
            .animation(.spring(response: 0.4, dampingFraction: 0.7), value: ws.answerPartialText)
            .animation(.spring(response: 0.4, dampingFraction: 0.7), value: ws.activeAnswer?.one_liner ?? "")
            .animation(.spring(response: 0.4, dampingFraction: 0.7), value: ws.synthesisError ?? "")
            .animation(.easeInOut(duration: 0.25), value: ws.qaHistory.count)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

            Spacer(minLength: 0)

            // Error banner — slides in above footer when an error is active (#239)
            if let err = ws.lastError, !err.isEmpty {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(Color(hex: "#EF5350"))
                    Text(err)
                        .font(.caption)
                        .foregroundStyle(Color(hex: "#EF5350"))
                        .lineLimit(2)
                    Spacer(minLength: 0)
                    Button {
                        ws.lastError = nil
                    } label: {
                        Image(systemName: "xmark")
                            .font(.caption2)
                            .foregroundStyle(Color.white.opacity(0.60))
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(Color(hex: "#EF5350").opacity(0.15))
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }

            Divider()
                .background(Color.white.opacity(0.10))

            // Footer / Status bar
            HUDStatusBarView(
                connectionState: ws.connectionState,
                isPinned: ws.isWindowFloating,
                lastExportPath: ws.lastExportPath,
                ttftMs: ws.lastTTFTms,
                totalMs: ws.lastTotalMs
            )
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .fontDesign(.rounded)
        .animation(.easeInOut(duration: 0.25), value: ws.lastError)
    }
}
