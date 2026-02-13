import SwiftUI

struct ContentView: View {
    @ObservedObject var ws: WebSocketClient

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text("Meeting Buddy")
                    .font(.system(size: 22, weight: .semibold, design: .rounded))

                Spacer()

                HStack(spacing: 6) {
                    Circle()
                        .fill(ws.connected ? Color.green.opacity(0.9) : Color.red.opacity(0.9))
                        .frame(width: 8, height: 8)

                    Text(ws.connected ? "Connected" : "Disconnected")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let err = ws.lastError, !err.isEmpty {
                Text("Error: \(err)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            GroupBox("Active Question") {
                Text(ws.activeQuestion.isEmpty ? "Listening…" : ws.activeQuestion)
                    .font(.headline)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            GroupBox("Answer") {
                Text(ws.oneLiner.isEmpty ? "Waiting…" : ws.oneLiner)
                    .font(.body.weight(.semibold))
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            GroupBox("Transcript") {
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(ws.segments.suffix(30), id: \.self) { seg in
                            Text(seg.text)
                                .font(.callout)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 220)
            }

            HStack {
                Button("Reconnect") {
                    ws.connect()
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Disconnect") {
                    ws.disconnect()
                }

                Spacer()
            }

            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(width: 420, height: 700)
        .background(.ultraThinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.white.opacity(0.12), lineWidth: 0.5)
        )
        .padding(8)
    }
}
