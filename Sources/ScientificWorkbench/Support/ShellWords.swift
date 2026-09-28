import Foundation

enum ShellWords {
  static func split(_ input: String) throws -> [String] {
    var words: [String] = []
    var current = ""
    var quote: Character?
    var escaping = false
    var preservingDoubleQuotedBackslash = false

    for character in input {
      if escaping {
        if preservingDoubleQuotedBackslash,
           character != "\\",
           character != "\"",
           character != "$",
           character != "`" {
          current.append("\\")
        }
        current.append(character)
        escaping = false
        preservingDoubleQuotedBackslash = false
        continue
      }

      if let activeQuote = quote {
        if character == activeQuote {
          quote = nil
        } else if activeQuote == "\"", character == "\\" {
          escaping = true
          preservingDoubleQuotedBackslash = true
        } else {
          current.append(character)
        }
        continue
      }

      if character == "\\" {
        escaping = true
        continue
      }

      if character == "'" || character == "\"" {
        quote = character
        continue
      }

      if character.isWhitespace {
        if !current.isEmpty {
          words.append(current)
          current = ""
        }
        continue
      }

      current.append(character)
    }

    if escaping {
      current.append("\\")
    }

    if quote != nil {
      throw ShellWordsError.unterminatedQuote
    }

    if !current.isEmpty {
      words.append(current)
    }

    return words
  }

  static func quote(_ word: String) -> String {
    guard !word.isEmpty else { return "''" }
    let safeCharacters = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "/._-:=+"))
    if word.unicodeScalars.allSatisfy({ safeCharacters.contains($0) }) {
      return word
    }
    return "'" + word.replacingOccurrences(of: "'", with: "'\\''") + "'"
  }
}

enum ShellWordsError: LocalizedError {
  case unterminatedQuote

  var errorDescription: String? {
    "The raw arguments contain an unterminated quote."
  }
}
