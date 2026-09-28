import Foundation

enum SafeURLSessionTransport {
  static func data(for request: URLRequest) async throws -> (Data, URLResponse) {
    let session = URLSession(
      configuration: .ephemeral,
      delegate: RedirectRejectingSessionDelegate(),
      delegateQueue: nil
    )
    defer { session.invalidateAndCancel() }
    return try await session.data(for: request)
  }
}

private final class RedirectRejectingSessionDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
  func urlSession(
    _ session: URLSession,
    task: URLSessionTask,
    willPerformHTTPRedirection response: HTTPURLResponse,
    newRequest request: URLRequest,
    completionHandler: @escaping (URLRequest?) -> Void
  ) {
    completionHandler(nil)
  }
}
