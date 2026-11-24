import SwiftUI

@main
struct BridgeApp: App {
    @StateObject private var bridge = SensorBridge()
    var body: some Scene {
        WindowGroup {
            Form {
                Section("Fitness-Cockpit Sensor-Spike") {
                    Text(bridge.status)
                    TimelineView(.periodic(from: .now, by: 1)) { context in
                        Text(bridge.latest.flatMap { $0.isFresh(at: context.date) ? "\(Int($0.bpm)) bpm · \($0.source)" : nil } ?? "Puls nicht verfügbar")
                    }
                    Button("BLE-Pulsgurt suchen") { bridge.scan() }
                    Button("BLE trennen") { bridge.disconnect() }
                }
                Section("Expliziter Versand an HTTPS-Testempfänger") {
                    TextField("https://testrechner:8443/pulse", text: $bridge.receiverURL)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                    SecureField("Temporäres Test-Token", text: $bridge.token)
                    Toggle("Live-Versand für diesen Test erlauben", isOn: $bridge.liveUpload)
                    Button("Aktuellen Wert einmal senden") { bridge.sendLatest() }
                    Text("Token und Zustimmung bleiben im Speicher. Der Testempfänger ist getrennt von der Produkt-API. Bei Versandfehler endet der Live-Versand.")
                        .font(.caption)
                }
            }
        }
    }
}
