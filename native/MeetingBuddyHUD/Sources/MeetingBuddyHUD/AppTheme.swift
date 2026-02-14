import SwiftUI

/// Design tokens for Meeting Buddy HUD
enum AppTheme {
    // MARK: - Colors
    static let accentBlue = Color(hex: "#60B6F2")
    static let textPrimary = Color.white
    static let textSecondary = Color.white.opacity(0.70)
    static let glassEdge = Color.white.opacity(0.10)

    // MARK: - Spacing
    static let spacing: CGFloat = 8
    static let margin: CGFloat = 16
    static let cornerRadius: CGFloat = 12

    // MARK: - Window
    static let windowWidth: CGFloat = 420
    static let windowHeight: CGFloat = 700
}

// MARK: - Color hex initializer
extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r, g, b: UInt64
        switch hex.count {
        case 6:
            (r, g, b) = ((int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        default:
            (r, g, b) = (0, 0, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: 1
        )
    }
}
