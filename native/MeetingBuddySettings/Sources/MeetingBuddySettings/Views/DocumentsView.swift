import SwiftUI
import AppKit

struct DocumentsView: View {

    @EnvironmentObject var store: SettingsStore
    @State private var selection = Set<DocInfo.ID>()

    var body: some View {
        VStack(spacing: 0) {
            if store.isIngesting {
                HStack {
                    ProgressView()
                        .controlSize(.small)
                    Text(store.ingestProgress ?? "Ingesting…")
                        .foregroundStyle(.secondary)
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.bar)

                Divider()
            }

            if store.docs.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.system(size: 48))
                        .foregroundStyle(.secondary)
                    Text("No Documents")
                        .font(.headline)
                    Text("Add files or folders to ingest into the active project")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                Table(store.docs, selection: $selection) {
                    TableColumn("Title") { doc in
                        Text(doc.title)
                    }
                    TableColumn("Chunks") { doc in
                        Text(doc.chunkCount.map { "\($0)" } ?? "—")
                            .foregroundStyle(.secondary)
                    }
                    .width(60)
                    TableColumn("Source") { doc in
                        Text(doc.source ?? "—")
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
            }
        }
        .navigationTitle("Documents")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    pickFiles()
                } label: {
                    Label("Add Files", systemImage: "doc.badge.plus")
                }
                .disabled(store.isIngesting)

                Button {
                    pickFolder()
                } label: {
                    Label("Add Folder", systemImage: "folder.badge.plus")
                }
                .disabled(store.isIngesting)

                Button(role: .destructive) {
                    deleteSelected()
                } label: {
                    Label("Delete", systemImage: "trash")
                }
                .disabled(selection.isEmpty || store.isIngesting)
            }
        }
        .task {
            await store.fetchDocs()
        }
    }

    private func pickFiles() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowedContentTypes = [.pdf, .plainText, .html]
        if panel.runModal() == .OK {
            let paths = panel.urls.map { $0.path }
            Task { await store.ingestFiles(paths) }
        }
    }

    private func pickFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            Task { await store.ingestFiles([url.path]) }
        }
    }

    private func deleteSelected() {
        let titles = selection
        Task {
            for title in titles {
                await store.deleteDoc(title)
            }
            selection.removeAll()
        }
    }
}
