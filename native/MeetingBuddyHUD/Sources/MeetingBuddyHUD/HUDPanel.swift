import AppKit
import SwiftUI

/// Custom NSPanel for the HUD window with proper floating behavior
final class HUDPanel: NSPanel {
    init() {
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: AppTheme.windowWidth, height: AppTheme.windowHeight),
            styleMask: [.nonactivatingPanel, .titled, .closable, .fullSizeContentView, .borderless],
            backing: .buffered,
            defer: false
        )

        // Floating panel behavior
        level = .floating
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        isMovableByWindowBackground = true
        hidesOnDeactivate = false

        // Transparent titlebar
        titlebarAppearsTransparent = true
        titleVisibility = .hidden

        // Background: fully transparent window chrome
        isOpaque = false
        backgroundColor = .clear
    }
}

/// Controller to manage the HUD panel lifecycle
final class HUDPanelController {
    private var panel: HUDPanel?
    private var hostingView: NSHostingView<AnyView>?

    /// Show the HUD with the given SwiftUI content
    func show<Content: View>(@ViewBuilder content: () -> Content) {
        if panel == nil {
            panel = HUDPanel()
            restorePosition()
        }

        guard let panel = panel else { return }

        let rootView = AnyView(
            ZStack {
                // Background material
                VisualEffectView(material: .hudWindow, blendingMode: .behindWindow)

                // Content
                content()
            }
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.cornerRadius)
                    .strokeBorder(AppTheme.glassEdge, lineWidth: 0.5)
            )
        )

        if hostingView == nil {
            let hosting = NSHostingView(rootView: rootView)
            hosting.frame = panel.contentView?.bounds ?? .zero
            hosting.autoresizingMask = [.width, .height]
            panel.contentView?.addSubview(hosting)
            hostingView = hosting
        } else {
            hostingView?.rootView = rootView
        }

        panel.makeKeyAndOrderFront(nil)
    }

    /// Hide the HUD
    func hide() {
        savePosition()
        panel?.orderOut(nil)
    }

    /// Toggle visibility
    func toggle<Content: View>(@ViewBuilder content: () -> Content) {
        if let panel = panel, panel.isVisible {
            hide()
        } else {
            show(content: content)
        }
    }

    var isVisible: Bool {
        panel?.isVisible ?? false
    }

    // MARK: - Position persistence

    private let positionKey = "MeetingBuddyHUD.windowPosition"

    private func savePosition() {
        guard let frame = panel?.frame else { return }
        let dict: [String: CGFloat] = ["x": frame.origin.x, "y": frame.origin.y]
        UserDefaults.standard.set(dict, forKey: positionKey)
    }

    private func restorePosition() {
        guard let dict = UserDefaults.standard.dictionary(forKey: positionKey) as? [String: CGFloat],
              let x = dict["x"], let y = dict["y"] else {
            // Center on screen
            panel?.center()
            return
        }
        panel?.setFrameOrigin(NSPoint(x: x, y: y))
    }
}

/// NSVisualEffectView wrapper for SwiftUI
struct VisualEffectView: NSViewRepresentable {
    let material: NSVisualEffectView.Material
    let blendingMode: NSVisualEffectView.BlendingMode

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = .active
        return view
    }

    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
        nsView.material = material
        nsView.blendingMode = blendingMode
    }
}
