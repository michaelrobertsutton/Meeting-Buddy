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
    dependencies: [
        .package(path: "../MeetingBuddyProtocol")
    ],
    targets: [
        .executableTarget(
            name: "MeetingBuddySettings",
            dependencies: [
                .product(name: "MeetingBuddyProtocol", package: "MeetingBuddyProtocol")
            ],
            path: "Sources/MeetingBuddySettings"
        )
    ]
)
