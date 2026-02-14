import SwiftUI

// MARK: - Transcript

struct TranscriptView: View {
    let segments: [TranscriptSegment]
    let lastSegmentAt: Date?

    @State private var now: Date = Date()
    @State private var listeningPulse: Bool = false

    var body: some View {
        ScrollViewReader { proxy in
            ZStack(alignment: .topLeading) {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(segments.enumerated()), id: \.offset) { idx, seg in
                            Text(seg.text)
                                .font(.body)
                                .foregroundStyle(Color.white.opacity(opacityForIndex(idx, total: segments.count)))
                                .id(idx)
                        }
                        .padding(.horizontal, AppTheme.margin)

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

                if isIdle {
                    HStack(spacing: 8) {
                        Circle()
                            .fill(AppTheme.accentBlue)
                            .frame(width: 6, height: 6)
                            .scaleEffect(listeningPulse ? 1.0 : 0.6)
                            .animation(
                                .easeInOut(duration: 1.2).repeatForever(autoreverses: true),
                                value: listeningPulse
                            )

                        Text("Listening…")
                            .font(.caption)
                            .foregroundStyle(AppTheme.textSecondary)
                    }
                    .padding(.horizontal, AppTheme.margin)
                    .padding(.top, 12)
                    .onAppear { listeningPulse = true }
                    .onChange(of: isIdle) { idle in
                        listeningPulse = idle
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
        if index == latest { return 1.0 }
        if index == latest - 1 { return 0.75 }
        if index == latest - 2 { return 0.55 }
        return 0.40
    }
}
