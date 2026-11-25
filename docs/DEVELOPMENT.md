# Development, validation and releases

Run commands from the repository root. Python 3.10+, CMake 3.18+, a C++17 toolchain, and Git are required for the application. Use a Python build with compatible torch/sentence-transformers dependencies. UI checks require Node.js 22.13+.

## Setup

Build the engine with `./scripts/build_engine.sh` on Linux/macOS or `.\scripts\build_engine.ps1` in Windows PowerShell. Use a fresh build directory if an existing CMake cache belongs to another generator or machine. Set `TALENTMATCH_LIB_PATH` for an alternate native output path.

Install runtime dependencies with `pip install -r requirements.txt`, or runtime plus test/benchmark dependencies with `pip install -r requirements-dev.txt`. Start `uvicorn api:app --host 127.0.0.1 --port 8000` to serve both API and website.

Docker currently builds C++ with XGBoost disabled, downloads MiniLM at image build time, copies the raw frontend, and starts FastAPI on `${PORT:-8000}`. Use the Docker run command in the [README](../README.md); the legacy Compose file still requires correction of its port and `.env` handling. This release was validated locally on Windows, not by building a fresh Linux Docker image.

## Python checks

```bash
python -m pytest tests/test_api_security.py tests/test_coaching.py -q
```

The API checks replace scoring with a local stub. Coaching checks mock model output. Neither invokes the external coaching service.

Full suite with a previously cached MiniLM model:

```bash
MOCK_LLM=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest tests/ -q
```

```powershell
$env:MOCK_LLM = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
python -m pytest tests/ -q
```

These variables apply to the current shell. Remove them after testing if you want normal coaching and model download behavior. Offline flags require an already cached embedding model. Full pipeline tests require the built native library; only `TestCppBridge` skips when it is missing.

Coverage includes static traversal and public route behavior, generated upload paths and cleanup, invalid/oversized inputs, safe internal errors, health status, coaching schema failures, opt-in resume text, PDF extraction, and the pipeline response contract.

## Interface and extension checks

```bash
npm install --prefix tests
npm test --prefix tests
```

The jsdom checks simulate the website and extension. They cover escaped malicious API text, PDF profile saving, reopening and clearing a profile, remembering opt-out, and theme persistence. They do not simulate the real browser permission model, job-board DOMs, Google Docs authentication, or store installation.

The website's main files live directly under `frontend/`. Its `src/` starter files are not the current UI. The extension has its own CSS with matching theme tokens and an external `theme.js` initializer. Confirm both light and dark forms and result states after styling changes.

## Native regressions

```bash
g++ -std=c++17 tests/native_regressions.cpp cpp_core/skills/trie.cpp cpp_core/features/education.cpp -o native_regressions
./native_regressions
```

In PowerShell run `.\native_regressions.exe`. The standalone check verifies punctuation around skills, single-letter exclusions such as `R&D`, and repeated keyword detection without penalizing a short diverse skill list. It is not a native thread-safety or model-quality benchmark. Rebuild the actual shared library after native changes; the application does not use this test executable.

## Recorded validation — November 25, 2026

| Check | Recorded result |
| --- | --- |
| Python pipeline, API security and coaching | 44 passed; cached embeddings and mock coaching |
| Website and extension simulation | 5 passed, including saved theme |
| Standalone C++ regressions | Passed |
| Native shared library | Rebuilt successfully with local MinGW |
| Light/dark popup layout | Rendered and visually inspected in headless Chrome |
| Release ZIP | Version 1.2.1, each packaged file matched extension source |
| Diff whitespace check | Passed |

Existing FastAPI startup and test-client deprecation warnings remain. Those warnings do not establish test failure. Live Groq output, Linux image building, Render rollout, real Chrome/Edge installation and job-board extraction were not validated by this run.

## Release workflow

1. Run checks relevant to the changed code. For native changes, rebuild the shared library before pipeline checks.
2. Update the extension manifest version when applicable, update the changelog, and rebuild with `python scripts/package_extension.py`.
3. Confirm the ZIP contains the five public extension files and matches source. Load it unpacked and check permissions and behavior in a real browser before store submission.
4. Review the Git diff and commit source, tests, documentation and the intended distributable. Exclude `.env`, resumes/uploads, local dependencies, temporary artwork, alternate ZIPs and generated native build files.
5. Push to the intended repository branch. A push may trigger configured hosting automation, but does not prove a deployment succeeded.
6. Verify Render logs/readiness and a successful analysis separately. Publish the extension through its store dashboard as a separate action.

## Remaining work

- A side panel or background task so closing the popup does not lose the visible request/report.
- Multiple resume profiles and an editable preview of saved text.
- Explicit extraction status and job-description review for supported sites.
- Six-category score visualization and rewrite suggestions in the extension.
- Report transfer/export, history, and consistent shared interface components.
- Per-user opt-out for external coaching, accessibility announcements and fuller keyboard navigation.
- Rate limiting, request/body limits before multipart parsing, a work queue, and deployment smoke checks.
- Fresh load tests with documented hardware and direct concurrent native tests before making capacity/thread-safety claims.
