import AppKit
import SwiftUI

/// Custom NSPanel for the HUD window with proper floating behavior.
/// Uses a standard visible title bar so macOS traffic lights render in their normal
/// position. The content view starts strictly below the title bar, so the window
/// chrome provides the rounded corners — no custom clipShape is needed on the SwiftUI
/// side and there is no double-corner artefact.
final class HUDPanel: NSPanel {
    init() {
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: AppTheme.windowWidth, height: AppTheme.windowHeight),
            styleMask: [.nonactivatingPanel, .titled, .closable, .resizable],
            backing: .buffered,
            defer: false
        )

        title = "Meeting Buddy"

        // Floating panel behavior
        level = .floating
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        isMovableByWindowBackground = true
        hidesOnDeactivate = false

        // Standard title bar: traffic lights in their natural position, content below.
        titlebarAppearsTransparent = false
        titleVisibility = .visible

        minSize = NSSize(width: 340, height: 400)

        isOpaque = false
        backgroundColor = .clear
    }

    // Toggle window level between floating (always-on-top) and normal (can go behind).
    func setFloating(_ floating: Bool) {
        level = floating ? .floating : .normal
    }
}

/// Delegate so the red close button hides the HUD instead of closing the app
private final class HUDPanelCloseDelegate: NSObject, NSWindowDelegate {
    let onClose: () -> Void
    init(onClose: @escaping () -> Void) { self.onClose = onClose }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        onClose()
        return false
    }
}

/// Controller to manage the HUD panel lifecycle
final class HUDPanelController {
    private var panel: HUDPanel?
    private var hostingView: NSHostingView<AnyView>?
    private var closeDelegate: HUDPanelCloseDelegate?

    /// Show the HUD with the given SwiftUI content
    func show<Content: View>(@ViewBuilder content: () -> Content) {
        if panel == nil {
            panel = HUDPanel()
            closeDelegate = HUDPanelCloseDelegate { [weak self] in
                self?.hide()
            }
            panel?.delegate = closeDelegate
            restorePosition()
        }

        guard let panel = panel else { return }

        let rootView = AnyView(
            ZStack {
                // Background material — fills the content view; window chrome clips corners
                VisualEffectView(material: .hudWindow, blendingMode: .behindWindow)

                content()
            }
        )

        if hostingView == nil {
            let hosting = NSHostingView(rootView: rootView)
            let contentFrame = panel.contentView?.bounds ?? NSRect(x: 0, y: 0, width: AppTheme.windowWidth, height: AppTheme.windowHeight)
            hosting.frame = contentFrame
            hosting.autoresizingMask = [.width, .height]
            panel.contentView?.addSubview(hosting)
            hostingView = hosting
        } else {
            hostingView?.rootView = rootView
        }

        panel.makeKeyAndOrderFront(nil)

        // Ensure hosting view fills panel after first layout (fixes blank content when bounds were zero)
        if let hosting = hostingView, let contentView = panel.contentView {
            DispatchQueue.main.async {
                hosting.frame = contentView.bounds
            }
        }
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

    func setFloating(_ floating: Bool) {
        panel?.setFloating(floating)
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
