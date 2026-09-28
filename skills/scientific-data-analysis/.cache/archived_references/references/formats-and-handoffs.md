# Formats And Handoffs

Compact mother-skill routing note. Full document/reporting guidance lives in `scientific-data-documents/references/formats-and-handoffs.md`; load that child skill for detailed document, presentation, office, iWork, PDF, and archive handling.

Required routing reminders:

- DOCX marked-run workflows: `docx-style-inventory` and `docx-styled-replace` operate on copies and verify readback.
- PDF rendering fallback: prefer Poppler/`pdftoppm`; when absent on macOS, report the fallback and use `qlmanage`, `quicklook_bridge.py`, or PyMuPDF only for the needed pages.
- Keep originals read-only; create copied workdirs or explicit edited outputs.
- For mixed packages, route first through `inspect_data_container.py` or `document_intake_workbench.py`, then choose a narrower capability.

Archive note: the full historical mother copy was moved to `tmp/v2_5_efficiency_goal/archived_mother_references/` during v2.5 budget hardening.
