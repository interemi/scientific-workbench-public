import SwiftUI

struct JobEvidenceStagesView: View {
  let job: JobRecord
  var compact = false
  @State private var assessment: JobEvidenceAssessment?

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("Evidence stages")
        .font(.headline)
      if let assessment {
        ForEach(assessment.stages, id: \.title) { stage in
          VStack(alignment: .leading, spacing: 3) {
            HStack {
              Text(stage.title)
                .font(compact ? .caption : .subheadline)
              Spacer()
              StatusBadge(status: stage.level.rawValue)
            }
            .help(stage.detail)
            if !compact {
              Text(stage.detail)
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
            }
          }
        }
      } else {
        ProgressView("Checking retained evidence...")
      }
      Text("A passing process or tool status is not scientific approval.")
        .font(.caption)
        .foregroundStyle(.secondary)
    }
    .padding(12)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    .task(id: job) {
      assessment = nil
      let result = await Task.detached(priority: .utility) {
        JobEvidenceAssessmentService().assess(job: job)
      }.value
      if !Task.isCancelled {
        assessment = result
      }
    }
  }
}
