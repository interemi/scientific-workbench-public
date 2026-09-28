import Foundation
import Vision

struct OCRResult: Codable {
    let image: String
    let text: String
}

var results: [OCRResult] = []

for argument in CommandLine.arguments.dropFirst() {
    let url = URL(fileURLWithPath: argument)
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["es-ES", "en-US"]

    let handler = VNImageRequestHandler(url: url, options: [:])
    do {
        try handler.perform([request])
        let observations = request.results ?? []
        let text = observations.compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
        results.append(OCRResult(image: url.lastPathComponent, text: text))
    } catch {
        results.append(OCRResult(image: url.lastPathComponent, text: ""))
    }
}

let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted]
let data = try encoder.encode(results)
if let json = String(data: data, encoding: .utf8) {
    print(json)
}
