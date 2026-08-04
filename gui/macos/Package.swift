// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "Copyist",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "Copyist",
            path: "Sources/Copyist"
        ),
        // Inspects a running Copyist the way a screen reader does. Separate
        // because SwiftUI's tree is only visible to an accessibility CLIENT,
        // not to the app itself — see Sources/axaudit/main.swift.
        .executableTarget(
            name: "axaudit",
            path: "Sources/axaudit"
        )
    ]
)
