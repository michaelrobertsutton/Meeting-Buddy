// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MeetingBuddySettings",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "MeetingBuddySettings", targets: ["MeetingBuddySettings"])
    ],
    targets: [
        .executableTarget(
            name: "MeetingBuddySettings",
            path: "Sources/MeetingBuddySettings"
        )
    ]
)
