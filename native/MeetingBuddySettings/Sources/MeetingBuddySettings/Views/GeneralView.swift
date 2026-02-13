import SwiftUI

struct GeneralView: View {

    @EnvironmentObject var store: SettingsStore
    @State private var showNewProject = false
    @State private var newProjectName = ""
    @State private var showDeleteConfirm = false

    var body: some View {
        Form {
            Section("Active Project") {
                if store.projects.isEmpty {
                    Text("No projects — create one below")
                        .foregroundStyle(.secondary)
                } else {
                    Picker("Project", selection: Binding(
                        get: { store.activeProject },
                        set: { name in Task { await store.switchProject(name) } }
                    )) {
                        ForEach(store.projects) { project in
                            Text(project.name).tag(project.name)
                        }
                    }
                    .pickerStyle(.menu)

                    if !store.activeProject.isEmpty {
                        Button(role: .destructive) {
                            showDeleteConfirm = true
                        } label: {
                            Label("Delete \"\(store.activeProject)\"", systemImage: "trash")
                        }
                        .confirmationDialog(
                            "Delete project \"\(store.activeProject)\"?",
                            isPresented: $showDeleteConfirm,
                            titleVisibility: .visible
                        ) {
                            Button("Delete", role: .destructive) {
                                let name = store.activeProject
                                Task { await store.deleteProject(name) }
                            }
                            Button("Cancel", role: .cancel) {}
                        } message: {
                            Text("All ingested documents will be removed. This cannot be undone.")
                        }
                    }
                }

                Button {
                    newProjectName = ""
                    showNewProject = true
                } label: {
                    Label("New Project…", systemImage: "plus")
                }
            }

            Section("Keyboard Shortcuts") {
                shortcutRow("Toggle overlay", key: "⌥Space")
                shortcutRow("Open Settings", key: "⌘,")
                shortcutRow("Pin answer", key: "⌘⇧P")
                shortcutRow("Clear session", key: "⌘K")
            }
        }
        .formStyle(.grouped)
        .navigationTitle("General")
        .sheet(isPresented: $showNewProject) {
            NewProjectSheet(name: $newProjectName) { name in
                Task { await store.createProject(name) }
            }
        }
    }

    private func shortcutRow(_ label: String, key: String) -> some View {
        HStack {
            Text(label)
            Spacer()
            Text(key)
                .font(.system(.body, design: .monospaced))
                .foregroundStyle(.secondary)
        }
    }
}

struct NewProjectSheet: View {
    @Binding var name: String
    let onCreate: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 20) {
            Text("New Project")
                .font(.headline)
            TextField("Project name", text: $name)
                .textFieldStyle(.roundedBorder)
                .frame(width: 280)
            HStack {
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Button("Create") {
                    guard !name.isEmpty else { return }
                    onCreate(name)
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(name.isEmpty)
            }
        }
        .padding(24)
        .frame(minWidth: 320)
    }
}
