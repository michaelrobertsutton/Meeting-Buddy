// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MeetingBuddyHUD",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "MeetingBuddyHUD", targets: ["MeetingBuddyHUD"])
    ],
    targets: [
        .executableTarget(
            name: "MeetingBuddyHUD",
            dependencies: [],
            path: "Sources/MeetingBuddyHUD"
        )
    ]
)
