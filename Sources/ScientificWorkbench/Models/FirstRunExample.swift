import Foundation

enum FirstRunExampleKind: String, CaseIterable, Identifiable {
  case table
  case fits
  case spectrum
  case document
  case mixed

  var id: String { rawValue }

  var title: String {
    switch self {
    case .table: return "Small table"
    case .fits: return "FITS image"
    case .spectrum: return "Synthetic spectrum"
    case .document: return "One-page PDF"
    case .mixed: return "Mixed research folder"
    }
  }

  var detail: String {
    switch self {
    case .table: return "Three operational rows; inspect columns and missing values."
    case .fits: return "An 8 × 8 image with a known WCS and one missing pixel."
    case .spectrum: return "Five wavelength and relative-flux samples."
    case .document: return "A readable, one-page synthetic observing note."
    case .mixed: return "A table, observing note, and PDF in one folder."
    }
  }

  var expectedResult: String {
    switch self {
    case .table:
      return "Table profile: 3 rows, 4 columns; no units or scientific inference."
    case .fits:
      return "FITS summary: one 8 × 8 image, 63 finite pixels, reference sky position 150°, −30°. Preview is not yet part of the guided run."
    case .spectrum:
      return "Table profile: 5 rows with wavelength in nm and relative flux; no line fit or radial velocity."
    case .document:
      return "Document intake: one readable PDF page; extracted text still needs review."
    case .mixed:
      return "Document intake inventories the note and PDF; a separate cross-domain run profiles the table. No combined scientific conclusion is produced."
    }
  }

  var capabilityID: String {
    switch self {
    case .table, .spectrum: return "profile_table"
    case .fits: return "inspect_fits"
    case .document, .mixed: return "document_intake_workbench"
    }
  }

  var catalogMode: CapabilityCatalogMode {
    self == .fits ? .expert : .normal
  }
}

struct PreparedFirstRunExample {
  let kind: FirstRunExampleKind
  let directory: URL
  let inputPaths: [String]
}
