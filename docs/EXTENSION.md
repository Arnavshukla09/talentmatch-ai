# Chrome / Edge extension

Current package version: **1.2.1**. Backend architecture: v2.

## Install or reload

1. Extract `talentmatch-extension.zip`, or use the repository's `extension/` folder.
2. Open `edge://extensions` or `chrome://extensions` and enable Developer mode.
3. Choose Load unpacked and select the folder containing `manifest.json`.
4. After source changes, click Reload for the extension and reopen the popup.

The source package is not automatically published to either browser store.

## Score a resume

Open a job page, then open the extension. It attempts to extract job text from known page containers and falls back to body text. Review and edit the job description before scoring. “Extract Again” requests a fresh extraction; protected browser pages and some dynamic sites do not allow extraction.

Upload a text-based PDF up to 2 MiB, or use a saved text profile. “Remember this resume” is selected by default. When selected for a PDF, the extension asks the API to return extracted resume text and stores that text locally after a successful analysis. When deselected, it does not request or store the extracted text.

“Save Page as Resume” extracts the active page into a local text profile. Google Docs extraction attempts the document text-export endpoint and then falls back to page text; access, authentication, and document rendering can affect the result. Check that the source page contains your resume before saving it.

A saved profile hides PDF upload controls. “Clear” deletes the saved profile and restores PDF upload. “Update Profile” saves text from the current page; it is not an editor or a multi-profile manager.

Requests go to `https://talentmatch-ai-jwqd.onrender.com/api/score`. The client stops waiting after 120 seconds. A free Render instance may need time to start. Retry after a timeout; a client timeout does not guarantee server processing stopped.

## Matching themes

| Mode | Background | Card | Accent |
| --- | --- | --- | --- |
| Light | Cream `#FCFAF5` | Translucent white | Maroon `#800020` |
| Dark | Charcoal `#181614` | Warm dark `#211E1B` | Terracotta `#C1622D` |

Use the sun/moon button to switch. The popup uses system preference when there is no saved choice. It caches the preference in extension-origin `localStorage` for startup and persists it in `chrome.storage.local`. The preference survives reopening the popup. Website and extension preferences are separate.

`theme.js` is an external script to comply with Manifest V3's restrictions on inline JavaScript. Styles include visible keyboard focus and reduced-motion handling. Font rendering uses Outfit when available, with Segoe UI and sans-serif fallbacks.

## Permissions and data

| Permission | Purpose |
| --- | --- |
| `activeTab` | Temporary access to the page the user activates the extension on |
| `scripting` | Extract text for a job description or saved resume |
| `storage` | Keep the resume text profile and theme preference locally |
| TalentMatch API host | Send scoring requests to the configured Render service |

The manifest does not request host access to every website. Saved text can contain personal information and remains on the device until cleared or the extension is uninstalled. When scoring is requested, the resume and job description are sent to the API. Optional server-configured coaching can then send excerpts to Groq. See the [privacy policy](../frontend/privacy.html).

## Results and current limitations

The popup shows overall and semantic scores, matched/missing skills, strengths, areas for improvement, ATS warnings, and an AI summary when available. The API returns rewrite suggestions, but the popup does not yet render those suggestions. Candidate highlight markup remains hidden because the API does not return `parsed_resume`.

“Visit TalentMatch Website” opens the homepage; it does not transfer the current report. Closing the popup does not preserve an in-progress request or the displayed report. There is no side panel, report export, history, or multi-profile selection yet.

## Package a release

From the repository root:

```bash
python scripts/package_extension.py
```

The script packages exactly these files at the ZIP root:

- `manifest.json`
- `popup.html`
- `popup.js`
- `theme.js`
- `style.css`

Local artwork, screenshots, dependencies, credentials, and temporary files are excluded. Bump `extension/manifest.json` before a new store submission, regenerate the ZIP, reload it locally, and separately submit through the store dashboard.
