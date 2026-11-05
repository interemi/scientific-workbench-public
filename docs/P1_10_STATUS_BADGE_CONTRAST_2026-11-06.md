# P1.10 status badge contrast review

Status badges use the system's primary text color over the existing tinted
background. A status remains readable as a word, with color as an additional
cue. The change is in `467bf060fe3b04d960944740502dee94e38d48a9`.

## Color measurements

The November 4 review resolved SwiftUI colors on macOS 27.0.1 with light and
dark color schemes. The cases combine five status colors, three opaque system
surfaces, and two appearances. The surfaces use the system window, control,
and text background colors. Each calculation composites the existing 14%
tint over its surface and the resolved text color over that tint.

The comparison evaluates source-over compositing in both linear sRGB and
encoded sRGB. For each final color pair, it computes relative luminance in
linear sRGB and applies the contrast formula `(Lighter + 0.05) / (Darker + 0.05)`.
The review uses 4.5:1 as the reference for the caption text. [W3C contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)

| Appearance | Prior text color ratio | Primary text color ratio |
| --- | ---: | ---: |
| Light | 1.896–3.829 | 5.056–13.680 |
| Dark | 3.154–6.338 | 6.559–10.661 |

Before the change, 21 of 30 cases fell below 4.5:1 in both models. After the
change, all 30 reached 4.5:1 in both models. These ranges describe the sampled
opaque surfaces. The Dashboard check below covers the rendered badge over
the app's material background.

## App verification

On November 6, the isolated app showed the existing synthetic table job's
`SUCCEEDED` badge with dark text in light appearance and light text in dark
appearance. Both screenshots retained the green tint, and the accompanying
accessibility trees contained the same status text. The test restored the
original Dark appearance and preserved the isolated job files and preferences.

The full local quality gate passed all 16 steps, including 380 Swift tests
and packaged UI checks. The gate preserved all 22 normal application-state
files byte for byte and the saved preference values. It used Swift 6.4 with
the installed macOS 26.5 SDK and the SwiftPM native build system. The local
app, capture hashes, palette inputs, and gate logs are retained privately.

## Remaining accessibility review

The November 4 session temporarily enabled VoiceOver and inspected Dashboard
focus. Two attempts to observe the caption process timed out. The original
VoiceOver and appearance settings were restored. Spoken announcements and
contrast coverage beyond these badges remain open. [Issue #22](https://github.com/interemi/scientific-workbench-public/issues/22)
