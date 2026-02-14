import SwiftUI

// MARK: - Status Bar

struct HUDStatusBarView: View {
    let connectionState: WebSocketClient.ConnectionState
    let isPinned: Bool

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
        HStack(spacing: 10) {
            // Processed locally badge
            Label("Processed Locally", systemImage: "lock.fill")
                .font(.caption2)
                .foregroundStyle(AppTheme.textSecondary)
                .padding(.vertical, 4)
                .padding(.horizontal, 8)
                .background(
                    Capsule().fill(AppTheme.accentBlue.opacity(0.10))
                )

            // Connection status
            HStack(spacing: 6) {
                Circle()
                    .fill(connectionDotColor)
                    .frame(width: 6, height: 6)
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
                    .foregroundStyle(AppTheme.accentBlue)
                    .transition(.opacity)
            } else {
                // Keep layout stable when pinned state toggles.
                Color.clear.frame(width: 0, height: 0)
            }
        }
        .padding(.horizontal, 16)
        .frame(height: 28)
        .background(Color.black.opacity(0.15))
    }
}
