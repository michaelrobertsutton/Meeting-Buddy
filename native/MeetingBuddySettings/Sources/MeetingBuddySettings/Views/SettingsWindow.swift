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
        .alert("Error", isPresented: .constant(store.errorMessage != nil), actions: {
            Button("OK") { store.errorMessage = nil }
        }, message: {
            Text(store.errorMessage ?? "")
        })
        .toolbar {
            if !store.isConnected {
                ToolbarItem(placement: .automatic) {
                    Label("Not connected", systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                        .help("Backend not connected — make sure Meeting Buddy is running")
                }
            }
        }
    }
}
