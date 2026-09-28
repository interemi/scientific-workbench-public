import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func jsonOutputExtractorFindsTypedObjectAfterTruncationMarker() throws {
    let text = """
    {"status":"stale"}
    {"unterminated":"prefix

    [Scientific Workbench truncated 9000 output bytes; showing the beginning and end.]

    tail fragment from a noisy process
    {"status":"PASS","selected_python":"/safe/python"}
    """

    let payload = try #require(
      JSONOutputExtractor.decodeLast(JSONExtractorFixture.self, from: text)
    )
    #expect(payload.status == "PASS")
    #expect(payload.selectedPython == "/safe/python")
  }

  @Test
  func jsonOutputExtractorSelectsLastMatchingOuterObject() throws {
    let text = """
    log {"diagnostic":true}
    {"tool":"first","status":"WARNING"}
    unmatched prefix {
    {"tool":"final","status":"OK","nested":{"status":"inner"}}
    """

    let payload = try #require(
      JSONOutputExtractor.lastObject(
        in: text,
        matching: { $0["tool"] as? String == "final" }
      )
    )
    #expect(payload["status"] as? String == "OK")
  }
}

private struct JSONExtractorFixture: Decodable {
  let status: String
  let selectedPython: String

  enum CodingKeys: String, CodingKey {
    case status
    case selectedPython = "selected_python"
  }
}
