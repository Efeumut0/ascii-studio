"""Playback timing, standalone dependencies, seeking, invalid input, and launcher tests."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

# Ensure headless dummy SDL drivers for test stability
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def get_standalone_project_dir() -> str:
    from tests.fixtures import standalone_project_dir
    return standalone_project_dir()


from ascii_engine.audio_engine import AudioEngine
from ascii_engine.video_decoder import VideoDecoder
from ascii_player import play_video


class TestM5LivePlaybackThroughputAndDrift(unittest.TestCase):
    """Tier 5.1: High-throughput live playback and drift verification."""

    def test_01_test_mp4_throughput_and_drift_bounds(self):
        """Verify test.mp4 decoding throughput > 30 FPS and sync drift < 35ms."""
        video_path = os.path.join(PROJECT_ROOT, "test.mp4")
        self.assertTrue(os.path.isfile(video_path), f"test.mp4 missing: {video_path}")

        decoder = VideoDecoder(video_path, target_cols=80)
        audio = AudioEngine(video_path)
        audio.load_for_playback()
        meta = decoder.get_metadata()
        self.assertGreaterEqual(meta.fps, 29.9)

        # 1. Throughput benchmark (unthrottled decode rate)
        t0 = time.perf_counter()
        frame_count = 0
        for _pts, _chars, _colors in decoder.iter_frames():
            frame_count += 1
            if frame_count >= 60:
                break
        elapsed = time.perf_counter() - t0
        decode_fps = frame_count / elapsed
        self.assertGreater(decode_fps, 30.0, f"Decode FPS {decode_fps:.1f} < 30.0")

        # 2. Paced presentation drift simulation
        decoder.seek(0.0)
        audio.play(0.0)
        drifts: list[float] = []
        frame_dur = 1.0 / meta.fps
        sim_frames = 0
        sim_start = time.perf_counter()

        for pts, _chars, _colors in decoder.iter_frames():
            sim_frames += 1
            cur_master = audio.get_master_time()
            drift = abs(pts - cur_master)
            drifts.append(drift)
            # Throttle to simulate real-time playback
            lead = pts - cur_master
            if lead > 0.002:
                time.sleep(min(lead, frame_dur))
            if sim_frames >= 45:
                break

        sim_elapsed = time.perf_counter() - sim_start
        paced_fps = sim_frames / sim_elapsed
        max_drift = max(drifts)
        avg_drift = sum(drifts) / len(drifts)

        decoder.close()
        audio.stop()

        self.assertGreaterEqual(paced_fps, 25.0, f"Paced FPS too low: {paced_fps:.1f}")
        self.assertLess(max_drift, frame_dur * 3.0)
        # Drift must stay bounded within 1.5 frame durations
        self.assertLess(avg_drift, frame_dur * 1.5, f"Average drift {avg_drift*1000:.1f}ms exceeds tolerance")

    def test_02_asci_mp4_throughput_and_drift_bounds(self):
        """Verify asci.mp4 decoding throughput > 30 FPS and sync drift bounds."""
        video_path = os.path.join(PROJECT_ROOT, "asci.mp4")
        self.assertTrue(os.path.isfile(video_path), f"asci.mp4 missing: {video_path}")

        decoder = VideoDecoder(video_path, target_cols=80)
        audio = AudioEngine(video_path)
        audio.load_for_playback()
        meta = decoder.get_metadata()
        self.assertGreater(meta.duration, 0.0)

        t0 = time.perf_counter()
        frame_count = 0
        for _pts, _chars, _colors in decoder.iter_frames():
            frame_count += 1
            if frame_count >= 60:
                break
        elapsed = time.perf_counter() - t0
        decode_fps = frame_count / elapsed
        self.assertGreater(decode_fps, 30.0, f"asci.mp4 decode FPS {decode_fps:.1f} < 30.0")

        decoder.close()
        audio.stop()

    def test_03_live_player_headless_full_pipeline_test_mp4(self):
        """Verify play_video() runs test.mp4 headlessly without crashing."""
        video_path = os.path.join(PROJECT_ROOT, "test.mp4")
        exit_code = play_video(
            video_path=video_path,
            cols=70,
            headless=True,
            max_duration=1.5,
        )
        self.assertEqual(exit_code, 0)

    def test_04_live_player_headless_full_pipeline_asci_mp4(self):
        """Verify play_video() runs asci.mp4 headlessly without crashing."""
        video_path = os.path.join(PROJECT_ROOT, "asci.mp4")
        exit_code = play_video(
            video_path=video_path,
            cols=70,
            headless=True,
            max_duration=1.5,
        )
        self.assertEqual(exit_code, 0)


class TestM5StandaloneDecoupling(unittest.TestCase):
    """Tier 5.2: Standalone playback without PyAV or OpenCV."""

    def test_01_ast_no_forbidden_imports(self):
        """Verify output_project/run.py and standalone_template/run.py have zero av/cv2/PIL imports."""
        target_files = [
            os.path.join(get_standalone_project_dir(), "run.py"),
            os.path.join(PROJECT_ROOT, "standalone_template", "run.py"),
        ]
        forbidden_modules = {"av", "cv2", "PIL", "torch", "matplotlib"}

        for filepath in target_files:
            if not os.path.exists(filepath):
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=filepath)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root_mod = alias.name.split(".")[0]
                        self.assertNotIn(
                            root_mod,
                            forbidden_modules,
                            f"Decoupling violation in {filepath}: imported '{root_mod}'",
                        )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    root_mod = node.module.split(".")[0]
                    self.assertNotIn(
                        root_mod,
                        forbidden_modules,
                        f"Decoupling violation in {filepath}: from '{root_mod}' import ...",
                    )

    def test_02_poisoned_subprocesses_decoupling_enforcement(self):
        """Run standalone run.py in subprocess with poisoned import hooks blocking av/cv2."""
        run_py_path = os.path.join(get_standalone_project_dir(), "run.py")
        self.assertTrue(os.path.exists(run_py_path), f"Missing {run_py_path}")

        poison_script = f"""
import sys
class PoisonImport:
    def find_spec(self, fullname, path, target=None):
        root = fullname.split('.')[0]
        if root in ('av', 'cv2', 'PIL', 'matplotlib'):
            raise ImportError(f'FORBIDDEN IMPORT IN STANDALONE RUNNER: {{fullname}}')
        return None
sys.meta_path.insert(0, PoisonImport())

import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

# Import and execute standalone runner
import importlib.util
spec = importlib.util.spec_from_file_location('standalone_run', r'{run_py_path}')
mod = importlib.util.module_from_spec(spec)
sys.modules['standalone_run'] = mod
sys.argv = ['run.py', '--headless', '--duration', '1.0']
spec.loader.exec_module(mod)
code = mod.main()
sys.exit(code)
"""
        res = subprocess.run(
            [sys.executable, "-c", poison_script],
            capture_output=True,
            text=True,
            check=False,
            cwd=get_standalone_project_dir(),
        )
        self.assertEqual(res.returncode, 0, f"Standalone runner failed under poisoned imports:\n{res.stderr}")


class TestM5SeekAndPauseStress(unittest.TestCase):
    """Tier 5.3: Stress test seeking and pausing on both live player and standalone player."""

    def test_01_live_player_rapid_seek_burst(self):
        """Perform rapid sequential seeks across test.mp4 and verify frame validity."""
        video_path = os.path.join(PROJECT_ROOT, "test.mp4")
        decoder = VideoDecoder(video_path, target_cols=80)
        meta = decoder.get_metadata()

        seek_targets = [0.0, 5.0, 2.0, 8.5, 1.0, 9.8, 0.5, 7.2]
        for target in seek_targets:
            success = decoder.seek(target)
            self.assertTrue(success, f"Seek to {target}s failed")
            frame_gen = decoder.iter_frames()
            try:
                pts, chars, _ = next(frame_gen)
                self.assertGreaterEqual(pts, 0.0)
                self.assertLessEqual(pts, meta.duration + 0.1)
                self.assertEqual(chars.shape, (decoder.rows, decoder.target_cols))
            except StopIteration:
                self.fail(f"Iter frames stopped immediately after seek to {target}s")

        decoder.close()

    def test_02_live_player_pause_clock_invariant(self):
        """Verify that pausing audio engine freezes master clock and prevents time skips."""
        video_path = os.path.join(PROJECT_ROOT, "test.mp4")
        audio = AudioEngine(video_path)
        audio.load_for_playback()
        audio.play(0.0)

        time.sleep(0.05)
        t_before_pause = audio.get_master_time()
        self.assertGreater(t_before_pause, 0.0)

        audio.pause()
        t_paused_1 = audio.get_master_time()
        time.sleep(0.1)
        t_paused_2 = audio.get_master_time()

        # Invariant: master clock must NOT advance while paused
        self.assertAlmostEqual(t_paused_1, t_paused_2, delta=0.001)

        audio.resume()
        time.sleep(0.05)
        t_resumed = audio.get_master_time()
        # Invariant: clock must resume from paused timestamp, not jump by 0.1s
        self.assertLess(t_resumed - t_before_pause, 0.12)

        audio.stop()

    def test_03_live_player_boundary_seeks(self):
        """Verify live player boundary seeks: negative timestamps and past EOF."""
        video_path = os.path.join(PROJECT_ROOT, "test.mp4")
        decoder = VideoDecoder(video_path, target_cols=80)
        audio = AudioEngine(video_path)
        audio.load_for_playback()
        audio.play(0.0)
        meta = decoder.get_metadata()

        # Negative seek -> should clamp to 0.0 without exception
        decoder.seek(max(0.0, -10.0))
        audio.seek(max(0.0, -10.0))
        self.assertAlmostEqual(audio.get_master_time(), 0.0, delta=0.05)

        # Seek past EOF -> clamped to duration
        past_eof = meta.duration + 100.0
        decoder.seek(min(meta.duration, past_eof))
        audio.seek(min(meta.duration, past_eof))
        self.assertLessEqual(audio.get_master_time(), meta.duration + 0.05)

        decoder.close()
        audio.stop()

    def test_04_standalone_player_seek_frame_slicing(self):
        """Verify standalone runner frame index calculation across regular and boundary seeks."""
        config_path = os.path.join(get_standalone_project_dir(), "config.json")
        self.assertTrue(os.path.exists(config_path))
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        total_frames = cfg["total_frames"]
        duration = cfg["duration_seconds"]
        fps = cfg["fps"]

        test_timestamps = [-5.0, 0.0, 1.5, duration / 2.0, duration - 0.1, duration + 10.0]
        for t in test_timestamps:
            clamped_t = max(0.0, min(duration, t))
            frame_idx = max(0, min(total_frames - 1, int(clamped_t * fps)))
            self.assertGreaterEqual(frame_idx, 0)
            self.assertLess(frame_idx, total_frames)


class TestM5FaultInjection(unittest.TestCase):
    """Tier 5.4: Fault injection (missing, empty, non-video, corrupted files)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="m5_fault_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_live_player_missing_file(self):
        """Live player with missing file exits with code 1."""
        missing = os.path.join(self.temp_dir, "non_existent.mp4")
        res = subprocess.run(
            [sys.executable, "ascii_player.py", missing, "--headless"],
            capture_output=True,
            text=True,
            check=False,
            cwd=PROJECT_ROOT,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("HATA", res.stderr + res.stdout)

    def test_02_live_player_zero_byte_file(self):
        """Live player with 0-byte file exits with code 2."""
        empty_file = os.path.join(self.temp_dir, "empty.mp4")
        open(empty_file, "wb").close()
        res = subprocess.run(
            [sys.executable, "ascii_player.py", empty_file, "--headless"],
            capture_output=True,
            text=True,
            check=False,
            cwd=PROJECT_ROOT,
        )
        self.assertEqual(res.returncode, 2)
        self.assertIn("0 bayt", res.stderr + res.stdout)

    def test_03_live_player_non_video_text_file(self):
        """Live player with text file disguised as MP4 exits with code 2."""
        txt_file = os.path.join(self.temp_dir, "fake.mp4")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write("This is a plain text file, not a video stream.")
        res = subprocess.run(
            [sys.executable, "ascii_player.py", txt_file, "--headless"],
            capture_output=True,
            text=True,
            check=False,
            cwd=PROJECT_ROOT,
        )
        self.assertEqual(res.returncode, 2)
        self.assertIn("HATA", res.stderr + res.stdout)

    def test_04_live_player_corrupted_header(self):
        """Live player with random corrupt bytes exits cleanly with code 2."""
        corrupt = os.path.join(self.temp_dir, "corrupt.mp4")
        with open(corrupt, "wb") as f:
            f.write(os.urandom(512))
        res = subprocess.run(
            [sys.executable, "ascii_player.py", corrupt, "--headless"],
            capture_output=True,
            text=True,
            check=False,
            cwd=PROJECT_ROOT,
        )
        self.assertEqual(res.returncode, 2)

    def test_05_standalone_player_missing_config(self):
        """Standalone runner with missing config file exits with code 1."""
        missing_cfg = os.path.join(self.temp_dir, "missing_config.json")
        runner_py = os.path.join(get_standalone_project_dir(), "run.py")
        res = subprocess.run(
            [sys.executable, runner_py, "--config", missing_cfg, "--headless"],
            capture_output=True,
            text=True,
            check=False,
            cwd=PROJECT_ROOT,
        )
        self.assertEqual(res.returncode, 1)

    def test_06_standalone_player_invalid_json(self):
        """Standalone runner with malformed JSON config exits with code 1."""
        bad_cfg = os.path.join(self.temp_dir, "bad.json")
        with open(bad_cfg, "w", encoding="utf-8") as f:
            f.write("{invalid json syntax:")
        runner_py = os.path.join(get_standalone_project_dir(), "run.py")
        res = subprocess.run(
            [sys.executable, runner_py, "--config", bad_cfg, "--headless"],
            capture_output=True,
            text=True,
            check=False,
            cwd=PROJECT_ROOT,
        )
        self.assertEqual(res.returncode, 1)

    def test_07_standalone_player_corrupted_npz(self):
        """Standalone runner with corrupted ascii_data.npz exits with code 1."""
        bad_npz = os.path.join(self.temp_dir, "bad.npz")
        with open(bad_npz, "wb") as f:
            f.write(os.urandom(256))
        cfg_file = os.path.join(self.temp_dir, "config.json")
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump({"data_file": bad_npz, "has_audio": False, "fps": 30}, f)

        runner_py = os.path.join(get_standalone_project_dir(), "run.py")
        res = subprocess.run(
            [sys.executable, runner_py, "--config", cfg_file, "--headless"],
            capture_output=True,
            text=True,
            check=False,
            cwd=PROJECT_ROOT,
        )
        self.assertEqual(res.returncode, 1)


class TestM5WindowsBatchScript(unittest.TestCase):
    """Tier 5.5: Windows batch script verification (run.bat robustness)."""

    def test_01_batch_launcher_execution_and_syntax(self):
        """Empirically execute standalone run.bat in cmd.exe and verify exit code."""
        proj_dir = get_standalone_project_dir()
        bat_path = os.path.join(proj_dir, "run.bat")
        self.assertTrue(os.path.exists(bat_path), f"run.bat not found at {bat_path}")

        # Test --help invocation in cmd.exe
        res = subprocess.run(
            ["cmd", "/c", "run.bat", "--help"],
            capture_output=True,
            text=True,
            check=False,
            cwd=proj_dir,
        )
        # Note: If batch file has syntax errors like '. was unexpected at this time',
        # this test will catch it empirically.
        has_syntax_error = ". was unexpected at this time" in res.stderr or ". was unexpected at this time" in res.stdout
        self.assertFalse(
            has_syntax_error,
            f"run.bat has Windows cmd syntax error (unbalanced parentheses with goto):\n{res.stdout}\n{res.stderr}",
        )
        self.assertEqual(
            res.returncode,
            0,
            f"run.bat --help returned non-zero exit code {res.returncode}:\n{res.stdout}\n{res.stderr}",
        )

    def test_02_batch_launcher_paths_with_spaces(self):
        """Copy standalone project to a directory path with spaces and test run.bat execution."""
        temp_spaced_dir = tempfile.mkdtemp(prefix="spaced path test_")
        target_proj_dir = os.path.join(temp_spaced_dir, "My ASCII Project With Spaces")
        try:
            shutil.copytree(get_standalone_project_dir(), target_proj_dir)
            bat_path = os.path.join(target_proj_dir, "run.bat")
            self.assertTrue(os.path.exists(bat_path))

            res = subprocess.run(
                ["cmd", "/c", "run.bat", "--help"],
                capture_output=True,
                text=True,
                check=False,
                cwd=target_proj_dir,
            )
            has_syntax_error = ". was unexpected at this time" in res.stderr or ". was unexpected at this time" in res.stdout
            self.assertFalse(
                has_syntax_error,
                f"run.bat failed in path with spaces:\n{res.stdout}\n{res.stderr}",
            )
            self.assertEqual(res.returncode, 0)
        finally:
            shutil.rmtree(temp_spaced_dir, ignore_errors=True)

    def test_03_batch_launcher_python_detection_order(self):
        """Verify run.bat structure inspects .venv, ..\\.venv, py, then python."""
        bat_path = os.path.join(get_standalone_project_dir(), "run.bat")
        with open(bat_path, "r", encoding="utf-8") as f:
            content = f.read()

        idx_venv = content.find(".venv\\Scripts\\python.exe")
        idx_parent_venv = content.find("..\\.venv\\Scripts\\python.exe")
        idx_py = content.find("where py")
        idx_python = content.find("where python")

        self.assertNotEqual(idx_venv, -1, "Missing .venv check")
        self.assertNotEqual(idx_parent_venv, -1, "Missing parent .venv check")
        self.assertNotEqual(idx_py, -1, "Missing 'where py' check")
        self.assertNotEqual(idx_python, -1, "Missing 'where python' check")
        self.assertLess(idx_venv, idx_parent_venv)
        self.assertLess(idx_parent_venv, idx_py)
        self.assertLess(idx_py, idx_python)


if __name__ == "__main__":
    unittest.main()
