import Foundation
import Combine
import CoreBluetooth
import WatchConnectivity
import BridgeMessages

final class SensorBridge: NSObject, ObservableObject, CBCentralManagerDelegate, CBPeripheralDelegate, WCSessionDelegate {
    @Published var latest: HeartRateSample?
    @Published var status = "Warte auf BLE oder Watch. Watch-Workout direkt auf der Uhr starten."
    @Published var receiverURL = ""
    @Published var token = ""
    @Published var liveUpload = false
    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var sessionID = UUID()
    private var sequence = 0
    private var sourceSequences: [UUID: Int] = [:]

    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: .main)
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    func scan() {
        guard central.state == .poweredOn else { status = "Bluetooth nicht bereit oder nicht freigegeben"; return }
        status = "Suche Heart-Rate-Service (ersten Gurt nur im beaufsichtigten Spike verwenden)"
        central.scanForPeripherals(withServices: [CBUUID(string: "180D")])
        DispatchQueue.main.asyncAfter(deadline: .now() + 8) { [weak self] in
            self?.central.stopScan()
            if self?.peripheral == nil { self?.status = "Kein Pulsgurt gefunden" }
        }
    }

    func disconnect() {
        central.stopScan()
        if let device = peripheral { central.cancelPeripheralConnection(device) }
        peripheral = nil
        latest = nil
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        status = central.state == .poweredOn ? "Bluetooth bereit" : "Bluetooth nicht verfügbar"
        if central.state != .poweredOn { latest = nil }
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String: Any], rssi RSSI: NSNumber) {
        guard self.peripheral == nil else { return }
        self.peripheral = peripheral
        peripheral.delegate = self
        central.stopScan()
        central.connect(peripheral)
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        sessionID = UUID(); sequence = 0
        peripheral.discoverServices([CBUUID(string: "180D")])
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        self.peripheral = nil; latest = nil; status = "BLE-Verbindung fehlgeschlagen"
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        if self.peripheral === peripheral { self.peripheral = nil; latest = nil; status = "BLE getrennt" }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard error == nil else { status = "BLE-Servicefehler"; return }
        peripheral.services?.forEach { peripheral.discoverCharacteristics([CBUUID(string: "2A37")], for: $0) }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard error == nil else { status = "BLE-Charakteristikfehler"; return }
        service.characteristics?.filter { $0.uuid == CBUUID(string: "2A37") }.forEach { peripheral.setNotifyValue(true, for: $0) }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard self.peripheral === peripheral, error == nil, let data = characteristic.value,
              let bpm = HeartRateSample.parseBLE(data) else { return }
        sequence += 1
        accept(HeartRateSample(sessionID: sessionID, sequence: sequence, timestamp: Date(), source: "ble_heart_rate", bpm: bpm))
    }

    private func accept(_ sample: HeartRateSample) {
        guard sample.schemaVersion == 1, sample.isFresh(), sample.sequence > (sourceSequences[sample.sessionID] ?? -1) else { return }
        if sourceSequences.count > 32 { sourceSequences.removeAll() }
        sourceSequences[sample.sessionID] = sample.sequence
        latest = sample
        status = "Frischer Puls · \(sample.source)"
        if liveUpload { sendLatest() }
    }

    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        guard let data = message["sample"] as? Data, let sample = try? HeartRateSample.decode(data) else { return }
        DispatchQueue.main.async { self.accept(sample) }
    }
    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {}
    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) { session.activate() }

    func sendLatest() {
        guard let sample = latest, sample.isFresh(), let url = URL(string: receiverURL),
              url.scheme == "https", url.user == nil, url.password == nil, !token.isEmpty else {
            status = "Frischer Wert, HTTPS-Testadresse und Token erforderlich"; return
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? sample.encoded()
        request.timeoutInterval = 10
        URLSession.shared.dataTask(with: request) { _, response, error in
            DispatchQueue.main.async {
                let success = error == nil && (response as? HTTPURLResponse)?.statusCode == 202
                self.status = success ? "Testempfänger hat Wert angenommen" : "Versand fehlgeschlagen; kein späterer Live-Replay"
                if !success { self.liveUpload = false }
            }
        }.resume()
    }
}
