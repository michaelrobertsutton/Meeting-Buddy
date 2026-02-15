import SwiftUI

// MARK: - Status Bar

struct HUDStatusBarView: View {
    let connectionState: WebSocketClient.ConnectionState
    let isPinned: Bool
    var lastExportPath: String? = nil
    var ttftMs: Double? = nil
    var totalMs: Double? = nil

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
        HStack(alignment: .center, spacing: 10) {
            // Processed Locally badge — 16pt from leading edge
            Label("Processed Locally", systemImage: "lock.fill")
                .font(.caption2)
                .imageScale(.small)
                .foregroundStyle(AppTheme.textSecondary)
                .padding(.vertical, 3)
                .padding(.horizontal, 8)
                .background(Capsule().fill(AppTheme.accentBlue.opacity(0.10)))

            // Connection status
            HStack(alignment: .center, spacing: 6) {
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

                Text(connectionLabel)
                    .font(.caption2)
                    .foregroundStyle(AppTheme.textSecondary)

                if let path = lastExportPath {
                    Text("Exported to \(path)")
                        .font(.caption2)
                        .foregroundStyle(Color(hex: "#66BB6A"))
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            .onAppear { pulse = (connectionState == .connecting) }
            .onChange(of: connectionState) { newValue in
                if newValue == .connecting {
                    pulse = false
                    DispatchQueue.main.async { pulse = true }
                } else {
                    pulse = false
                }
            }

            Spacer(minLength: 0)

            if let ttftMs {
                Text(String(format: "TTFT %.0fms", ttftMs))
                    .font(.caption2)
                    .foregroundStyle(AppTheme.textSecondary)
            }

            if let totalMs {
                Text(String(format: "Total %.0fms", totalMs))
                    .font(.caption2)
                    .foregroundStyle(AppTheme.textSecondary)
            }

            if isPinned {
                Label("On Top", systemImage: "pin.fill")
                    .font(.caption2)
                    .imageScale(.small)
                    .foregroundStyle(AppTheme.accentBlue)
                    .transition(.opacity)
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 6)
        .padding(.bottom, 16)
        .background(Color.black.opacity(0.15))
    }
}
