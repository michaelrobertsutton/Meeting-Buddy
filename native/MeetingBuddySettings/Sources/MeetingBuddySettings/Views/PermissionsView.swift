import SwiftUI
import AppKit
import AVFoundation

struct PermissionsView: View {

    private enum PrivacyPane: String {
        case screenCapture = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        case microphone = "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
    }

    @State private var screenRecordingGranted: Bool = false
    @State private var microphoneGranted: Bool = false

    var body: some View {
        Form {
            Section {
                Text("Meeting Buddy needs the following macOS permissions to capture system audio and run correctly. Open each pane to grant or check access.")
                    .foregroundStyle(.secondary)
            }

            Section("Required") {
                permissionRow(
                    title: "Screen Recording",
                    granted: screenRecordingGranted,
                    description: "Required for capturing system audio (e.g. meeting audio, browser playback) via ScreenCaptureKit. Grant access to \"Meeting Buddy\" (or Terminal when running from the command line).",
                    buttonTitle: "Open Screen Recording settings",
                    urlString: PrivacyPane.screenCapture.rawValue
                )
            }

            Section("Optional") {
                permissionRow(
                    title: "Microphone",
                    granted: microphoneGranted,
                    description: "Optional; only needed if you add microphone input in the future. Not required for system audio capture.",
                    buttonTitle: "Open Microphone settings",
                    urlString: PrivacyPane.microphone.rawValue
                )
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Permissions")
        .onAppear { checkPermissions() }
    }

    private func checkPermissions() {
        screenRecordingGranted = CGPreflightScreenCaptureAccess()
        microphoneGranted = AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
    }

    private func permissionRow(
        title: String,
        granted: Bool,
        description: String,
        buttonTitle: String,
        urlString: String
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: granted ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                    .foregroundStyle(granted ? .green : .orange)
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
