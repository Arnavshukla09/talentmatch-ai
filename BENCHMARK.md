# TalentMatch AI — performance records and validation

The throughput measurements below are historical results from before the November 25, 2026 hardening and extension 1.2.1 update. They have not been rerun against the current source. Hardware, worker configuration, model cache state and exact source revision were not recorded, so these numbers are not reproducible capacity guarantees.

## Current validation — November 25, 2026

| Check | Result | Scope |
| --- | --- | --- |
| Python suite | 44 passed | Pipeline, API boundaries, PDF extraction, coaching contract; mock AI and cached embeddings |
| Simulated UI / extension | 5 passed | Safe report rendering, profile persistence/opt-out, theme persistence |
| Standalone native regressions | Passed | Skill punctuation and repeated keyword detection |
| Local native rebuild | Passed | MinGW shared library |
| Extension appearance | Inspected | Light/dark popup rendered in headless Chrome |
| Release package | Verified | Extension 1.2.1; all five packaged files matched source |

These are correctness checks. They do not measure accuracy against labeled hiring decisions, production throughput, native thread safety, or live external service behavior. See [the development guide](docs/DEVELOPMENT.md) for commands and limitations.

## Historical benchmark

### Recorded setup
- Executed via `run_detailed_benchmarks.py`
- Payload: Dynamically generated dummy PDF (`fpdf`) against a dummy Job Description.
- Inference flow: PDF Text Extraction -> Sentence-Transformer Embeddings -> C++ Engine Scoring (`talentmatch.dll`) -> JSON serialization.
- *Note: External AI summary calls (Groq) were bypassed to test pure backend engine performance without network jitter or exposing API keys.*

### Recorded results

#### 100 Requests (Client Concurrency = 10)
- **Total Time**: 2.74 seconds
- **Throughput**: ~36.5 requests / sec
- **Average Latency**: 265 ms
- **Median Latency**: 255 ms
- **p95 Latency**: 427 ms
- **p99 Latency**: 852 ms
- **Success Rate**: 100%

#### Stress test: client concurrency

| Concurrency | Total Requests | Total Time | Throughput | Avg Latency | p95 Latency | Success Rate |
|-------------|----------------|------------|------------|-------------|-------------|--------------|
| **10**      | 10             | 0.38s      | 26.4 req/s | 242 ms      | 377 ms      | 100%         |
| **25**      | 25             | 0.66s      | 37.6 req/s | 383 ms      | 642 ms      | 100%         |
| **50**      | 50             | 1.39s      | 35.9 req/s | 811 ms      | 1336 ms     | 100%         |
| **100**     | 100            | 2.91s      | 34.3 req/s | 1695 ms     | 2782 ms     | 100%         |

### Interpretation and limitations
- **Observed failure rate: 0% in the reported run.** This measures HTTP request success, not C++ thread safety. The async endpoint runs synchronous inference on the event loop, so client concurrency does not establish parallel engine execution. Direct concurrent engine tests are required before making thread-safety claims.
- **Historical results:** The numbers above have not been rerun for the current fixes and omit hardware and server configuration. They should not be treated as a production capacity guarantee.
- **Observed latency:** The reported median was 255 ms in the historical 100-request run. There is no controlled comparison here with the previous Python implementation.

## Repeating performance measurements

Install `requirements-dev.txt`, build the native engine, and start a local API process from the repository root. Explicitly remove `GROQ_API_KEY` from that server's environment to omit coaching, or use `MOCK_LLM=1` to substitute mock coaching. The benchmark client does not disable coaching in a separately running server.

Run `python run_detailed_benchmarks.py` against the default `http://localhost:8000/api/score`. The script creates `dummy.pdf` in the working directory; run in a directory where that name does not contain a file you need. It measures a single short synthetic resume and HTTP statuses, not the semantic correctness of each response. Its latency percentiles include successful responses and start after the client semaphore admits each request, excluding time waiting for that semaphore.

For a new report, record the source revision, OS/CPU/RAM, compiler flags, Python/native versions, worker count, model cache state, coaching mode, warm-up and cold-start runs, varied payload sizes, response correctness, error counts and latency distributions. Use direct native concurrency checks before asserting thread safety. No new performance numbers are claimed for this release.
