import SwiftUI

// MARK: - Toolbar

struct HUDToolbarView: View {
    @ObservedObject var ws: WebSocketClient

    @State private var manualQuestion: String = ""
    @FocusState private var isQuestionFocused: Bool

    @State private var hoveringExport: Bool = false
    @State private var hoveringSettings: Bool = false
    @State private var hoveringPin: Bool = false

    @State private var lastProjectSelection: String? = nil

    var body: some View {
        ZStack {
            // Drag region behind the toolbar content
            WindowDragRegion()

            HStack(spacing: 12) {
                // Left: Project picker
                Picker("Project", selection: $ws.activeProject) {
                    if ws.availableProjects.isEmpty {
                        Text("(default)").tag("")
                    }
                    ForEach(ws.availableProjects, id: \.self) { p in
                        Text(p).tag(p)
                    }
                }
                .pickerStyle(.menu)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(AppTheme.textPrimary)
                .onChange(of: ws.activeProject) { newValue in
                    // Bootstrap guard:
                    // - First change just seeds lastProjectSelection (e.g., get_settings initial sync)
                    // - Subsequent changes are assumed user-initiated and trigger switch_project
                    guard let last = lastProjectSelection else {
                        lastProjectSelection = newValue
                        return
                    }
                    guard newValue != last else { return }
                    lastProjectSelection = newValue
                    Task { await ws.switchProject(name: newValue) }
                }

                Spacer(minLength: 0)

                // Center: Manual question
                TextField("Ask a question…", text: $manualQuestion)
                    .textFieldStyle(.plain)
                    .focused($isQuestionFocused)
                    .padding(.vertical, 6)
                    .padding(.horizontal, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill(Color.white.opacity(0.08))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(
                                isQuestionFocused ? AppTheme.accentBlue.opacity(0.40) : Color.clear,
                                lineWidth: 1
                            )
                    )
                    .frame(maxWidth: 260)
                    .onSubmit {
                        Task {
                            if manualQuestion.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                await ws.clearQuestionOverride()
                            } else {
                                await ws.setQuestion(manualQuestion)
                            }
                        }
                    }

                Spacer(minLength: 0)


                // Right: icon buttons (zIndex so hits aren't taken by WindowDragRegion)
                HStack(spacing: 10) {
                    toolbarButton(
                        systemName: "square.and.arrow.up",
                        help: "Export session to file (~/.meeting-buddy/exports)",
                        hovering: $hoveringExport
                    ) {
                        Task { await ws.exportSession(format: "markdown") }
                    }

                    toolbarButton(
                        systemName: "gearshape",
                        help: "Settings",
                        hovering: $hoveringSettings
                    ) {
                        do {
                            try SettingsLauncher.launch()
                        } catch {
                            // best-effort; surface error via lastError
                            ws.lastError = error.localizedDescription
                        }
                    }

                    toolbarButton(
                        systemName: ws.isPinned ? "pin.fill" : "pin",
                        help: "Pin current answer to list",
                        hovering: $hoveringPin
                    ) {
                        Task { await ws.togglePin() }
                    }

                    Button {
                        NotificationCenter.default.post(name: .meetingBuddyHUDHide, object: nil)
                    } label: {
                        Image(systemName: "chevron.down.circle")
                            .frame(width: 28, height: 28)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(AppTheme.textSecondary)
                    .opacity(0.85)
                    .help("Hide (Cmd+H). Alt+Space to show again.")
                }
                .zIndex(1)
            }
            .padding(.horizontal, 16)
        }
        .frame(height: 44)
    }

    private func toolbarButton(
        systemName: String,
        help: String,
        hovering: Binding<Bool>,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .frame(width: 28, height: 28)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(AppTheme.accentBlue)
        .opacity(hovering.wrappedValue ? 0.75 : 1.0)
        .onHover { hovering.wrappedValue = $0 }
        .help(help)
    }
}
