import AppKit
import SwiftUI

final class HUDPanelController {
    private var panel: NSPanel?

    func show<Content: View>(@ViewBuilder content: () -> Content) {
        if let panel {
            panel.makeKeyAndOrderFront(nil)
            return
        }

        let panel = NSPanel(
            contentRect: NSRect(x: 80, y: 120, width: 420, height: 700),
            styleMask: [.nonactivatingPanel, .titled, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )

        panel.titleVisibility = .hidden
        panel.titlebarAppearsTransparent = true
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isMovableByWindowBackground = true
        panel.hidesOnDeactivate = false
        panel.isOpaque = false
        panel.backgroundColor = .clear

        // Host SwiftUI
        panel.contentView = NSHostingView(rootView: content())

        self.panel = panel
        panel.orderFrontRegardless()
    }
}
