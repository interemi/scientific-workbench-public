import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func safeURLSessionTransportDoesNotFollowHTTPRedirects() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Redirect-\(UUID().uuidString)", isDirectory: true)
    let portFile = root.appendingPathComponent("port.txt")
    let targetMarker = root.appendingPathComponent("redirect-target-reached.txt")
    let serverErrorLog = root.appendingPathComponent("server-stderr.txt")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    try Data().write(to: serverErrorLog)
    let errorHandle = try FileHandle(forWritingTo: serverErrorLog)
    defer { try? errorHandle.close() }

    let server = Process()
    server.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    server.arguments = [
      "-c",
      """
      import http.server, pathlib, sys
      port_file = pathlib.Path(sys.argv[1])
      marker = pathlib.Path(sys.argv[2])
      class Handler(http.server.BaseHTTPRequestHandler):
          def do_GET(self):
              if self.path == '/redirect':
                  self.send_response(302)
                  self.send_header('Location', '/target')
                  self.end_headers()
              else:
                  marker.write_text('redirect followed', encoding='utf-8')
                  self.send_response(200)
                  self.end_headers()
                  self.wfile.write(b'target')
          def log_message(self, format, *args):
              pass
      server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
      port_file.write_text(str(server.server_port), encoding='utf-8')
      server.serve_forever()
      """,
      portFile.path,
      targetMarker.path,
    ]
    server.standardOutput = FileHandle.nullDevice
    server.standardError = errorHandle
    try server.run()
    defer {
      if server.isRunning {
        server.terminate()
        server.waitUntilExit()
      }
    }

    let port = try await waitForRedirectTestPort(
      at: portFile,
      server: server,
      errorLog: serverErrorLog
    )
    var request = URLRequest(url: URL(string: "http://127.0.0.1:\(port)/redirect")!)
    request.timeoutInterval = 3
    let (_, response) = try await SafeURLSessionTransport.data(for: request)

    #expect((response as? HTTPURLResponse)?.statusCode == 302)
    #expect(!FileManager.default.fileExists(atPath: targetMarker.path))
  }

  private func waitForRedirectTestPort(
    at url: URL,
    server: Process,
    errorLog: URL
  ) async throws -> Int {
    let deadline = Date().addingTimeInterval(15)
    while Date() < deadline {
      if let text = try? String(contentsOf: url, encoding: .utf8),
         let port = Int(text.trimmingCharacters(in: .whitespacesAndNewlines)),
         port > 0 {
        return port
      }
      if !server.isRunning {
        throw RedirectTransportTestError.serverDidNotStart(
          "Python exited with status \(server.terminationStatus): \(serverError(at: errorLog))"
        )
      }
      try await Task.sleep(nanoseconds: 50_000_000)
    }
    throw RedirectTransportTestError.serverDidNotStart(
      "Python did not report a port within 15 seconds: \(serverError(at: errorLog))"
    )
  }

  private func serverError(at url: URL) -> String {
    let message = (try? String(contentsOf: url, encoding: .utf8))?
      .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return message.isEmpty ? "no stderr output" : String(message.prefix(500))
  }
}

private enum RedirectTransportTestError: Error {
  case serverDidNotStart(String)
}
