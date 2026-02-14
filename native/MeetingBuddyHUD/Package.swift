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
    dependencies: [
        .package(path: "../MeetingBuddyProtocol")
    ],
    targets: [
        .executableTarget(
            name: "MeetingBuddyHUD",
            dependencies: [
                .product(name: "MeetingBuddyProtocol", package: "MeetingBuddyProtocol")
            ],
            path: "Sources/MeetingBuddyHUD"
        )
    ]
)
