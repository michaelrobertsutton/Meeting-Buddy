import AppKit
import SwiftUI

// Set activation policy before NSApplicationMain starts so the dock icon
// is never shown.
NSApplication.shared.setActivationPolicy(.accessory)

MeetingBuddySettingsApp.main()
