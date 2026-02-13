import SwiftUI

struct ToolbarView: View {
    @ObservedObject var ws: WebSocketClient

    @State private var query: String = ""

    var body: some View {
        HStack(spacing: 12) {
            // Left: App name + project picker
            VStack(alignment: .leading, spacing: 2) {
                Text("Meeting Buddy")
                    .font(.headline)
                    .foregroundStyle(.primary)

                Picker("Project", selection: $ws.activeProject) {
                    if ws.availableProjects.isEmpty {
                        Text("(default)").tag("")
                    }
                    ForEach(ws.availableProjects, id: \.self) { p in
                        Text(p).tag(p)
                    }
                }
                .pickerStyle(.menu)
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            Spacer(minLength: 0)

            // Center: Search / Type question
            TextField("Search / Type question", text: $query)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 360)

            Spacer(minLength: 0)

            // Right: SF Symbols actions
            HStack(spacing: 10) {
                Button {
                    // TODO (#120 follow-on): hook up to export command.
                } label: {
                    Image(systemName: "square.and.arrow.up")
                }
                .help("Export")

                Button {
                    do {
                        try SettingsLauncher.launch()
                    } catch {
                        ws.settingsError = error.localizedDescription
                    }
                } label: {
                    Image(systemName: "gearshape")
                }
                .help("Settings")

                Button {
                    // TODO: pinned answers UI
                } label: {
                    Image(systemName: "pin.fill")
                }
                .help("Pinned")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color.clear)
    }
}
