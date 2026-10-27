# Test suite readiness report (TEST_READY.md)

The last recorded source verification ran on 28 October 2026:

- Command: `python -m unittest discover -s tests -q`
- Result: 361 tests passed in 45.428 seconds using generated video patterns and stereo tones.
- UI checks cover hover feedback, row selection, scrolling, and rounded/restored window corners.
- F1 opens the shared Graphite guide in both players; language, seek interval, and small-window placement are covered.
- Ruff reported no issues in the application modules and changed test files.
- The Windows executable was separately checked on 27 October without source or Python on PATH, in Turkish and English.
- Frozen playback, MP4 rendering, EXE export, and generated players with and without audio completed successfully.
- A frozen worker produced a 3840x2160 MP4, and both encoded frames decoded successfully.

This is a record of that run, not a guarantee about later changes. Run the tests again after editing the project. Commands and test groups are listed in `TEST_INFRA.md`.
