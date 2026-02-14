// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MeetingBuddyProtocol",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .library(name: "MeetingBuddyProtocol", targets: ["MeetingBuddyProtocol"])
    ],
    targets: [
        .target(
            name: "MeetingBuddyProtocol",
            dependencies: [],
            path: "Sources/MeetingBuddyProtocol"
        )
    ]
)
