// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MeetingBuddyShell",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "MeetingBuddyShell", targets: ["MeetingBuddyShell"])
    ],
    dependencies: [
    ],
    targets: [
        .executableTarget(
            name: "MeetingBuddyShell",
            dependencies: [],
            path: "Sources/MeetingBuddyShell"
        )
    ]
)
