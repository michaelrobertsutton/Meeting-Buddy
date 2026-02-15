import AppKit
import SwiftUI

// Set activation policy before NSApplicationMain starts so the dock icon
// is never shown — doing it in App.init() or applicationDidFinishLaunching
// is too late when using WindowGroup (SwiftUI resets it back to .regular).
NSApplication.shared.setActivationPolicy(.accessory)

MeetingBuddySettingsApp.main()
