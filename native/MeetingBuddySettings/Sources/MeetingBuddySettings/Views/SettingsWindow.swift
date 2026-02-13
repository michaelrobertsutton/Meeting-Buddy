import SwiftUI

enum SettingsSection: String, CaseIterable, Identifiable {
    case general = "General"
    case documents = "Documents"
    case account = "Account"

    var id: String { rawValue }

    var systemImage: String {
        switch self {
        case .general: return "gearshape"
        case .documents: return "doc.text"
        case .account: return "person.circle"
        }
    }
}

struct SettingsWindow: View {

    @EnvironmentObject var store: SettingsStore
    @State private var selection: SettingsSection? = .general

    var body: some View {
        NavigationSplitView {
            List(SettingsSection.allCases, selection: $selection) { section in
                Label(section.rawValue, systemImage: section.systemImage)
                    .tag(section)
            }
            .navigationSplitViewColumnWidth(180)
        } detail: {
            Group {
                switch selection ?? .general {
                case .general:
                    GeneralView()
                case .documents:
                    DocumentsView()
                case .account:
                    AccountView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .frame(minWidth: 700, minHeight: 500)
        .alert("Error", isPresented: Binding(
            get: { store.errorMessage != nil },
            set: { newValue in
                if newValue == false { store.errorMessage = nil }
            }
        ), actions: {
            Button("OK") { store.errorMessage = nil }
        }, message: {
            Text(store.errorMessage ?? "")
        })
        .overlay(alignment: .bottom) {
            if let msg = store.toastMessage {
                Text(msg)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
                    .padding(.bottom, 16)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.2), value: store.toastMessage)
        .toolbar {
            if !store.isConnected {
                ToolbarItem(placement: .automatic) {
                    if store.reconnecting {
                        HStack(spacing: 8) {
                            ProgressView()
                                .controlSize(.small)
                            Text("Reconnecting…")
                        }
                        .help("Backend not running — start with: python -m backend.main")
                    } else {
                        Label("Not connected", systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.orange)
                            .help("Backend not running — start with: python -m backend.main")
                    }
                }
            }
        }
    }
}
