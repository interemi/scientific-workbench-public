struct HistoryPage {
  static let pagingThreshold = 250
  static let pageSize = 100

  let total: Int
  let index: Int
  let pageCount: Int
  let range: Range<Int>

  init(total: Int, index: Int) {
    self.total = total
    pageCount = total > Self.pagingThreshold ? (total + Self.pageSize - 1) / Self.pageSize : 1
    self.index = min(max(index, 0), pageCount - 1)
    let start = self.index * Self.pageSize
    range = start..<(pageCount == 1 ? total : min(start + Self.pageSize, total))
  }

  static func containing(_ offset: Int?, total: Int) -> Int {
    guard total > pagingThreshold, let offset else { return 0 }
    return offset / pageSize
  }
}
