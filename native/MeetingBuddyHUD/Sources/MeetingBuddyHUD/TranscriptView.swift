import SwiftUI
import MeetingBuddyProtocol

// MARK: - Transcript

struct TranscriptView: View {
    let segments: [TranscriptSegment]
    let lastSegmentAt: Date?
    var isListening: Bool = true
    var onTapSegment: ((String) -> Void)? = nil

    @State private var now: Date = Date()
    @State private var listeningPulse: Bool = false

    var body: some View {
        ScrollViewReader { proxy in
            ZStack(alignment: .topLeading) {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(segments.enumerated()), id: \.0) { idx, seg in
                            Text(seg.text)
                                .font(.body)
                                .foregroundStyle(Color.white.opacity(opacityForIndex(idx, total: segments.count)))
                                .id(idx)
                                .contentShape(Rectangle())
                                .onTapGesture {
                                    onTapSegment?(seg.text)
                                }
                        }
                        // Horizontal padding comes from parent ContentView (AppTheme.margin = 16pt)

                        // Anchor for autoscroll
                        Color.clear
                            .frame(height: 1)
                            .id("latest")
                    }
                    .padding(.top, 10)
                    .padding(.bottom, 8)
                }
                .mask(
                    LinearGradient(
                        stops: [
                            .init(color: .clear, location: 0.0),
                            .init(color: .black, location: 0.2),
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .onChange(of: segments.count) { _ in
                    withAnimation(.easeOut(duration: 0.2)) {
                        proxy.scrollTo("latest", anchor: .bottom)
                    }
                }

                if !isListening || isIdle {
                    HStack(spacing: 8) {
                        if isListening {
                            Circle()
                                .fill(AppTheme.accentBlue)
                                .frame(width: 6, height: 6)
                                .scaleEffect(listeningPulse ? 1.0 : 0.6)
                                .animation(
                                    .easeInOut(duration: 1.2).repeatForever(autoreverses: true),
                                    value: listeningPulse
                                )
                        } else {
                            Image(systemName: "pause.fill")
                                .font(.system(size: 8))
                                .foregroundStyle(AppTheme.textSecondary)
                        }

                        Text(isListening ? "Listening…" : "Paused")
                            .font(.caption)
                            .foregroundStyle(AppTheme.textSecondary)
                    }
                    .padding(.top, 12)
                    .onAppear { listeningPulse = isListening }
                    .onChange(of: isIdle) { idle in
                        listeningPulse = idle && isListening
                    }
                    .onChange(of: isListening) { listening in
                        listeningPulse = listening && isIdle
                    }
                }
            }
        }
        .frame(minHeight: 120, maxHeight: 200)
        .onReceive(Timer.publish(every: 0.5, on: .main, in: .common).autoconnect()) { now in
            self.now = now
        }
    }

    private var isIdle: Bool {
        guard !segments.isEmpty else { return true }
        guard let last = lastSegmentAt else { return true }
        return now.timeIntervalSince(last) > 4.0
    }

    private func opacityForIndex(_ index: Int, total: Int) -> Double {
        guard total > 0 else { return 1.0 }
        let latest = total - 1
        if index == latest { return 1.0 }   // Current line: 100% white
        return 0.30                          // Previous lines: 30% (secondary white) for focus
    }
}
