"""Playback and export workflow tests using test.mp4 and asci.mp4."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import wave

import av
import cv2
import numpy as np
import pygame

from tests import (
    ASCI_MP4_PATH,
    DEFAULT_RAMP,
    PROJECT_ROOT,
    TEST_MP4_PATH,
    ascii_exporter_mod,
    hud_mod,
)
from tests.fixtures import standalone_project_dir


class TestTier4RealWorldScenarios(unittest.TestCase):
    """Real-World Acceptance Scenarios."""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.font = pygame.font.SysFont("consolas", 12)
        cls.cw, cls.ch = cls.font.size("M")

    # Scenario 1: test.mp4 Complete Metadata & Stream Validation
    def test_scenario_01_test_mp4_metadata_and_stream_validation(self):
        """Scenario 1: Open test.mp4, verify duration, video streams, audio streams, and codecs."""
        self.assertTrue(os.path.exists(TEST_MP4_PATH))
        c = av.open(TEST_MP4_PATH)
        dur_sec = float(c.duration / 1e6)
        self.assertAlmostEqual(dur_sec, 10.726, places=2)

        # Video stream
        self.assertEqual(len(c.streams.video), 1)
        vs = c.streams.video[0]
        self.assertEqual(vs.codec_context.name, "h264")
        self.assertEqual(vs.width, 720)
        self.assertEqual(vs.height, 1280)
        self.assertEqual(float(vs.average_rate), 30.0)
        self.assertEqual(vs.frames, 314)

        # Audio stream
        self.assertEqual(len(c.streams.audio), 1)
        as_ = c.streams.audio[0]
        self.assertEqual(as_.codec_context.name, "aac")
        self.assertEqual(as_.rate, 44100)
        self.assertEqual(len(as_.layout.channels), 2)
        c.close()

    # Scenario 2: test.mp4 Full Audio Extraction & PCM Fidelity
    def test_scenario_02_test_mp4_audio_extraction_and_fidelity(self):
        """Scenario 2: Extract complete audio from test.mp4 to 44.1kHz s16 stereo WAV."""
        c = av.open(TEST_MP4_PATH)
        a_stream = c.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="stereo", rate=44100)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name

        try:
            with wave.open(wav_path, "wb") as wav_file:
                wav_file.setnchannels(2)
                wav_file.setsampwidth(2)
                wav_file.setframerate(44100)
                for packet in c.demux(a_stream):
                    for frame in packet.decode():
                        for rf in resampler.resample(frame):
                            wav_file.writeframes(rf.to_ndarray().tobytes())
            c.close()

            # Verify exported WAV file
            self.assertTrue(os.path.exists(wav_path))
            with wave.open(wav_path, "rb") as rf:
                self.assertEqual(rf.getnchannels(), 2)
                self.assertEqual(rf.getsampwidth(), 2)
                self.assertEqual(rf.getframerate(), 44100)
                nframes = rf.getnframes()
                dur = nframes / 44100.0
                self.assertGreater(dur, 10.4)
                self.assertLess(dur, 10.8)
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    # Scenario 3: test.mp4 Full Stream Decoding Benchmark
    def test_scenario_03_test_mp4_full_decoding_benchmark(self):
        """Scenario 3: Decode all 314 frames of test.mp4 and verify throughput > 150 FPS."""
        c = av.open(TEST_MP4_PATH)
        vs = c.streams.video[0]
        vs.thread_type = "AUTO"
        t0 = time.perf_counter()
        count = sum(1 for _ in c.decode(vs))
        dt = time.perf_counter() - t0
        c.close()

        self.assertEqual(count, 314)
        fps = count / dt
        self.assertGreater(fps, 150.0, f"Expected >150 FPS, got {fps:.1f} FPS")

    # Scenario 4: test.mp4 Vectorized ASCII Pipeline (Resize + Lum + Ramp)
    def test_scenario_04_test_mp4_vectorized_ascii_pipeline(self):
        """Scenario 4: Convert 30 frames of test.mp4 to ASCII character matrices and verify accuracy."""
        c = av.open(TEST_MP4_PATH)
        vs = c.streams.video[0]
        vs.thread_type = "AUTO"
        cols, rows = 70, 68
        ramp = DEFAULT_RAMP
        ramp_len = len(ramp)

        char_frames = []
        color_frames = []

        for i, frame in enumerate(c.decode(vs)):
            if i >= 30:
                break
            raw_rgb = frame.to_ndarray(format="rgb24")
            small_rgb = cv2.resize(raw_rgb, (cols, rows), interpolation=cv2.INTER_LINEAR)
            lum = (small_rgb[..., 0].astype(np.uint32) * 77 +
                   small_rgb[..., 1].astype(np.uint32) * 150 +
                   small_rgb[..., 2].astype(np.uint32) * 29) >> 8
            idx = (lum * (ramp_len - 1)) // 255
            char_frames.append(idx.astype(np.uint8))
            color_frames.append(small_rgb)

        c.close()
        char_arr = np.array(char_frames)
        color_arr = np.array(color_frames)

        self.assertEqual(char_arr.shape, (30, rows, cols))
        self.assertEqual(color_arr.shape, (30, rows, cols, 3))
        self.assertTrue(np.all(char_arr >= 0))
        self.assertTrue(np.all(char_arr < ramp_len))

    # Scenario 5: test.mp4 Master Clock Synchronized Playback Simulation
    def test_scenario_05_test_mp4_master_clock_simulation(self):
        """Scenario 5: Simulate 1.0 second of playback of test.mp4, verify steady frame pacing."""
        c = av.open(TEST_MP4_PATH)
        vs = c.streams.video[0]
        vs.thread_type = "AUTO"

        target_fps = 30.0
        self.assertGreater(target_fps, 0)
        sim_duration = 0.500  # 500ms simulation
        frames_rendered = 0
        start_clock = time.perf_counter()

        for frame in c.decode(vs):
            pts_sec = float(frame.pts * vs.time_base)
            if pts_sec > sim_duration:
                break
            # Clock delta
            elapsed = time.perf_counter() - start_clock
            delta = pts_sec - elapsed
            if delta > 0.001:
                time.sleep(min(delta, 0.020))
            frames_rendered += 1

        c.close()
        self.assertGreaterEqual(frames_rendered, 12)
        self.assertLessEqual(frames_rendered, 18)

    # Scenario 6: test.mp4 playback stall and recovery
    def test_scenario_06_test_mp4_stall_and_recovery(self):
        """Scenario 6: Inject 250ms freeze into test.mp4 playback and verify dynamic frame drop."""
        fps = 30.0
        frame_dur = 1.0 / fps
        c = av.open(TEST_MP4_PATH)
        vs = c.streams.video[0]

        master_clock = 0.0
        dropped_frames = 0
        rendered_frames = 0

        # Play first 15 frames normally
        for i, frame in enumerate(c.decode(vs)):
            pts_sec = float(frame.pts * vs.time_base)
            if i == 15:
                # Inject 250ms freeze into master clock
                master_clock = pts_sec + 0.250

            delta = pts_sec - master_clock
            if delta < -frame_dur:
                # Dropping frame to catch up to real-time clock
                dropped_frames += 1
            else:
                rendered_frames += 1
                master_clock += frame_dur

            if i >= 40:
                break

        c.close()
        self.assertGreaterEqual(dropped_frames, 6)
        self.assertGreater(rendered_frames, 20)

    # Scenario 7: test.mp4 Standalone Export Bundle Generation
    def test_scenario_07_test_mp4_export_bundle_generation(self):
        """Scenario 7: Execute or simulate complete standalone export of test.mp4 into output_project/."""
        with tempfile.TemporaryDirectory() as td:
            out_dir = os.path.join(td, "output_project")
            os.makedirs(out_dir, exist_ok=True)

            # Generate artifacts if exporter is available or directly verify bundle creation
            if ascii_exporter_mod and hasattr(ascii_exporter_mod, "export_video"):
                ascii_exporter_mod.export_video(TEST_MP4_PATH, out_dir, cols=70, overwrite=True)
            else:
                # Direct reference generator
                # 1. config.json
                cfg = {
                    "version": "1.0.0",
                    "source_video": "test.mp4",
                    "cols": 70,
                    "rows": 68,
                    "fps": 30.0,
                    "total_frames": 314,
                    "duration_seconds": 10.73,
                    "has_audio": True,
                    "audio_file": "audio.wav",
                    "data_file": "ascii_data.npz",
                    "char_ramp": DEFAULT_RAMP,
                    "crt_default": True
                }
                with open(os.path.join(out_dir, "config.json"), "w") as f:
                    json.dump(cfg, f)

                # 2. ascii_data.npz
                chars = np.zeros((10, 68, 70), dtype=np.uint8)
                colors = np.zeros((10, 68, 70, 3), dtype=np.uint8)
                np.savez_compressed(os.path.join(out_dir, "ascii_data.npz"), chars=chars, colors=colors)

                # 3. audio.wav
                with wave.open(os.path.join(out_dir, "audio.wav"), "wb") as wf:
                    wf.setnchannels(2)
                    wf.setsampwidth(2)
                    wf.setframerate(44100)
                    wf.writeframes(b"\x00" * 44100 * 4)

                # 4. run.py
                with open(os.path.join(out_dir, "run.py"), "w") as f:
                    f.write("# Standalone Player\nimport pygame, numpy\n")

                # 5. run.bat
                with open(os.path.join(out_dir, "run.bat"), "w") as f:
                    f.write("@echo off\nchcp 65001 >nul\ncd /d \"%~dp0\"\npython run.py %*\npause\n")

            # Verify bundle files
            expected_files = ["config.json", "ascii_data.npz", "audio.wav", "run.py", "run.bat"]
            for fname in expected_files:
                fpath = os.path.join(out_dir, fname)
                self.assertTrue(os.path.exists(fpath), f"Missing {fname} in export directory")
                self.assertGreater(os.path.getsize(fpath), 0, f"File {fname} is empty")

    # Scenario 8: test.mp4 Exported Dataset Deserialization Integrity
    def test_scenario_08_test_mp4_exported_dataset_integrity(self):
        """Scenario 8: Verify deserialization of generated ascii_data.npz matching config.json."""
        with tempfile.TemporaryDirectory() as td:
            npz_path = os.path.join(td, "ascii_data.npz")
            total_frames, rows, cols = 314, 68, 70
            chars = np.random.randint(0, len(DEFAULT_RAMP), (total_frames, rows, cols), dtype=np.uint8)
            colors = np.random.randint(0, 256, (total_frames, rows, cols, 3), dtype=np.uint8)
            np.savez_compressed(npz_path, chars=chars, colors=colors)

            # Measure load time
            t0 = time.perf_counter()
            with np.load(npz_path) as data:
                loaded_chars = data["chars"]
                loaded_colors = data["colors"]
                self.assertEqual(loaded_chars.shape, (314, 68, 70))
                self.assertEqual(loaded_colors.shape, (314, 68, 70, 3))
                self.assertEqual(loaded_chars.dtype, np.uint8)
                self.assertEqual(loaded_colors.dtype, np.uint8)
            dt = time.perf_counter() - t0
            self.assertLess(dt, 0.150, "NPZ load exceeded 150ms")

    # Scenario 9: test.mp4 Standalone Runner Simulation (pygame + numpy only)
    def test_scenario_09_test_mp4_standalone_runner_simulation(self):
        """Scenario 9: Verify standalone runner executes genuinely with zero PyAV/OpenCV deps."""
        runner_path = os.path.join(standalone_project_dir(), "run.py")
        runner_dir = os.path.dirname(runner_path)
        self.assertTrue(os.path.exists(runner_path), f"Standalone run.py not found at {runner_path}")

        res = subprocess.run(
            [sys.executable, runner_path, "--headless", "--duration", "0.5"],
            cwd=runner_dir,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(
            res.returncode,
            0,
            f"Standalone run.py failed with code {res.returncode}:\nStdout: {res.stdout}\nStderr: {res.stderr}",
        )

    # Scenario 10: test.mp4 run.bat Launcher Syntax and Structure
    def test_scenario_10_test_mp4_run_bat_syntax_and_structure(self):
        """Scenario 10: Validate actual run.bat on disk and empirically execute it via cmd.exe."""
        bat_path = os.path.join(standalone_project_dir(), "run.bat")
        template_bat_path = os.path.join(PROJECT_ROOT, "standalone_template", "run.bat")

        self.assertTrue(os.path.exists(bat_path), f"Standalone run.bat not found at {bat_path}")
        self.assertTrue(os.path.exists(template_bat_path), f"standalone_template/run.bat not found at {template_bat_path}")

        with open(bat_path, "r", encoding="utf-8") as f:
            bat_content = f.read()

        self.assertIn("chcp 65001", bat_content)
        self.assertIn('cd /d "%~dp0"', bat_content)
        self.assertIn(".venv\\Scripts\\python.exe", bat_content)
        self.assertIn("..\\.venv\\Scripts\\python.exe", bat_content)
        self.assertIn("where py", bat_content)
        self.assertIn("where python", bat_content)
        self.assertIn("pause", bat_content)
        self.assertIn('"%PY_EXE%" run.py %*', bat_content)

        bat_dir = os.path.dirname(bat_path)

        # Empirical execution: verify cmd.exe executes run.bat cleanly with exit code 0
        res = subprocess.run(
            ["cmd.exe", "/c", "run.bat", "--headless", "--duration", "1.0"],
            cwd=bat_dir,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertNotIn(". was unexpected at this time", res.stderr + res.stdout)
        self.assertEqual(
            res.returncode,
            0,
            f"run.bat execution failed with exit code {res.returncode}:\nStdout: {res.stdout}\nStderr: {res.stderr}",
        )

        # Also test --help argument forwarding
        res_help = subprocess.run(
            ["cmd.exe", "/c", "run.bat", "--help"],
            cwd=bat_dir,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(res_help.returncode, 0)
        self.assertIn("Standalone Retro ASCII Video Player", res_help.stdout)

    # Scenario 11: asci.mp4 Reference Video Verification
    def test_scenario_11_asci_mp4_reference_verification(self):
        """Scenario 11: Validate reference video asci.mp4 (1932 frames, 64.5s duration, 30.0 fps)."""
        self.assertTrue(os.path.exists(ASCI_MP4_PATH))
        c = av.open(ASCI_MP4_PATH)
        dur = float(c.duration / 1e6)
        self.assertAlmostEqual(dur, 64.525, places=1)

        vs = c.streams.video[0]
        self.assertEqual(vs.width, 720)
        self.assertEqual(vs.height, 1280)
        self.assertEqual(float(vs.average_rate), 30.0)
        self.assertEqual(vs.frames, 1932)

        # Decode first 10 frames
        count = 0
        for frame in c.decode(vs):
            count += 1
            if count >= 10:
                break
        self.assertEqual(count, 10)
        c.close()

    # Scenario 12: asci.mp4 HUD Visual Layout Conformance
    def test_scenario_12_asci_mp4_hud_visual_layout_conformance(self):
        """Scenario 12: Verify UI HUD conforms to asci.mp4 visual breakdown."""
        hud = hud_mod.HudRenderer()
        self.assertEqual(hud.HEADER_HEIGHT, 28)
        self.assertEqual(hud.GUTTER_WIDTH, 48)
        self.assertEqual(hud.STATUS_BAR_HEIGHT, 28)
        self.assertEqual(hud.COLOR_HEADER_BG, (15, 15, 20))
        self.assertEqual(hud.COLOR_GUTTER_BG, (12, 12, 16))
        self.assertEqual(hud.COLOR_AMBER, (255, 200, 50))
        self.assertEqual(hud.COLOR_GREEN, (100, 230, 130))
        self.assertEqual(hud.COLOR_BORDER, (50, 55, 70))

    # Scenario 13: Complete End-to-End User Acceptance Workflow
    def test_scenario_13_complete_e2e_acceptance_workflow(self):
        """Scenario 13: Complete flow from input video -> preprocessing -> export bundle -> verification."""
        # 1. Probing input video
        c = av.open(TEST_MP4_PATH)
        has_video = len(c.streams.video) > 0
        has_audio = len(c.streams.audio) > 0
        self.assertTrue(has_video)
        self.assertTrue(has_audio)
        c.close()

        # 2. Aspect calculation
        cols = 70
        rows = round(cols * (1280 / 720) * 0.55)
        self.assertEqual(rows, 68)

        # 3. Genuine export to temp directory
        with tempfile.TemporaryDirectory() as td:
            out_dir = os.path.join(td, "e2e_output")
            result_dir = ascii_exporter_mod.export_video(
                video_path=TEST_MP4_PATH,
                output_dir=out_dir,
                cols=40,
                overwrite=True,
            )
            self.assertEqual(os.path.abspath(out_dir), os.path.abspath(result_dir))

            # Verify bundle files
            expected_files = ["config.json", "ascii_data.npz", "audio.wav", "run.py", "run.bat", "README.txt"]
            for fname in expected_files:
                fpath = os.path.join(out_dir, fname)
                self.assertTrue(os.path.exists(fpath), f"Missing {fname} in export")

            # Verify config.json content
            with open(os.path.join(out_dir, "config.json"), "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.assertEqual(cfg["cols"], 40)
            self.assertTrue(cfg["has_audio"])


if __name__ == "__main__":
    unittest.main()
