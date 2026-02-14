import AppKit
import Carbon.HIToolbox

/// Registers a global hotkey (Alt+Space) to toggle the HUD
final class GlobalHotkey {
    private var eventMonitor: Any?
    private let action: () -> Void

    init(action: @escaping () -> Void) {
        self.action = action
    }

    func register() {
        // Monitor for Alt+Space globally
        eventMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            // Check for Alt (Option) + Space
            // Space keyCode = 49
            if event.keyCode == 49 && event.modifierFlags.contains(.option) {
                self?.action()
            }
        }
    }

    func unregister() {
        if let monitor = eventMonitor {
            NSEvent.removeMonitor(monitor)
            eventMonitor = nil
        }
    }

    deinit {
        unregister()
    }
}
