import SwiftUI

// MARK: - Status Bar

struct HUDStatusBarView: View {
    let connectionState: WebSocketClient.ConnectionState
    let isPinned: Bool
    var lastError: String? = nil
    var lastExportPath: String? = nil

    @State private var pulse: Bool = false

    private var connectionDotColor: Color {
        switch connectionState {
        case .connected:
            return Color(hex: "#66BB6A")
        case .connecting:
            return Color(hex: "#FFA726")
        case .disconnected:
            return Color(hex: "#EF5350")
        }
    }

    private var connectionLabel: String {
        switch connectionState {
        case .connected:
            return "Connected"
        case .connecting:
            return "Connecting…"
        case .disconnected:
            return "Not connected"
        }
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            // Processed locally badge
            Label("Processed Locally", systemImage: "lock.fill")
                .font(.caption2)
                .imageScale(.small)
                .foregroundStyle(AppTheme.textSecondary)
                .padding(.vertical, 4)
                .padding(.horizontal, 8)
                .background(
                    Capsule().fill(AppTheme.accentBlue.opacity(0.10))
                )

            // Connection status and feedback
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Image(systemName: "circle.fill")
                        .font(.system(size: 6))
                        .foregroundStyle(connectionDotColor)
                        .scaleEffect(connectionState == .connecting && pulse ? 1.35 : 1.0)
                        .opacity(connectionState == .connecting && pulse ? 0.55 : 1.0)
                        .animation(
                            connectionState == .connecting
                            ? .easeInOut(duration: 0.9).repeatForever(autoreverses: true)
                            : .default,
                            value: pulse
                        )
                        .imageScale(.small)
                        .alignmentGuide(.firstTextBaseline) { d in d[VerticalAlignment.center] }

                    Text(connectionLabel)
                        .font(.caption2)
                        .foregroundStyle(AppTheme.textSecondary)
                }

                if let err = lastError, !err.isEmpty {
                    Text(err)
                        .font(.caption2)
                        .foregroundStyle(Color(hex: "#EF5350"))
                        .lineLimit(1)
                        .truncationMode(.tail)
                } else if let path = lastExportPath {
                    Text("Exported to \(path)")
                        .font(.caption2)
                        .foregroundStyle(Color(hex: "#66BB6A"))
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            .onAppear {
                // Kick off pulse animation (only visible in .connecting)
                pulse = (connectionState == .connecting)
            }
            .onChange(of: connectionState) { newValue in
                // Restart the pulse any time we enter the connecting state.
                if newValue == .connecting {
                    pulse = false
                    DispatchQueue.main.async {
                        pulse = true
                    }
                } else {
                    pulse = false
                }
            }

            Spacer(minLength: 0)

            if isPinned {
                Label("Pinned", systemImage: "pin.fill")
                    .font(.caption2)
                    .imageScale(.small)
                    .foregroundStyle(AppTheme.accentBlue)
                    .transition(.opacity)
            } else {
                // Keep layout stable when pinned state toggles.
                Color.clear.frame(width: 0, height: 0)
            }
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 16)
        .frame(height: 28)
        .background(Color.black.opacity(0.15))
    }
}
