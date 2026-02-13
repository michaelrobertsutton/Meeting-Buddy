import SwiftUI

struct ContentView: View {
    @ObservedObject var ws: WebSocketClient

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Meeting Buddy")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Text(ws.connected ? "Connected" : "Disconnected")
                    .font(.caption)
                    .foregroundStyle(ws.connected ? .green : .red)
            }

            if let err = ws.lastError {
                Text("Error: \(err)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
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

            Spacer(minLength: 0)
        }
        .padding(12)
        .background(.ultraThinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.white.opacity(0.12), lineWidth: 0.5)
        )
    }
}
