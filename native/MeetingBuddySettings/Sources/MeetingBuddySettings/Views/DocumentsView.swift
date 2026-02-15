import SwiftUI
import AppKit

struct DocumentsView: View {

    @EnvironmentObject var store: SettingsStore
    @State private var selection = Set<DocInfo.ID>()
    @State private var sortOrder: [KeyPathComparator<DocInfo>] = [KeyPathComparator(\.title, order: .forward)]
    @State private var showPriorityInfo = false
    @AppStorage("defaultDocPriority") private var defaultDocPriority: String = "normal"

    private let priorityOptions = ["low", "normal", "high"]

    private var sortedDocs: [DocInfo] {
        store.docs.sorted(using: sortOrder)
    }

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
                Table(sortedDocs, selection: $selection, sortOrder: $sortOrder) {
                    TableColumn("Name", value: \.title) { doc in
                        Text(doc.title)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                    TableColumn("Type") { doc in
                        Text(doc.fileType)
                            .foregroundStyle(.secondary)
                    }
                    .width(80)
                    TableColumn("Size") { doc in
                        Text(doc.sizeLabel)
                            .monospacedDigit()
                            .foregroundStyle(.secondary)
                    }
                    .width(80)
                    TableColumn("Status") { doc in
                        Text(doc.statusLabel)
                            .foregroundStyle(.secondary)
                    }
                    .width(100)
                    TableColumn("Priority") { doc in
                        Menu {
                            ForEach(priorityOptions, id: \.self) { option in
                                Button(option.capitalized) {
                                    Task { await store.updateDocMeta(title: doc.title, priority: option) }
                                }
                            }
                        } label: {
                            HStack(spacing: 4) {
                                Text((doc.priority ?? "normal").capitalized)
                                Image(systemName: "chevron.up.chevron.down")
                                    .font(.caption2)
                            }
                            .foregroundStyle(.secondary)
                        }
                        .menuStyle(.borderlessButton)
                    }
                    .width(110)
                }
                .tableStyle(.inset)
                .contextMenu {
                    if let single = selection.first {
                        Button("Remove Document", role: .destructive) {
                            Task { await store.deleteDoc(single) }
                            selection.remove(single)
                        }
                    }
                }
            }

            Divider()

            // Footer: Default Priority picker + info
            HStack(spacing: 8) {
                Text("Default Priority for new docs:")
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                Picker("", selection: $defaultDocPriority) {
                    ForEach(priorityOptions, id: \.self) { option in
                        Text(option.capitalized).tag(option)
                    }
                }
                .labelsHidden()
                .pickerStyle(.menu)
                .frame(width: 90)

                Button {
                    showPriorityInfo.toggle()
                } label: {
                    Image(systemName: "info.circle")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .popover(isPresented: $showPriorityInfo, arrowEdge: .top) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Document Priority & RAG Weighting")
                            .font(.headline)
                        Text("Priority controls how strongly a document influences synthesis answers.\n\n• High — chunks from this doc score a 2× boost when retrieved, making them appear more often in answers.\n• Normal — standard retrieval weight.\n• Low — chunks are retrieved with half weight; useful for background or reference material you want available but not dominant.")
                            .font(.body)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(16)
                    .frame(maxWidth: 320)
                }

                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(.bar)
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
