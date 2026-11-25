# Changelog

## Extension 1.2.1 and backend v2 hardening — November 25, 2026

### Extension and interface

- Matched the website's cream/maroon light mode and charcoal/terracotta dark mode in the extension.
- Added the sun/moon toggle, persistent theme choice, keyboard focus styles and reduced-motion styling.
- Packaged the external Manifest V3-compatible `theme.js` initializer with version 1.2.1.
- Restored PDF-derived profile saving using opt-in `extracted_resume_text` from the API.
- Restricted extension host access to the scoring service and escaped untrusted report text.
- Added 120-second client request timeouts and improved non-JSON error handling.
- Renamed the website action to “Visit TalentMatch Website” because it opens the homepage without transferring a report.

### API and scoring

- Contained static serving to the public frontend root and allowlisted raw site assets.
- Replaced client-supplied upload paths with generated temporary PDF filenames.
- Enforced PDF, job-description and resume-text limits; rejected blank or unreadable resumes.
- Preserved HTTP validation status codes, hid internal analysis errors and returned 503 for unavailable native health checks.
- Returned coaching summaries and suggestions, with no-store response headers.
- Added bounded Groq requests, validated coaching fields/priorities and allowed mock coaching without a key.
- Fixed skill matching around punctuation while retaining single-letter exclusions.
- Replaced distinct-skill density with repeated-mention checks for keyword stuffing.

### Documentation and validation

- Added API, extension, development and release guides and corrected the README contribution descriptions.
- Corrected optional-coaching, native extraction, model-training, frontend serving and test prerequisite documentation.
- Marked historical performance numbers as pre-change observations rather than thread-safety or production-capacity evidence.
- Added API security, coaching, simulated interface and standalone native regression checks.
- Recorded 44 passing Python tests, five passing interface checks, native regression success, and rendered light/dark popup verification.

This describes repository source and the generated ZIP. It does not certify browser-store publication or a completed production rollout.
