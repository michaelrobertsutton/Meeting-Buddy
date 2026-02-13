// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "AudioCapture",
    platforms: [
        .macOS("14.2")
    ],
    targets: [
        .executableTarget(
            name: "AudioCapture",
            dependencies: [],
            path: "Sources/AudioCapture"
        )
    ]
)
