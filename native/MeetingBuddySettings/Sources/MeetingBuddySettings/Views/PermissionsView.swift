import SwiftUI
import AppKit

struct PermissionsView: View {

    private enum PrivacyPane: String {
        case screenCapture = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        case microphone = "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
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
                    description: "Required for capturing system audio (e.g. meeting audio, browser playback) via ScreenCaptureKit. Grant access to \"Meeting Buddy\" (or Terminal when running from the command line).",
                    buttonTitle: "Open Screen Recording settings",
                    urlString: PrivacyPane.screenCapture.rawValue
                )
            }

            Section("Optional") {
                permissionRow(
                    title: "Microphone",
                    description: "Optional; only needed if you add microphone input in the future. Not required for system audio capture.",
                    buttonTitle: "Open Microphone settings",
                    urlString: PrivacyPane.microphone.rawValue
                )
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Permissions")
    }

    private func permissionRow(
        title: String,
        description: String,
        buttonTitle: String,
        urlString: String
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
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
