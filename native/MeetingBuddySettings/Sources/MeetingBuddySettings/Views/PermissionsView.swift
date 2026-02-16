import SwiftUI
import AppKit
import AVFoundation
import CoreGraphics

struct PermissionsView: View {
    @EnvironmentObject var store: SettingsStore

    private enum PrivacyPane: String {
        case screenCapture = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        case microphone = "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
    }

    private enum PermissionState {
        case granted
        case notGranted
        case unknown

        var iconName: String {
            switch self {
            case .granted: return "checkmark.circle.fill"
            case .notGranted: return "exclamationmark.triangle.fill"
            case .unknown: return "questionmark.circle.fill"
            }
        }

        var color: Color {
            switch self {
            case .granted: return .green
            case .notGranted: return .red
            case .unknown: return .secondary
            }
        }

        var a11yLabel: String {
            switch self {
            case .granted: return "granted"
            case .notGranted: return "not granted"
            case .unknown: return "unknown"
            }
        }
    }

    @State private var screenRecordingGrantedLocal: Bool = false
    @State private var microphoneGrantedLocal: Bool = false

    private var runtimeScreenRecordingGranted: Bool {
        guard let status = store.audioStatus else { return false }
        return status.running
            || status.frames_received > 0
            || status.receiving_audio
            || status.receiving_non_silent_audio
    }

    private var screenRecordingState: PermissionState {
        if runtimeScreenRecordingGranted || screenRecordingGrantedLocal {
            return .granted
        }
        return store.isConnected ? .notGranted : .unknown
    }

    private var microphoneState: PermissionState {
        if microphoneGrantedLocal { return .granted }
        // Mic permission is per-executable; the Settings helper can report false
        // even when the main app is granted.
        return .unknown
    }

    var body: some View {
        Form {
            Section {
                Text("Meeting Buddy needs the following macOS permissions to capture system audio and run correctly. Open each pane to grant or check access.")
                    .foregroundStyle(.secondary)
            }

            Section("Required") {
                permissionRow(
                    title: "Screen Recording",
                    state: screenRecordingState,
                    description: "Required for capturing system audio (e.g. meeting audio, browser playback) via ScreenCaptureKit. Grant access to \"Meeting Buddy\" (or Terminal when running from the command line).",
                    buttonTitle: "Open Screen Recording settings",
                    urlString: PrivacyPane.screenCapture.rawValue
                )
            }

            Section("Optional") {
                permissionRow(
                    title: "Microphone",
                    state: microphoneState,
                    description: "Optional; only needed if you add microphone input in the future. Not required for system audio capture.",
                    buttonTitle: "Open Microphone settings",
                    urlString: PrivacyPane.microphone.rawValue
                )
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Permissions")
        .onAppear {
            checkPermissions()
            Task { await store.fetchAudioStatus() }
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            checkPermissions()
            Task { await store.fetchAudioStatus() }
        }
    }

    private func checkPermissions() {
        screenRecordingGrantedLocal = CGPreflightScreenCaptureAccess()
        microphoneGrantedLocal = AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
    }

    private func permissionRow(
        title: String,
        state: PermissionState,
        description: String,
        buttonTitle: String,
        urlString: String
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: state.iconName)
                    .foregroundStyle(state.color)
                    .accessibilityLabel("\(title): \(state.a11yLabel)")
                Text(title)
                    .font(.headline)
            }
            Text(description)
                .font(.caption)
                .foregroundStyle(.secondary)
            Button(buttonTitle) {
                if let url = URL(string: urlString) {
                    NSWorkspace.shared.open(url)
                }
            }
        }
        .padding(.vertical, 4)
    }
}
