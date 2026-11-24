import Foundation
import Combine
import HealthKit
import WatchConnectivity
import BridgeMessages

final class WorkoutBridge: NSObject, ObservableObject, HKWorkoutSessionDelegate, HKLiveWorkoutBuilderDelegate, WCSessionDelegate {
    @Published var status = "Noch kein Workout"
    @Published var active = false
    private let health = HKHealthStore()
    private var workout: HKWorkoutSession?
    private var builder: HKLiveWorkoutBuilder?
    private var sessionID = UUID()
    private var sequence = 0

    override init() {
        super.init()
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    func start() {
        guard !active, HKHealthStore.isHealthDataAvailable(), let hr = HKQuantityType.quantityType(forIdentifier: .heartRate) else { return }
        health.requestAuthorization(toShare: [HKObjectType.workoutType()], read: [hr]) { success, error in
            DispatchQueue.main.async {
                guard success, error == nil else { self.status = "HealthKit nicht freigegeben"; return }
                self.begin()
            }
        }
    }

    private func begin() {
        guard !active else { return }
        let configuration = HKWorkoutConfiguration()
        configuration.activityType = .cycling
        configuration.locationType = .indoor
        do {
            let session = try HKWorkoutSession(healthStore: health, configuration: configuration)
            let liveBuilder = session.associatedWorkoutBuilder()
            liveBuilder.dataSource = HKLiveWorkoutDataSource(healthStore: health, workoutConfiguration: configuration)
            session.delegate = self
            liveBuilder.delegate = self
            workout = session; builder = liveBuilder
            sessionID = UUID(); sequence = 0
            active = true; status = "Workout aktiv; warte auf Puls"
            let start = Date()
            session.startActivity(with: start)
            liveBuilder.beginCollection(withStart: start) { success, error in
                if !success || error != nil { DispatchQueue.main.async { self.stop(); self.status = "Workout-Erfassung fehlgeschlagen" } }
            }
        } catch { status = "Workout konnte nicht starten" }
    }

    func stop() {
        workout?.end()
        // This measurement spike intentionally does not save a duplicate workout.
        builder?.discardWorkout()
        builder = nil; workout = nil; active = false
        status = "Beendet; Workout verworfen"
    }

    func workoutBuilder(_ workoutBuilder: HKLiveWorkoutBuilder, didCollectDataOf collectedTypes: Set<HKSampleType>) {
        guard let hr = HKQuantityType.quantityType(forIdentifier: .heartRate), collectedTypes.contains(hr),
              let stats = workoutBuilder.statistics(for: hr), let quantity = stats.mostRecentQuantity(),
              let interval = stats.mostRecentQuantityDateInterval() else { return }
        let bpm = quantity.doubleValue(for: HKUnit.count().unitDivided(by: .minute()))
        DispatchQueue.main.async {
            guard self.active else { return }
            self.sequence += 1
            let sample = HeartRateSample(sessionID: self.sessionID, sequence: self.sequence, timestamp: interval.end, source: "apple_watch", bpm: bpm)
            guard sample.isFresh() else { self.status = "Kein frischer Puls"; return }
            guard WCSession.default.isReachable, let data = try? sample.encoded() else { self.status = "iPhone nicht erreichbar; Wert verworfen"; return }
            WCSession.default.sendMessage(["sample": data], replyHandler: nil) { _ in
                DispatchQueue.main.async { self.status = "Übertragung unterbrochen" }
            }
            self.status = "\(Int(bpm)) bpm → iPhone"
        }
    }

    func workoutBuilderDidCollectEvent(_ workoutBuilder: HKLiveWorkoutBuilder) {}
    func workoutSession(_ workoutSession: HKWorkoutSession, didChangeTo toState: HKWorkoutSessionState, from fromState: HKWorkoutSessionState, date: Date) {
        if toState == .ended { DispatchQueue.main.async { self.active = false } }
    }
    func workoutSession(_ workoutSession: HKWorkoutSession, didFailWithError error: Error) {
        DispatchQueue.main.async { self.stop(); self.status = "Workout abgebrochen" }
    }
    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {}
}
