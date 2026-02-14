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
                TranscriptView(segments: ws.segments)

                // Answer card (when active)
                if !ws.oneLiner.isEmpty || ws.synthesisSearching {
                    AnswerCard(
                        question: ws.activeQuestion,
                        answer: ws.activeAnswer,
                        searching: ws.synthesisSearching
                    )
                }
            }
            .padding(AppTheme.margin)
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

// MARK: - Toolbar

struct HUDToolbarView: View {
    @ObservedObject var ws: WebSocketClient

    @State private var manualQuestion: String = ""
    @FocusState private var isQuestionFocused: Bool

    @State private var hoveringExport: Bool = false
    @State private var hoveringSettings: Bool = false
    @State private var hoveringPin: Bool = false

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


                // Right: icon buttons
                HStack(spacing: 10) {
                    toolbarButton(
                        systemName: "square.and.arrow.up",
                        help: "Export",
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
                        help: "Pin",
                        hovering: $hoveringPin
                    ) {
                        Task { await ws.togglePin() }
                    }

                    Button {
                        NotificationCenter.default.post(name: .meetingBuddyHUDHide, object: nil)
                    } label: {
                        Image(systemName: "chevron.down.circle")
                            .frame(width: 28, height: 28)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(AppTheme.textSecondary)
                    .opacity(0.85)
                    .help("Hide (Alt+Space)")
                }
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
        }
        .buttonStyle(.plain)
        .foregroundStyle(AppTheme.accentBlue)
        .opacity(hovering.wrappedValue ? 0.75 : 1.0)
        .onHover { hovering.wrappedValue = $0 }
        .help(help)
    }
}

// MARK: - Transcript

struct TranscriptView: View {
    let segments: [TranscriptSegment]

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 4) {
                    if segments.isEmpty {
                        Text("Listening…")
                            .font(.body)
                            .foregroundStyle(AppTheme.textSecondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, AppTheme.margin)
                            .padding(.vertical, 12)
                    } else {
                        ForEach(Array(segments.enumerated()), id: \.offset) { idx, seg in
                            Text(seg.text)
                                .font(.body)
                                .foregroundStyle(idx == segments.count - 1 ? AppTheme.textPrimary : AppTheme.textSecondary)
                                .id(idx)
                        }
                        .padding(.horizontal, AppTheme.margin)
                    }
                }
            }
            .onChange(of: segments.count) { _ in
                guard !segments.isEmpty else { return }
                withAnimation {
                    proxy.scrollTo(segments.count - 1, anchor: .bottom)
                }
            }
        }
        .frame(minHeight: 120, maxHeight: 200)
    }
}

// MARK: - Answer Card

struct AnswerCard: View {
    let question: String
    let answer: ActiveAnswer?
    let searching: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.spacing) {
            // Question
            if !question.isEmpty {
                Text(question)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppTheme.accentBlue)
            }

            // Searching indicator
            if searching {
                HStack(spacing: 6) {
                    ProgressView()
                        .scaleEffect(0.7)
                    Text("Searching…")
                        .font(.caption)
                        .foregroundStyle(AppTheme.textSecondary)
                }
            }

            // One-liner
            if let ans = answer, let oneLiner = ans.one_liner, !oneLiner.isEmpty {
                Text(oneLiner)
                    .font(.body)
                    .foregroundStyle(AppTheme.textPrimary)
            }

            // Bullets
            if let bullets = answer?.bullets, !bullets.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(bullets, id: \.self) { bullet in
                        HStack(alignment: .top, spacing: 6) {
                            Text("•")
                                .foregroundStyle(AppTheme.accentBlue)
                            Text(bullet)
                                .foregroundStyle(AppTheme.textSecondary)
                        }
                        .font(.callout)
                    }
                }
            }
        }
        .padding(AppTheme.margin)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.2))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

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
