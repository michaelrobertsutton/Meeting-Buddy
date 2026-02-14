import SwiftUI

struct ContentView: View {
    @ObservedObject var ws: WebSocketClient

    var body: some View {
        VStack(spacing: 0) {
            // Header / Toolbar
            HUDToolbarView(ws: ws)

            Divider()
                .background(Color.white.opacity(0.08))

            // Main content area (background so it's never blank)
            VStack(spacing: AppTheme.spacing) {
                // Transcript section
                TranscriptView(segments: ws.segments, lastSegmentAt: ws.lastTranscriptAt)

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
            }
            .padding(AppTheme.margin)
            .animation(.spring(response: 0.4, dampingFraction: 0.7), value: ws.synthesisSearching)
            .animation(.spring(response: 0.4, dampingFraction: 0.7), value: ws.answerPartialText)
            .animation(.spring(response: 0.4, dampingFraction: 0.7), value: ws.activeAnswer?.one_liner ?? "")
            .animation(.spring(response: 0.4, dampingFraction: 0.7), value: ws.synthesisError ?? "")
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(Color.black.opacity(0.12))

            Spacer(minLength: 0)

            Divider()
                .background(Color.white.opacity(0.08))

            // Footer / Status bar
            HUDStatusBarView(
                connectionState: ws.connectionState,
                isPinned: ws.isPinned
            )
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .fontDesign(.rounded)
    }
}
