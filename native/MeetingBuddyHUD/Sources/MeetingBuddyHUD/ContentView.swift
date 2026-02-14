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

                // Synthesis card (when active)
                if ws.synthesisSearching || !ws.answerPartialText.isEmpty || ws.activeAnswer != nil || ws.synthesisError != nil {
                    SynthesisCardView(
                        question: ws.activeQuestion,
                        answer: ws.activeAnswer,
                        searching: ws.synthesisSearching,
                        partialText: ws.answerPartialText,
                        error: ws.synthesisError
                    )
                    .transition(.asymmetric(insertion: .move(edge: .top).combined(with: .opacity), removal: .opacity))
                }
            }
            .padding(AppTheme.margin)
            .animation(.spring(response: 0.4, dampingFraction: 0.7), value: ws.synthesisSearching)
            .animation(.spring(response: 0.4, dampingFraction: 0.7), value: ws.answerPartialText)
            .animation(.spring(response: 0.4, dampingFraction: 0.7), value: ws.activeAnswer?.one_liner ?? "")
            .animation(.spring(response: 0.4, dampingFraction: 0.7), value: ws.synthesisError ?? "")
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
        .frame(width: AppTheme.windowWidth, height: AppTheme.windowHeight)
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

// MARK: - Synthesis Card

struct SynthesisCardView: View {
    let question: String
    let answer: ActiveAnswer?
    let searching: Bool
    let partialText: String
    let error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("DIRECT ANSWER")
                .font(.caption2)
                .textCase(.uppercase)
                .kerning(0.5)
                .foregroundStyle(AppTheme.accentBlue)

            if searching {
                HStack(spacing: 8) {
                    ProgressView()
                        .tint(AppTheme.accentBlue)
                    Text("Searching sources…")
                        .font(.caption)
                        .foregroundStyle(AppTheme.textSecondary)
                }
            }

            if let err = error, !err.isEmpty {
                Text(err)
                    .font(.body)
                    .foregroundStyle(Color(hex: "#F44336"))
            }

            if !partialText.isEmpty {
                Text(partialText)
                    .font(.body)
                    .italic()
                    .foregroundStyle(AppTheme.accentBlue)
            }

            if let one = answer?.one_liner, !one.isEmpty {
                Text(one)
                    .font(.body)
                    .foregroundStyle(AppTheme.textPrimary)
            }

            if let bullets = answer?.bullets, !bullets.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(bullets, id: \.self) { bullet in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "circle.fill")
                                .font(.system(size: 5, weight: .semibold))
                                .foregroundStyle(AppTheme.accentBlue)
                                .padding(.top, 6)

                            Text(bullet)
                                .font(.body)
                                .foregroundStyle(AppTheme.textPrimary)
                        }
                    }
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(.ultraThinMaterial)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color.white.opacity(0.04))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(confidenceColor.opacity(0.6), lineWidth: 1)
        )
    }

    private var confidenceColor: Color {
        let c = answer?.confidence ?? 0
        if c > 0.6 { return Color(hex: "#4CAF50") }
        if c >= 0.3 { return Color(hex: "#FFC107") }
        return Color(hex: "#F44336")
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
