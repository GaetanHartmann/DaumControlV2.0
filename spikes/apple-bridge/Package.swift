// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "BridgeMessages",
    platforms: [.iOS(.v17), .watchOS(.v10), .macOS(.v13)],
    products: [.library(name: "BridgeMessages", targets: ["BridgeMessages"])],
    targets: [.target(name: "BridgeMessages"), .testTarget(name: "BridgeMessagesTests", dependencies: ["BridgeMessages"])]
)
