import XCTest
@testable import BridgeMessages

final class HeartRateSampleTests: XCTestCase {
    func testEightAndSixteenBitBLEAndMalformedPackets() {
        XCTAssertEqual(HeartRateSample.parseBLE(Data([0, 98])), 98)
        XCTAssertEqual(HeartRateSample.parseBLE(Data([1, 44, 1])), 300)
        XCTAssertNil(HeartRateSample.parseBLE(Data([1, 44])))
        XCTAssertNil(HeartRateSample.parseBLE(Data()))
    }

    func testExpiryAndWireRoundtrip() throws {
        let date = Date(timeIntervalSince1970: 1_700_000_000)
        let sample = HeartRateSample(sessionID: UUID(), sequence: 2, timestamp: date, source: "apple_watch", bpm: 100)
        XCTAssertEqual(try HeartRateSample.decode(sample.encoded()), sample)
        XCTAssertTrue(sample.isFresh(at: date.addingTimeInterval(9)))
        XCTAssertFalse(sample.isFresh(at: date.addingTimeInterval(11)))
        XCTAssertFalse(sample.isFresh(at: date.addingTimeInterval(-3)))
    }
}
