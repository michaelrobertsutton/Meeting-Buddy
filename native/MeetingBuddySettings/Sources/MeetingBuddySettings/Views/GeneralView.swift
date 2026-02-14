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

            GroupBox("Keyboard Shortcuts") {
                Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 8) {
                    GridRow {
                        Text("Alt+Space").monospaced()
                        Text("Toggle overlay")
                    }
                    GridRow {
                        Text("Cmd+,").monospaced()
                        Text("Open Settings")
                    }
                    GridRow {
                        Text("Cmd+K").monospaced()
                        Text("Clear session")
                    }
                    GridRow {
                        Text("Cmd+Shift+P").monospaced()
                        Text("Pin/unpin answer")
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
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
