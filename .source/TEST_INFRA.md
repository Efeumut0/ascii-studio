# E2E test infrastructure: Video-to-ASCII System

Tests use Python `unittest` and SDL dummy video/audio drivers. They check decoding, audio extraction, rendering, playback state, exports, and invalid inputs without opening application windows.

## Running tests

From `.source/`, generate the synthetic inputs before the first test run:

`python tools/make_test_media.py`

Then run all discoverable tests:

`python -m unittest discover -s tests -q`

For a report grouped by tier, run `python tests/run_all_tests.py`. This runner includes Graphite, tiers 1–7, and the audit regression suite; discovery also includes other unittest classes in the test directory.

## Test groups

- `test_tier1_features.py`: individual features.
- `test_tier2_boundaries.py`: boundary values and error handling.
- `test_tier3_combinations.py`: interactions between features.
- `test_tier4_scenarios.py`: playback and export workflows using `test.mp4` and `asci.mp4`.
- `test_tier5_sharpness_and_settings.py`: rendering and setting propagation.
- `test_tier6_gui_progress_and_output.py`: GUI progress messages and output folders.
- `test_tier7_resolution_and_windowed.py`: render resolution and window configuration.
- `test_audit_regressions.py`: FPS conversion, encoder failures, short audio tracks, source file protection, and malformed data.
- `test_graphite_studio.py`: native selection, live translation, advanced settings, persistence, background jobs, cancellation, and streaming portable exports.
- `test_graphite_help.py`: shared F1 guide, translations, shortcuts and small-window placement.
- `test_public_fixtures.py`: generated video/audio metadata and protection of existing files.

Additional adversarial and benchmark modules cover decoding throughput, seeking, and resource handling. Some expose their own runners rather than unittest cases.

## Interpreting results

A passing run exits with code 0 and reports no failures or errors. Performance measurements depend on the machine and workload. Headless tests do not verify speaker output, interactive desktop use, or a newly packaged EXE.
