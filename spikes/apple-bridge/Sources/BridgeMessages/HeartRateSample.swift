import Foundation

public struct HeartRateSample: Codable, Equatable {
    public let schemaVersion: Int
    public let sessionID: UUID
    public let sequence: Int
    public let timestamp: Date
    public let source: String
    public let bpm: Double

    public init(sessionID: UUID, sequence: Int, timestamp: Date, source: String, bpm: Double) {
        self.schemaVersion = 1
        self.sessionID = sessionID
        self.sequence = sequence
        self.timestamp = timestamp
        self.source = source
        self.bpm = bpm
    }

    public func isFresh(at now: Date = Date()) -> Bool {
        bpm.isFinite && (20...250).contains(bpm) && sequence >= 0 &&
        now.timeIntervalSince(timestamp) >= -2 && now.timeIntervalSince(timestamp) <= 10
    }

    public static func decode(_ data: Data) throws -> Self {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(Self.self, from: data)
    }

    public func encoded() throws -> Data {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return try encoder.encode(self)
    }

    public static func parseBLE(_ bytes: Data) -> Double? {
        let data = Array(bytes)
        guard data.count >= 2 else { return nil }
        if data[0] & 1 == 1 {
            guard data.count >= 3 else { return nil }
            return Double(UInt16(data[1]) | UInt16(data[2]) << 8)
        }
        return Double(data[1])
    }
}
