import SwiftUI

struct AccountView: View {

    @EnvironmentObject var store: SettingsStore
    @State private var showApiKeyField = false
    @State private var apiKeyInput = ""
    @State private var apiKeySaved = false

    var body: some View {
        Form {
            GroupBox {
                oauthSection
            } label: {
                HStack(spacing: 6) {
                    Label("ChatGPT Plus (OAuth)", systemImage: "person.crop.circle")
                    statusBadge(active: store.oauthEmail != nil)
                }
            }

            Divider()

            GroupBox {
                apiKeySection
            } label: {
                HStack(spacing: 6) {
                    Label("OpenAI API Key", systemImage: "key")
                    statusBadge(active: store.hasApiKey)
                }
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Account")
        .animation(.default, value: apiKeySaved)
    }

    private func statusBadge(active: Bool) -> some View {
        Text(active ? "Active" : "Inactive")
            .font(.caption)
            .foregroundStyle(active ? Color.green : Color.secondary)
    }

    @ViewBuilder
    private var oauthSection: some View {
        if let email = store.oauthEmail {
            LabeledContent("Signed in as", value: email)

            if let expiry = store.oauthExpiry {
                LabeledContent("Token expires", value: expiry)
            }

            Button(role: .destructive) {
                Task { await store.logout() }
            } label: {
                Label("Sign out", systemImage: "rectangle.portrait.and.arrow.right")
            }
        } else {
            Text("Not signed in")
                .foregroundStyle(.secondary)

            Button {
                Task { await store.startLogin() }
            } label: {
                Label("Sign in with ChatGPT…", systemImage: "safari")
            }
            .buttonStyle(.borderedProminent)

            Text("Opens browser for OAuth login. Requires a ChatGPT Plus subscription.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private var apiKeySection: some View {
        if store.hasApiKey {
            HStack {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                Text("API key is set")
                Spacer()
                Button("Replace") {
                    apiKeyInput = ""
                    showApiKeyField = true
                }
            }
        }

        if showApiKeyField || !store.hasApiKey {
            VStack(alignment: .leading, spacing: 8) {
                SecureField("sk-…", text: $apiKeyInput)
                    .textFieldStyle(.roundedBorder)

                HStack {
                    Button("Save Key") {
                        guard !apiKeyInput.isEmpty else { return }
                        Task {
                            await store.setApiKey(apiKeyInput)
                            apiKeyInput = ""
                            apiKeySaved = true
                            try? await Task.sleep(nanoseconds: 2_000_000_000)
                            apiKeySaved = false
                        }
                    }
                    .disabled(apiKeyInput.isEmpty)

                    if apiKeySaved {
                        Label("Saved", systemImage: "checkmark")
                            .foregroundStyle(.green)
                            .transition(.opacity)
                    }
                }

                Text("Used when not signed into ChatGPT. Stored locally at ~/.meeting-buddy/config.json")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.top, 4)
        }
    }
}
