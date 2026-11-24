import SwiftUI

@main
struct BridgeWatchApp: App {
    @StateObject private var workout = WorkoutBridge()
    var body: some Scene {
        WindowGroup {
            VStack {
                Text("Fitness-Cockpit")
                Text(workout.status).font(.caption)
                Button("Workout starten") { workout.start() }.disabled(workout.active)
                Button("Beenden / verwerfen") { workout.stop() }.disabled(!workout.active)
            }.padding()
        }
    }
}
