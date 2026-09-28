#!/usr/bin/env swift

import Foundation
import PDFKit

struct PDFTextRecord: Codable {
    let path: String
    let text: String?
    let error: String?
}

var records: [PDFTextRecord] = []

for path in CommandLine.arguments.dropFirst() {
    let url = URL(fileURLWithPath: path)
    guard let document = PDFDocument(url: url) else {
        records.append(PDFTextRecord(path: path, text: nil, error: "PDFKit could not open the document"))
        continue
    }
    guard let text = document.string, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
        records.append(PDFTextRecord(path: path, text: nil, error: "PDF contains no extractable text"))
        continue
    }
    records.append(PDFTextRecord(path: path, text: text, error: nil))
}

let encoder = JSONEncoder()
encoder.outputFormatting = [.sortedKeys]
let payload = try encoder.encode(records)
FileHandle.standardOutput.write(payload)
FileHandle.standardOutput.write(Data("\n".utf8))
