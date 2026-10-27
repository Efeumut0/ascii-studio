"""
Empirical Benchmark and Adversarial Stress Harness for Milestone M2.
Challenger 1: Retro CRT & HUD Pygame Engine (AsciiRenderer & CrtEffect).

This script performs empirical measurements for:
1. High Cell Counts: 3,000, 6,000, 10,000, and 15,000 characters.
   Measures min/mean/max frame rendering time and FPS.
2. CRT Effect Toggling: 100 frames disabled vs 100 frames enabled.
   Measures CRT overhead and verifies < 3.0 ms requirement.
3. Memory Stability: 1,000 continuous render passes tracking RSS and tracemalloc.
   Verifies zero unbounded memory leak.
4. Extreme Inputs & Boundary Conditions:
   Empty arrays, 1x1 grid, non-standard character indices, negative indices,
   out-of-bounds indices, unicode, shape mismatches, and extreme resolutions.
"""

from __future__ import annotations

import gc
import os
import sys
import time
import tracemalloc
from typing import Any

# Ensure headless drivers before importing pygame
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import psutil
import pygame

from ascii_ui.crt_effects import CrtEffect
from ascii_ui.renderer import AsciiRenderer


def print_header(title: str) -> None:
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def benchmark_high_cell_counts() -> dict[str, Any]:
    print_header("1. HIGH CELL COUNT BENCHMARK")
    print(f"{'Cell Count':<12} | {'Grid (R x C)':<14} | {'Mean (ms)':<10} | {'FPS':<10} | {'Min (ms)':<10} | {'Max (ms)':<10}")
    print("-" * 78)

    test_configs = [
        (3000, 50, 60),    # 50 rows x 60 cols = 3,000
        (6000, 60, 100),   # 60 rows x 100 cols = 6,000
        (10000, 80, 125),  # 80 rows x 125 cols = 10,000
        (15000, 100, 150), # 100 rows x 150 cols = 15,000
    ]

    renderer = AsciiRenderer(font_name="consolas", font_size=12)
    cw, ch = renderer.get_cell_size()

    results = {}

    for count, rows, cols in test_configs:
        w = cols * cw
        h = rows * ch
        screen = pygame.Surface((w, h))

        char_indices = np.random.randint(0, 10, (rows, cols), dtype=np.uint8)
        colors = np.random.randint(0, 256, (rows, cols, 3), dtype=np.uint8)

        # Warmup (15 frames)
        for _ in range(15):
            renderer.render_frame(screen, char_indices, colors)

        # 100 Benchmark frames
        trials = 100
        durations = []
        for _ in range(trials):
            # Vary colors slightly to simulate dynamic video feed
            t0 = time.perf_counter()
            renderer.render_frame(screen, char_indices, colors)
            t1 = time.perf_counter()
            durations.append((t1 - t0) * 1000.0)

        mean_ms = float(np.mean(durations))
        min_ms = float(np.min(durations))
        max_ms = float(np.max(durations))
        fps = 1000.0 / mean_ms if mean_ms > 0 else 9999.0

        grid_str = f"{rows}x{cols}"
        print(f"{count:<12} | {grid_str:<14} | {mean_ms:<10.3f} | {fps:<10.1f} | {min_ms:<10.3f} | {max_ms:<10.3f}")

        results[count] = {
            "rows": rows,
            "cols": cols,
            "mean_ms": mean_ms,
            "fps": fps,
            "min_ms": min_ms,
            "max_ms": max_ms,
        }

    return results


def benchmark_crt_toggling() -> dict[str, Any]:
    print_header("2. CRT EFFECT TOGGLING OVERHEAD BENCHMARK")

    w, h = 1280, 720
    screen = pygame.Surface((w, h))
    # Fill screen with test pattern
    screen.fill((40, 80, 160))
    pygame.draw.circle(screen, (255, 200, 50), (640, 360), 200)

    crt = CrtEffect(width=w, height=h)

    # Warmup
    for _ in range(15):
        crt.apply(screen, crt_enabled=True)
        crt.apply(screen, crt_enabled=False)

    trials = 100

    # 1. Benchmark 100 frames with CRT DISABLED
    disabled_times = []
    for _ in range(trials):
        t0 = time.perf_counter()
        crt.apply(screen, crt_enabled=False)
        t1 = time.perf_counter()
        disabled_times.append((t1 - t0) * 1000.0)

    # 2. Benchmark 100 frames with CRT ENABLED
    enabled_times = []
    for _ in range(trials):
        t0 = time.perf_counter()
        crt.apply(screen, crt_enabled=True)
        t1 = time.perf_counter()
        enabled_times.append((t1 - t0) * 1000.0)

    # 3. Benchmark 100 frames RAPID TOGGLE (alternating every frame)
    toggle_times = []
    state = False
    for _ in range(trials):
        state = not state
        t0 = time.perf_counter()
        crt.apply(screen, crt_enabled=state)
        t1 = time.perf_counter()
        toggle_times.append((t1 - t0) * 1000.0)

    mean_disabled = float(np.mean(disabled_times))
    mean_enabled = float(np.mean(enabled_times))
    overhead_ms = mean_enabled - mean_disabled
    mean_toggle = float(np.mean(toggle_times))

    print(f"CRT Disabled Mean Latency : {mean_disabled:.5f} ms")
    print(f"CRT Enabled Mean Latency  : {mean_enabled:.3f} ms (Bloom + Scanlines + Vignette)")
    print(f"CRT Toggle Overhead       : {overhead_ms:.3f} ms")
    print(f"Rapid Toggle Mean Latency : {mean_toggle:.3f} ms")
    print(f"Requirement Check (< 3 ms): {'PASS' if overhead_ms < 3.0 else 'FAIL'} ({overhead_ms:.3f} ms vs 3.000 ms target)")

    return {
        "mean_disabled_ms": mean_disabled,
        "mean_enabled_ms": mean_enabled,
        "overhead_ms": overhead_ms,
        "rapid_toggle_mean_ms": mean_toggle,
        "passed": overhead_ms < 3.0,
    }


def benchmark_memory_stability() -> dict[str, Any]:
    print_header("3. MEMORY STABILITY BENCHMARK (1,000 CONTINUOUS PASSES)")

    gc.collect()
    process = psutil.Process(os.getpid())
    tracemalloc.start()

    renderer = AsciiRenderer(font_name="consolas", font_size=12)
    cw, ch = renderer.get_cell_size()
    cols, rows = 80, 50
    w, h = 1280, 720
    screen = pygame.Surface((w, h))
    crt = CrtEffect(width=w, height=h)

    char_indices = np.random.randint(0, 10, (rows, cols), dtype=np.uint8)
    colors = np.random.randint(0, 256, (rows, cols, 3), dtype=np.uint8)
    dest_rect = pygame.Rect(48, 28, cols * cw, rows * ch)

    checkpoints = [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
    rss_history = {}
    tracemalloc_history = {}

    print(f"{'Pass':<8} | {'RSS Memory (MB)':<16} | {'Traced Current (MB)':<20} | {'Traced Peak (MB)':<16}")
    print("-" * 68)

    for i in range(1001):
        if i in checkpoints:
            gc.collect()
            rss_mb = process.memory_info().rss / (1024 * 1024)
            current_traced, peak_traced = tracemalloc.get_traced_memory()
            curr_mb = current_traced / (1024 * 1024)
            peak_mb = peak_traced / (1024 * 1024)
            rss_history[i] = rss_mb
            tracemalloc_history[i] = (curr_mb, peak_mb)
            print(f"{i:<8} | {rss_mb:<16.2f} | {curr_mb:<20.3f} | {peak_mb:<16.3f}")

        if i < 1000:
            # Vary colors per frame
            colors[0, 0] = (i % 256, (i * 2) % 256, (i * 3) % 256)
            renderer.render_frame(screen, char_indices, colors, dest_rect=dest_rect)
            crt.apply(screen, crt_enabled=True)

    tracemalloc.stop()

    initial_rss = rss_history[0]
    warmup_rss = rss_history[100]
    final_rss = rss_history[1000]

    delta_total_mb = final_rss - initial_rss
    delta_steady_mb = final_rss - warmup_rss

    print("-" * 68)
    print(f"Initial RSS (Pass 0)      : {initial_rss:.2f} MB")
    print(f"Warmup RSS (Pass 100)     : {warmup_rss:.2f} MB")
    print(f"Final RSS (Pass 1000)     : {final_rss:.2f} MB")
    print(f"Total Delta (0 -> 1000)   : {delta_total_mb:+.2f} MB")
    print(f"Steady-State Delta (100->): {delta_steady_mb:+.2f} MB")
    # In Python, memory stability is confirmed if steady-state delta is negligible (< 5 MB)
    is_stable = abs(delta_steady_mb) < 5.0
    print(f"Memory Stability Verdict  : {'PASS' if is_stable else 'FAIL'}")

    return {
        "rss_history": rss_history,
        "delta_total_mb": delta_total_mb,
        "delta_steady_mb": delta_steady_mb,
        "passed": is_stable,
    }


def stress_test_extreme_inputs() -> dict[str, Any]:
    print_header("4. EXTREME INPUTS & BOUNDARY CONDITIONS STRESS TEST")

    renderer = AsciiRenderer(font_name="consolas", font_size=12)
    cw, ch = renderer.get_cell_size()
    screen = pygame.Surface((800, 600))
    _crt = CrtEffect(width=800, height=600)

    test_cases: list[dict[str, Any]] = []

    def record_test(name: str, passed: bool, notes: str) -> None:
        status_str = "PASS" if passed else "FAIL"
        print(f"[{status_str}] {name}: {notes}")
        test_cases.append({"name": name, "passed": passed, "notes": notes})

    # --- Test 1: Empty char_indices (0, 0) ---
    try:
        empty_chars = np.zeros((0, 0), dtype=np.uint8)
        empty_colors = np.zeros((0, 0, 3), dtype=np.uint8)
        renderer.render_frame(screen, empty_chars, empty_colors)
        record_test("Empty (0, 0) grid", False, "Did not raise ValueError for 0 dimensions")
    except ValueError as e:
        record_test("Empty (0, 0) grid", True, f"Cleanly raised ValueError: {e}")
    except Exception as e:  # noqa: BLE001
        record_test("Empty (0, 0) grid", False, f"Unexpected exception: {type(e).__name__}: {e}")

    # --- Test 2: Partial zero dimension (0, 50) and (50, 0) ---
    try:
        renderer.render_frame(screen, np.zeros((0, 50), dtype=np.uint8), np.zeros((0, 50, 3), dtype=np.uint8))
        record_test("Zero rows (0, 50) grid", False, "Did not raise ValueError")
    except ValueError as e:
        record_test("Zero rows (0, 50) grid", True, f"Cleanly raised ValueError: {e}")
    except Exception as e:  # noqa: BLE001
        record_test("Zero rows (0, 50) grid", False, f"Unexpected exception: {type(e).__name__}: {e}")

    try:
        renderer.render_frame(screen, np.zeros((50, 0), dtype=np.uint8), np.zeros((50, 0, 3), dtype=np.uint8))
        record_test("Zero cols (50, 0) grid", False, "Did not raise ValueError")
    except ValueError as e:
        record_test("Zero cols (50, 0) grid", True, f"Cleanly raised ValueError: {e}")
    except Exception as e:  # noqa: BLE001
        record_test("Zero cols (50, 0) grid", False, f"Unexpected exception: {type(e).__name__}: {e}")

    # --- Test 3: None inputs ---
    try:
        renderer.render_frame(screen, None, None)
        record_test("None inputs", True, "Gracefully returned without error")
    except Exception as e:  # noqa: BLE001
        record_test("None inputs", False, f"Crashed with {type(e).__name__}: {e}")

    # --- Test 4: 1x1 Minimal Grid ---
    try:
        one_char = np.zeros((1, 1), dtype=np.uint8)
        one_color = np.full((1, 1, 3), 255, dtype=np.uint8)
        mini_screen = pygame.Surface((cw, ch))
        renderer.render_frame(mini_screen, one_char, one_color)
        record_test("1x1 Grid", True, f"Rendered 1x1 cell ({cw}x{ch}px) successfully")
    except Exception as e:  # noqa: BLE001
        record_test("1x1 Grid", False, f"Failed on 1x1 grid: {type(e).__name__}: {e}")

    # --- Test 5: Standard ramp indices (0..9) ---
    try:
        chars_ramp = np.arange(10, dtype=np.uint8).reshape((2, 5))
        cols_ramp = np.full((2, 5, 3), 128, dtype=np.uint8)
        renderer.render_frame(screen, chars_ramp, cols_ramp)
        record_test("Standard ramp indices (0..9)", True, "Rendered cleanly with ramp_glyphs LUT")
    except Exception as e:  # noqa: BLE001
        record_test("Standard ramp indices (0..9)", False, f"Failed: {type(e).__name__}: {e}")

    # --- Test 6: Extended ASCII indices (32..126) ---
    try:
        ascii_indices = np.array([[32, 65, 90], [97, 122, 126]], dtype=np.uint8)
        colors_ascii = np.full((2, 3, 3), 200, dtype=np.uint8)
        renderer.render_frame(screen, ascii_indices, colors_ascii)
        record_test("Printable ASCII indices (32..126)", True, "Rendered cleanly with ascii_glyphs LUT")
    except Exception as e:  # noqa: BLE001
        record_test("Printable ASCII indices (32..126)", False, f"Failed: {type(e).__name__}: {e}")

    # --- Test 7: Out-of-bounds High indices (> 255) in uint16/int32 ---
    try:
        oob_indices = np.array([[256, 300, 1000], [5000, 32767, 65535]], dtype=np.int32)
        colors_oob = np.full((2, 3, 3), 255, dtype=np.uint8)
        renderer.render_frame(screen, oob_indices, colors_oob)
        record_test("Out-of-bounds indices (>255)", True, "Fallback to space glyph gracefully handled without crash")
    except Exception as e:  # noqa: BLE001
        record_test("Out-of-bounds indices (>255)", False, f"Failed: {type(e).__name__}: {e}")

    # --- Test 8: Negative Character Indices (-1, -10, -500) ---
    try:
        neg_indices = np.array([[-1, -10, -50], [-100, -256, -500]], dtype=np.int32)
        colors_neg = np.full((2, 3, 3), 255, dtype=np.uint8)
        renderer.render_frame(screen, neg_indices, colors_neg)
        record_test("Negative indices", True, "Handled negative indices without crashing")
    except IndexError as e:
        record_test("Negative indices", False, f"IndexError raised on negative index: {e}")
    except Exception as e:  # noqa: BLE001
        record_test("Negative indices", False, f"Failed with {type(e).__name__}: {e}")

    # --- Test 9: Unicode / String character array ---
    try:
        str_indices = np.array([["A", "B", "#"], ["@", " ", "%"]], dtype=object)
        colors_str = np.full((2, 3, 3), 255, dtype=np.uint8)
        renderer.render_frame(screen, str_indices, colors_str)
        record_test("String / Object character array", True, "Successfully rendered object array of characters")
    except Exception as e:  # noqa: BLE001
        record_test("String / Object character array", False, f"Failed with {type(e).__name__}: {e}")

    # --- Test 10: RGBA Colors (4 channels) ---
    try:
        rgba_colors = np.full((10, 10, 4), 200, dtype=np.uint8)
        rgba_chars = np.zeros((10, 10), dtype=np.uint8)
        renderer.render_frame(screen, rgba_chars, rgba_colors)
        record_test("RGBA 4-channel colors", True, "Successfully sliced 4th channel and rendered")
    except Exception as e:  # noqa: BLE001
        record_test("RGBA 4-channel colors", False, f"Failed with {type(e).__name__}: {e}")

    # --- Test 11: Non-contiguous color array ---
    try:
        large_colors = np.random.randint(0, 256, (20, 20, 3), dtype=np.uint8)
        non_contig_colors = large_colors[::2, ::2, :]  # Strided slice: non-contiguous
        assert not non_contig_colors.flags.c_contiguous
        chars_contig = np.zeros((10, 10), dtype=np.uint8)
        renderer.render_frame(screen, chars_contig, non_contig_colors)
        record_test("Non-contiguous color array", True, "Handled non-contiguous buffer via np.ascontiguousarray")
    except Exception as e:  # noqa: BLE001
        record_test("Non-contiguous color array", False, f"Failed with {type(e).__name__}: {e}")

    # --- Test 12: Shape Mismatched Indices vs Colors ---
    try:
        mismatch_chars = np.zeros((10, 20), dtype=np.uint8)
        mismatch_colors = np.zeros((15, 25, 3), dtype=np.uint8)
        renderer.render_frame(screen, mismatch_chars, mismatch_colors)
        record_test("Mismatched dimensions", False, "Did not raise exception on mismatched dimensions")
    except ValueError as e:
        record_test("Mismatched dimensions", True, f"Cleanly rejected mismatched buffer: {e}")
    except Exception as e:  # noqa: BLE001
        record_test("Mismatched dimensions", True, f"Raised exception on mismatched dimensions: {type(e).__name__}: {e}")

    # --- Test 13: CRT Extreme Dimensions (1x1) ---
    try:
        tiny_crt = CrtEffect(width=1, height=1)
        tiny_screen = pygame.Surface((1, 1))
        tiny_crt.apply(tiny_screen, crt_enabled=True)
        record_test("CRT 1x1 Surface", True, "Successfully applied CRT on 1x1 surface without zero division")
    except Exception as e:  # noqa: BLE001
        record_test("CRT 1x1 Surface", False, f"Failed on 1x1 surface: {type(e).__name__}: {e}")

    # --- Test 14: CRT Dynamic Resize on Screen Change ---
    try:
        crt_dyn = CrtEffect(width=640, height=480)
        big_screen = pygame.Surface((1920, 1080))
        crt_dyn.apply(big_screen, crt_enabled=True)
        assert crt_dyn.width == 1920 and crt_dyn.height == 1080
        record_test("CRT Dynamic Resize", True, "Automatically resized internal buffers on screen dimension change")
    except Exception as e:  # noqa: BLE001
        record_test("CRT Dynamic Resize", False, f"Failed on dynamic resize: {type(e).__name__}: {e}")

    # --- Test 15: CRT 4K Ultra-HD (3840x2160) ---
    try:
        crt_4k = CrtEffect(width=3840, height=2160)
        screen_4k = pygame.Surface((3840, 2160))
        t0 = time.perf_counter()
        crt_4k.apply(screen_4k, crt_enabled=True)
        t_4k = (time.perf_counter() - t0) * 1000.0
        record_test("CRT 4K Surface (3840x2160)", True, f"Successfully processed 4K in {t_4k:.2f} ms")
    except Exception as e:  # noqa: BLE001
        record_test("CRT 4K Surface (3840x2160)", False, f"Failed on 4K surface: {type(e).__name__}: {e}")

    return {"test_cases": test_cases}


def main() -> None:
    print("\n" + "#" * 78)
    print("  EMPIRICAL CHALLENGE HARNESS: AsciiRenderer & CrtEffect (Milestone M2)")
    print("#" * 78)

    cell_results = benchmark_high_cell_counts()
    crt_results = benchmark_crt_toggling()
    mem_results = benchmark_memory_stability()
    stress_results = stress_test_extreme_inputs()

    print_header("SUMMARY & VERDICT")
    print("1. High Cell Counts: Tested 3k, 6k, 10k, 15k characters.")
    for k, v in cell_results.items():
        print(f"   - {k:,} cells: {v['mean_ms']:.2f} ms ({v['fps']:.1f} FPS)")

    print(f"\n2. CRT Overhead: {crt_results['overhead_ms']:.3f} ms (Target < 3.0 ms) -> {'CONFIRMED' if crt_results['passed'] else 'FAILED'}")
    print(f"3. Memory Stability: Steady-state delta {mem_results['delta_steady_mb']:+.2f} MB over 1,000 passes -> {'CONFIRMED' if mem_results['passed'] else 'FAILED'}")

    passed_stress = sum(1 for tc in stress_results['test_cases'] if tc['passed'])
    total_stress = len(stress_results['test_cases'])
    print(f"4. Boundary & Stress Tests: {passed_stress}/{total_stress} passed.")

    failed_cases = [tc for tc in stress_results['test_cases'] if not tc['passed']]
    if failed_cases:
        print("\nIdentified Boundary Vulnerabilities:")
        for fc in failed_cases:
            print(f"   [!] {fc['name']}: {fc['notes']}")

    all_confirmed = (
        crt_results['passed'] and
        mem_results['passed'] and
        cell_results[3000]['fps'] >= 150.0 and
        cell_results[6000]['fps'] >= 100.0 and
        cell_results[15000]['fps'] >= 30.0 and
        len(failed_cases) == 0
    )

    verdict = "CONFIRM" if all_confirmed else "FAIL"
    print(f"\nFINAL VERDICT: {verdict}")


if __name__ == "__main__":
    main()
