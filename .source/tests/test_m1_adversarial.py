"""
Milestone M1 Empirical Stress & Adversarial Test Harness.

Executes rigorous empirical stress testing against:
- ascii_engine.video_decoder.VideoDecoder
- ascii_engine.audio_engine.AudioEngine

Tests:
1. High Throughput Decoding (Multi-iteration FPS benchmarks on test.mp4 and asci.mp4)
2. Aspect Ratio Preservation across arbitrary column dimensions & char aspects
3. Rapid Seeking Stress Test (20 sequential random seeks on test.mp4 and asci.mp4)
4. Boundary Seeking & EOF Robustness (seek(duration), seek(past duration), seek(0.0))
5. Memory Leak / Bounded RSS Consumption during sustained decoding (1,200 frames)
6. Fault Injection (nonexistent paths, empty files, text files, corrupt media, audio-only)
7. AudioEngine stress & clock stability under rapid state transitions
"""

from __future__ import annotations

import gc
import json
import os
import random
import sys
import tempfile
import time
import wave
from typing import Any

import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ascii_engine.audio_engine import AudioEngine
from ascii_engine.video_decoder import VideoDecoder


class M1EmpiricalChallenger:
    def __init__(self, test_mp4: str = "test.mp4", asci_mp4: str = "asci.mp4") -> None:
        self.test_mp4 = os.path.abspath(test_mp4)
        self.asci_mp4 = os.path.abspath(asci_mp4)
        self.results: dict[str, Any] = {}
        self.findings: list[dict[str, Any]] = []

    def record_result(self, category: str, data: Any) -> None:
        self.results[category] = data

    def log_finding(self, severity: str, title: str, details: str, reproduction: str, mitigation: str) -> None:
        print(f"\n[FINDING - {severity.upper()}] {title}")
        print(f"  Details: {details}")
        print(f"  Repro: {reproduction}")
        print(f"  Mitigation: {mitigation}")
        self.findings.append({
            "severity": severity,
            "title": title,
            "details": details,
            "reproduction": reproduction,
            "mitigation": mitigation,
        })

    # -------------------------------------------------------------------------
    # TEST 1: High Throughput Decoding Benchmark
    # -------------------------------------------------------------------------
    def test_high_throughput_decoding(self) -> None:
        print("\n=== [TEST 1] High Throughput Decoding Multi-Iteration Benchmark ===")
        videos = [
            ("test.mp4", self.test_mp4, 3),  # 3 full passes
            ("asci.mp4", self.asci_mp4, 2),  # 2 full passes (~1932 frames each)
        ]

        throughput_data: dict[str, Any] = {}

        for name, path, iterations in videos:
            if not os.path.exists(path):
                self.log_finding(
                    "critical",
                    f"Benchmark file missing: {name}",
                    f"Path {path} does not exist.",
                    f"os.path.exists('{path}')",
                    "Ensure media file exists in workspace root.",
                )
                continue

            iteration_stats = []
            for it in range(1, iterations + 1):
                decoder = VideoDecoder(path, target_cols=80, char_aspect=0.55)
                frame_count = 0
                t0 = time.perf_counter()

                for pts, chars, colors in decoder.iter_frames():
                    frame_count += 1
                    if chars.shape != (decoder.rows, decoder.cols):
                        self.log_finding(
                            "high",
                            f"Output tensor shape mismatch in {name}",
                            f"Frame {frame_count} chars shape {chars.shape} != expected {(decoder.rows, decoder.cols)}",
                            "decoder.iter_frames()",
                            "Verify resize dimensions match rows/cols.",
                        )

                elapsed = time.perf_counter() - t0
                fps = frame_count / elapsed if elapsed > 0 else 0.0
                decoder.close()

                print(f"  [{name}] Pass {it}/{iterations}: {frame_count} frames in {elapsed:.3f}s -> {fps:.1f} FPS")
                iteration_stats.append({
                    "iteration": it,
                    "frames": frame_count,
                    "elapsed_s": round(elapsed, 4),
                    "fps": round(fps, 2),
                })

            avg_fps = sum(s["fps"] for s in iteration_stats) / len(iteration_stats)
            min_fps = min(s["fps"] for s in iteration_stats)
            max_fps = max(s["fps"] for s in iteration_stats)

            print(f"  -> {name} Average Throughput: {avg_fps:.1f} FPS (Min: {min_fps:.1f}, Max: {max_fps:.1f})")

            if avg_fps < 100.0:
                self.log_finding(
                    "high",
                    f"{name} throughput below 100 FPS target",
                    f"Measured average FPS was {avg_fps:.1f}, required >= 100 FPS.",
                    "test_high_throughput_decoding()",
                    "Optimize frame resizing and luminance conversion.",
                )

            throughput_data[name] = {
                "passes": iteration_stats,
                "avg_fps": round(avg_fps, 2),
                "min_fps": round(min_fps, 2),
                "max_fps": round(max_fps, 2),
                "passed": avg_fps >= 100.0,
            }

        self.record_result("throughput", throughput_data)

    # -------------------------------------------------------------------------
    # TEST 2: Aspect Ratio Preservation
    # -------------------------------------------------------------------------
    def test_aspect_ratio_preservation(self) -> None:
        print("\n=== [TEST 2] Aspect Ratio Preservation Across Arbitrary Target Columns ===")
        test_cols = [20, 40, 60, 80, 100, 120, 160, 200]
        test_aspects = [0.45, 0.50, 0.55, 0.60]

        aspect_results = []
        decoder = VideoDecoder(self.test_mp4)
        meta = decoder.get_metadata()
        decoder.close()

        img_aspect = meta.width / meta.height  # 720 / 1280 = 0.5625

        for cols in test_cols:
            for char_aspect in test_aspects:
                expected_rows = max(1, round(cols * (meta.height / meta.width) * char_aspect))
                vd = VideoDecoder(self.test_mp4, target_cols=cols, char_aspect=char_aspect)

                if vd.rows != expected_rows:
                    self.log_finding(
                        "medium",
                        f"Row calculation mismatch for cols={cols}, char_aspect={char_aspect}",
                        f"Expected {expected_rows}, got {vd.rows}",
                        "VideoDecoder(..., target_cols=cols, char_aspect=char_aspect)",
                        "Check formula: round(cols * (height / width) * char_aspect)",
                    )

                for pts, chars, colors in vd.iter_frames():
                    if chars.shape != (expected_rows, cols) or colors.shape != (expected_rows, cols, 3):
                        self.log_finding(
                            "high",
                            "Frame tensor dimension mismatch",
                            f"chars: {chars.shape}, colors: {colors.shape}, expected: ({expected_rows}, {cols})",
                            "vd.iter_frames()",
                            "Fix cv2.resize target size (cols, rows)",
                        )
                    break

                physical_aspect = (cols * char_aspect) / expected_rows
                aspect_error = abs(physical_aspect - img_aspect) / img_aspect

                aspect_results.append({
                    "cols": cols,
                    "char_aspect": char_aspect,
                    "rows": vd.rows,
                    "img_aspect": round(img_aspect, 4),
                    "physical_aspect": round(physical_aspect, 4),
                    "error_pct": round(aspect_error * 100, 2),
                })
                vd.close()

        max_err = max(r["error_pct"] for r in aspect_results)
        avg_err = sum(r["error_pct"] for r in aspect_results) / len(aspect_results)
        print(f"  Tested {len(aspect_results)} column/aspect combinations.")
        print(f"  Geometry distortion: Max error: {max_err:.2f}%, Avg error: {avg_err:.2f}%")

        # Corner case: minimal columns (cols=1)
        vd_tiny = VideoDecoder(self.test_mp4, target_cols=1, char_aspect=0.55)
        for pts, chars, colors in vd_tiny.iter_frames():
            if chars.shape[1] != 1 or chars.shape[0] < 1:
                self.log_finding(
                    "medium",
                    "cols=1 edge case failure",
                    f"Shape was {chars.shape}",
                    "VideoDecoder(..., target_cols=1)",
                    "Ensure rows >= 1 and cols >= 1",
                )
            break
        vd_tiny.close()

        # Input validation checks
        invalid_cases = [
            ("cols_zero", {"target_cols": 0, "char_aspect": 0.55, "char_ramp": " .#"}),
            ("cols_neg", {"target_cols": -10, "char_aspect": 0.55, "char_ramp": " .#"}),
            ("aspect_zero", {"target_cols": 80, "char_aspect": 0.0, "char_ramp": " .#"}),
            ("aspect_neg", {"target_cols": 80, "char_aspect": -0.5, "char_ramp": " .#"}),
            ("ramp_empty", {"target_cols": 80, "char_aspect": 0.55, "char_ramp": ""}),
        ]
        for name_case, inv in invalid_cases:
            try:
                VideoDecoder(self.test_mp4, **inv)
                self.log_finding(
                    "medium",
                    f"Invalid argument not rejected: {name_case}",
                    f"Args {inv} did not raise ValueError",
                    f"VideoDecoder('{self.test_mp4}', **{inv})",
                    "Add validation raising ValueError for non-positive or empty inputs.",
                )
            except ValueError:
                pass  # Correctly rejected

        self.record_result("aspect_ratio", {
            "combinations_tested": len(aspect_results),
            "max_error_pct": round(max_err, 2),
            "avg_error_pct": round(avg_err, 2),
            "passed": max_err < 10.0,
        })

    # -------------------------------------------------------------------------
    # TEST 3: Rapid Seeking Stress Test (20 Sequential Seeks)
    # -------------------------------------------------------------------------
    def test_rapid_seeking_stress(self) -> None:
        print("\n=== [TEST 3] Rapid Seeking Stress Test (20 Sequential Random Seeks) ===")
        for name, path in [("test.mp4", self.test_mp4), ("asci.mp4", self.asci_mp4)]:
            vd = VideoDecoder(path, target_cols=80)
            meta = vd.get_metadata()
            duration = meta.duration
            print(f"  [{name}] Duration: {duration:.2f}s, executing 20 random seeks within active window...")

            # Seed for deterministic reproducibility
            rng = random.Random(42)
            # Safe playable window: 0.1s to duration - 1.0s
            seek_targets = [round(rng.uniform(0.1, max(0.5, duration - 1.0)), 3) for _ in range(20)]

            seek_records = []
            for idx, target in enumerate(seek_targets):
                t_seek_start = time.perf_counter()
                ok = vd.seek(target)
                seek_time = time.perf_counter() - t_seek_start

                if not ok:
                    self.log_finding(
                        "high",
                        f"Seek returned False for {name} at {target}s",
                        f"Seek operation to {target} failed.",
                        f"vd.seek({target})",
                        "Ensure PyAV container seek handles timestamps correctly.",
                    )
                    continue

                frame_pts = None
                for pts, chars, colors in vd.iter_frames():
                    frame_pts = pts
                    break

                delta = abs(frame_pts - target) if frame_pts is not None else 999.0
                seek_records.append({
                    "target": target,
                    "frame_pts": round(frame_pts, 3) if frame_pts is not None else None,
                    "delta": round(delta, 3),
                    "seek_time_ms": round(seek_time * 1000, 2),
                })

            vd.close()
            avg_seek_ms = sum(r["seek_time_ms"] for r in seek_records) / len(seek_records)
            max_seek_ms = max(r["seek_time_ms"] for r in seek_records)
            print(f"  [{name}] Completed {len(seek_records)} seeks. Avg seek latency: {avg_seek_ms:.2f}ms, Max: {max_seek_ms:.2f}ms")

            self.record_result(f"seeking_{name}", {
                "total_seeks": len(seek_records),
                "avg_seek_time_ms": round(avg_seek_ms, 2),
                "max_seek_time_ms": round(max_seek_ms, 2),
            })

    # -------------------------------------------------------------------------
    # TEST 4: Boundary Seeking & EOF Robustness (Adversarial Corner Cases)
    # -------------------------------------------------------------------------
    def test_boundary_seeking_and_eof(self) -> None:
        print("\n=== [TEST 4] Boundary Seeking & EOF Robustness (Adversarial Corner Cases) ===")
        vd = VideoDecoder(self.test_mp4)
        duration = vd.metadata.duration

        # 4.1 Seek to 0.0 (rewind)
        ok_0 = vd.seek(0.0)
        first_pts = None
        for pts, chars, colors in vd.iter_frames():
            first_pts = pts
            break
        print(f"  Seek(0.0): ok={ok_0}, first frame pts={first_pts}")
        if first_pts != 0.0:
            self.log_finding(
                "medium",
                "Seek to 0.0 did not yield PTS 0.0",
                f"Got PTS {first_pts}",
                "vd.seek(0.0); next(vd.iter_frames())",
                "Ensure seek(0.0) cleanly starts from the beginning.",
            )

        # 4.2 Seek to negative timestamp (-5.0) -> should clamp to 0.0
        ok_neg = vd.seek(-5.0)
        neg_pts = None
        for pts, chars, colors in vd.iter_frames():
            neg_pts = pts
            break
        print(f"  Seek(-5.0): ok={ok_neg}, frame pts={neg_pts}")
        if neg_pts != 0.0:
            self.log_finding(
                "medium",
                "Seek to negative timestamp did not clamp to 0.0",
                f"Got PTS {neg_pts}",
                "vd.seek(-5.0)",
                "Clamp target_seconds = max(0.0, float(target_seconds))",
            )

        # 4.3 Seek to exact duration (10.467s) or past duration (15.0s)
        # Note: In test.mp4, duration is 10.467s but last frame PTS is 10.433s.
        print(f"  Testing seek to duration ({duration:.3f}s)...")
        vd.seek(duration)
        try:
            frames_after_eof_seek = []
            for pts, chars, colors in vd.iter_frames():
                frames_after_eof_seek.append(pts)
                if len(frames_after_eof_seek) >= 2:
                    break
            print(f"  Seek to duration yielded {len(frames_after_eof_seek)} frames: {frames_after_eof_seek}")
        except Exception as exc:  # noqa: BLE001
            print(f"  CRASH on seek to duration: {type(exc).__name__}: {exc}")
            self.log_finding(
                "critical",
                "VideoDecoder crashes with unhandled av.error.EOFError on seek(duration)",
                f"Seeking to duration ({duration:.3f}s) causes forward-decode loop to exhaust stream. PyAV's decoder enters EOF state without resetting or holding the last frame. When iter_frames() is subsequently called, self.container.decode() raises uncaught av.error.EOFError.",
                "vd = VideoDecoder('test.mp4'); vd.seek(vd.metadata.duration); list(vd.iter_frames())",
                "In VideoDecoder.seek(), track last_frame during forward-decode. If pts >= target_seconds is not met, store self._pending_frame = last_frame. In iter_frames(), wrap decode loop with 'except av.error.EOFError: pass' and set self._at_eof = True.",
            )

        vd.close()

    # -------------------------------------------------------------------------
    # TEST 5: Memory Leak & Bounded Consumption Check
    # -------------------------------------------------------------------------
    def test_memory_leak_bounded_consumption(self) -> None:
        print("\n=== [TEST 5] Memory Leak & Bounded RSS Consumption Check (1,200 Frames) ===")
        process = psutil.Process()
        gc.collect()

        baseline_rss = process.memory_info().rss / (1024 * 1024)
        print(f"  Baseline Process RSS: {baseline_rss:.2f} MB")

        total_target_frames = 1200
        frames_decoded = 0
        rss_samples = []

        vd = VideoDecoder(self.test_mp4, target_cols=80)
        t0 = time.perf_counter()

        while frames_decoded < total_target_frames:
            for pts, chars, colors in vd.iter_frames():
                frames_decoded += 1
                if frames_decoded % 300 == 0:
                    current_rss = process.memory_info().rss / (1024 * 1024)
                    rss_samples.append({
                        "frame": frames_decoded,
                        "rss_mb": round(current_rss, 2),
                    })
                    print(f"    Frame {frames_decoded}/{total_target_frames} - RSS: {current_rss:.2f} MB")
                if frames_decoded >= total_target_frames:
                    break

        vd.close()
        elapsed = time.perf_counter() - t0

        gc.collect()
        final_rss = process.memory_info().rss / (1024 * 1024)
        rss_growth = final_rss - baseline_rss

        fps = frames_decoded / elapsed if elapsed > 0 else 0.0
        print(f"  Decoded {frames_decoded} frames in {elapsed:.3f}s ({fps:.1f} FPS)")
        print(f"  Final RSS: {final_rss:.2f} MB (Net Delta: {rss_growth:+.2f} MB)")

        if rss_growth > 25.0:
            self.log_finding(
                "high",
                f"Unbounded RSS memory growth during decoding: {rss_growth:.2f} MB",
                f"Memory grew from {baseline_rss:.2f} MB to {final_rss:.2f} MB over {frames_decoded} frames.",
                "Sustained iteration over 1,200 frames",
                "Ensure numpy arrays or decoded AVFrames are not referenced in closures or caches.",
            )

        self.record_result("memory_boundedness", {
            "baseline_rss_mb": round(baseline_rss, 2),
            "final_rss_mb": round(final_rss, 2),
            "rss_growth_mb": round(rss_growth, 2),
            "passed": rss_growth <= 25.0,
        })

    # -------------------------------------------------------------------------
    # TEST 6: Fault Injection & Error Diagnostics
    # -------------------------------------------------------------------------
    def test_fault_injection(self) -> None:
        print("\n=== [TEST 6] Fault Injection & Error Diagnostics ===")
        fault_cases: dict[str, Any] = {}

        # 6.1 Nonexistent file path
        nonexistent = "nonexistent_file_adversarial_12345.mp4"
        try:
            VideoDecoder(nonexistent)
            self.log_finding(
                "high",
                "VideoDecoder did not raise FileNotFoundError for nonexistent file",
                f"Path {nonexistent} was accepted without error.",
                f"VideoDecoder('{nonexistent}')",
                "Add os.path.isfile check raising FileNotFoundError.",
            )
            fault_cases["nonexistent_video"] = "FAIL"
        except FileNotFoundError as err:
            msg = str(err)
            bilingual_ok = ("bulunamadı" in msg) and ("not found" in msg.lower())
            fault_cases["nonexistent_video"] = f"PASS (bilingual={bilingual_ok})"
            if not bilingual_ok:
                self.log_finding(
                    "low",
                    "VideoDecoder error message missing bilingual content",
                    f"Message: {msg}",
                    "VideoDecoder(nonexistent)",
                    "Include Turkish and English text in FileNotFoundError.",
                )

        try:
            AudioEngine(nonexistent)
            self.log_finding(
                "high",
                "AudioEngine did not raise FileNotFoundError for nonexistent file",
                f"Path {nonexistent} was accepted without error.",
                f"AudioEngine('{nonexistent}')",
                "Add os.path.isfile check raising FileNotFoundError.",
            )
            fault_cases["nonexistent_audio"] = "FAIL"
        except FileNotFoundError as err:
            msg = str(err)
            bilingual_ok = ("bulunamadı" in msg) and ("not found" in msg.lower())
            fault_cases["nonexistent_audio"] = f"PASS (bilingual={bilingual_ok})"

        # 6.2 Non-video empty file (0 bytes)
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp_empty_path = tmp.name
        try:
            try:
                VideoDecoder(tmp_empty_path)
                self.log_finding(
                    "high",
                    "VideoDecoder did not raise ValueError on empty file",
                    "Empty 0-byte file was accepted without error.",
                    f"VideoDecoder('{tmp_empty_path}')",
                    "Validate container has valid streams or raise ValueError.",
                )
                fault_cases["empty_file"] = "FAIL"
            except ValueError:
                fault_cases["empty_file"] = "PASS (ValueError raised)"

            try:
                ae_empty = AudioEngine(tmp_empty_path)
                if ae_empty.has_audio:
                    self.log_finding(
                        "medium",
                        "AudioEngine reported has_audio=True for empty file",
                        "Empty file should have has_audio=False.",
                        f"AudioEngine('{tmp_empty_path}')",
                        "Ensure has_audio=False on empty files.",
                    )
                ae_empty.close()
                fault_cases["empty_audio"] = "PASS"
            except AttributeError as err:
                self.log_finding(
                    "critical",
                    "AudioEngine raises AttributeError due to nonexistent av.AVError in exception handler",
                    f"AudioEngine.__init__ failed with: {err}. PyAV has no 'AVError' attribute (base exception is av.error.FFmpegError or av.FFmpegError).",
                    f"AudioEngine('{tmp_empty_path}')",
                    "Replace all occurrences of 'av.AVError' with 'av.error.FFmpegError' or 'av.FFmpegError' in ascii_engine/audio_engine.py (lines 82, 126) and ascii_engine/video_decoder.py (lines 108, 284, 294).",
                )
                fault_cases["empty_audio"] = f"CRASH: {err}"
        finally:
            if os.path.exists(tmp_empty_path):
                os.remove(tmp_empty_path)

        # 6.3 Non-video plain text file
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as tmp:
            tmp.write("This is a plain text file, not a video stream.\nLine 2.\n")
            tmp_text_path = tmp.name
        try:
            try:
                VideoDecoder(tmp_text_path)
                self.log_finding(
                    "high",
                    "VideoDecoder did not raise ValueError on text file",
                    "Plain text file was accepted without error.",
                    f"VideoDecoder('{tmp_text_path}')",
                    "Raise ValueError when no video stream is found.",
                )
                fault_cases["text_file"] = "FAIL"
            except ValueError:
                fault_cases["text_file"] = "PASS (ValueError raised)"
        finally:
            if os.path.exists(tmp_text_path):
                os.remove(tmp_text_path)

        # 6.4 Random corrupt bytes
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(os.urandom(4096))
            tmp_corrupt_path = tmp.name
        try:
            try:
                VideoDecoder(tmp_corrupt_path)
                self.log_finding(
                    "high",
                    "VideoDecoder did not raise ValueError on corrupt random bytes",
                    "Corrupted file was accepted without error.",
                    f"VideoDecoder('{tmp_corrupt_path}')",
                    "Catch av.AVError on corrupt files and raise ValueError.",
                )
                fault_cases["corrupt_bytes"] = "FAIL"
            except ValueError:
                fault_cases["corrupt_bytes"] = "PASS (ValueError raised)"
        finally:
            if os.path.exists(tmp_corrupt_path):
                os.remove(tmp_corrupt_path)

        # 6.5 Audio-only WAV file passed to VideoDecoder
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav_path = tmp.name
        try:
            with wave.open(tmp_wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(44100)
                wf.writeframes(b"\x00\x00" * 44100)

            try:
                VideoDecoder(tmp_wav_path)
                self.log_finding(
                    "high",
                    "VideoDecoder did not raise ValueError on audio-only file",
                    "Audio-only file was accepted as video.",
                    f"VideoDecoder('{tmp_wav_path}')",
                    "Check container.streams.video and raise ValueError if empty.",
                )
                fault_cases["audio_only_to_video"] = "FAIL"
            except ValueError as err:
                fault_cases["audio_only_to_video"] = f"PASS ({err})"
        finally:
            if os.path.exists(tmp_wav_path):
                os.remove(tmp_wav_path)

        print(f"  Fault injection completed: {len(fault_cases)} scenarios evaluated.")
        self.record_result("fault_injection", fault_cases)

    # -------------------------------------------------------------------------
    # TEST 7: AudioEngine Master Clock & State Machine Stress
    # -------------------------------------------------------------------------
    def test_audio_engine_stress(self) -> None:
        print("\n=== [TEST 7] AudioEngine Master Clock & State Machine Stress ===")
        audio = AudioEngine(self.test_mp4)
        loaded = audio.load_for_playback()
        print(f"  Audio loaded for playback: {loaded}, duration: {audio.duration:.2f}s")

        operations = [
            ("play", 0.0),
            ("sleep", 0.05),
            ("pause", None),
            ("sleep", 0.03),
            ("resume", None),
            ("sleep", 0.04),
            ("seek", 5.0),
            ("sleep", 0.04),
            ("pause", None),
            ("seek", 2.0),
            ("resume", None),
            ("sleep", 0.05),
            ("seek", 100.0),
            ("sleep", 0.02),
            ("seek", -5.0),
            ("stop", None),
        ]

        for op, val in operations:
            if op == "play":
                audio.play(val)
            elif op == "pause":
                audio.pause()
            elif op == "resume":
                audio.resume()
            elif op == "seek":
                audio.seek(val)
            elif op == "stop":
                audio.stop()
            elif op == "sleep":
                time.sleep(val)

        final_time = audio.get_master_time()
        audio.close()

        if final_time != 0.0:
            self.log_finding(
                "medium",
                "AudioEngine master time not reset to 0.0 after stop()",
                f"Final time was {final_time}",
                "audio.stop(); audio.get_master_time()",
                "Reset _start_offset = 0.0 in stop().",
            )

        dur = 1.0 / 30.0
        late = AudioEngine.is_frame_late(frame_pts=1.0, master_time=1.05, frame_duration=dur)
        not_late = AudioEngine.is_frame_late(frame_pts=1.04, master_time=1.05, frame_duration=dur)

        if not late or not_late:
            self.log_finding(
                "high",
                "AudioEngine.is_frame_late logic inverted or incorrect",
                f"late={late}, not_late={not_late}",
                "AudioEngine.is_frame_late(1.0, 1.05, 1/30)",
                "Condition should be frame_pts < (master_time - frame_duration)",
            )

        print(f"  AudioEngine state transitions completed smoothly. Final master time: {final_time}")
        self.record_result("audio_engine_stress", {
            "operations_count": len(operations),
            "final_time": final_time,
            "is_frame_late_correct": late and not not_late,
        })

    def run_all(self) -> dict[str, Any]:
        self.test_high_throughput_decoding()
        self.test_aspect_ratio_preservation()
        self.test_rapid_seeking_stress()
        self.test_boundary_seeking_and_eof()
        self.test_memory_leak_bounded_consumption()
        self.test_fault_injection()
        self.test_audio_engine_stress()

        has_critical_or_high = any(f["severity"] in ("critical", "high") for f in self.findings)
        verdict = "FAIL" if has_critical_or_high else "CONFIRM"

        print("\n=======================================================")
        print(f">>> CHALLENGE VERDICT: {verdict} ({len(self.findings)} findings) <<<")
        for idx, f in enumerate(self.findings, 1):
            print(f"  {idx}. [{f['severity'].upper()}] {f['title']}")
        print("=======================================================")

        return {
            "verdict": verdict,
            "findings": self.findings,
            "metrics": self.results,
        }


if __name__ == "__main__":
    challenger = M1EmpiricalChallenger()
    result = challenger.run_all()
    # Save structured results to file for auditing
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "m1_stress_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"Empirical results written to: {out_path}")
    sys.exit(0 if result["verdict"] == "CONFIRM" else 1)
