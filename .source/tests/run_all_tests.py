"""Run tiered test suites and audit regressions with timing and failure reports."""

import os
import sys
import time
import unittest

# Ensure headless drivers
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ANSI Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


class CustomTestResult(unittest.TextTestResult):
    """Custom result collector that captures test results per tier."""
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.successes = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes.append(test)


def run_suite(suite_module_name, suite_display_name):
    """Executes a specific test tier and returns summary statistics."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(suite_module_name)

    with open(os.devnull, "w") as devnull:
        runner = unittest.TextTestRunner(
            verbosity=0,
            resultclass=CustomTestResult,
            stream=devnull,
        )
        t0 = time.perf_counter()
        result = runner.run(suite)
        elapsed = time.perf_counter() - t0

    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)
    passed = total - failures - errors - skipped

    return {
        "name": suite_display_name,
        "module": suite_module_name,
        "total": total,
        "passed": passed,
        "skipped": skipped,
        "failures": failures,
        "errors": errors,
        "elapsed": elapsed,
        "failure_details": result.failures,
        "error_details": result.errors,
    }


def main():
    print(f"\n{BOLD}{CYAN}{'=' * 75}{RESET}")
    print(f"{BOLD}{CYAN}   Video-to-ASCII System -- Test Results   {RESET}")
    print(f"{BOLD}{CYAN}{'=' * 75}{RESET}\n")

    suites_to_run = [
        ("tests.test_graphite_studio", "Graphite: Desktop, Settings & Portable Export"),
        ("tests.test_graphite_help", "Graphite: Player Keyboard Guide"),
        ("tests.test_public_fixtures", "Generated Test Media"),
        ("tests.test_audit_regressions", "Audit: Timing, Worker Errors & Invalid Data"),
        ("tests.test_tier1_features", "Tier 1: Feature Coverage (22 Features x 5)"),
        ("tests.test_tier2_boundaries", "Tier 2: Boundary & Corner Cases (22 Features x 5)"),
        ("tests.test_tier3_combinations", "Tier 3: Cross-Feature Pairwise Interactions"),
        ("tests.test_tier4_scenarios", "Tier 4: Real-World Acceptance Scenarios"),
        ("tests.test_tier5_sharpness_and_settings", "Tier 5: Sharpness & Settings Propagation"),
        ("tests.test_tier6_gui_progress_and_output", "Tier 6: GUI Progress & Output Folders"),
        ("tests.test_tier7_resolution_and_windowed", "Tier 7: Resolution Scaling, Windowed Mode & Taskbar Icon"),
    ]

    results = []
    total_start = time.perf_counter()

    for mod_name, disp_name in suites_to_run:
        sys.stdout.write(f"  Running {disp_name}... ")
        sys.stdout.flush()
        res = run_suite(mod_name, disp_name)
        results.append(res)
        if res["failures"] == 0 and res["errors"] == 0:
            status = f"{GREEN}[PASS]{RESET}"
        else:
            status = f"{RED}[FAIL]{RESET}"
        sys.stdout.write(f"{status} ({res['passed']}/{res['total']} in {res['elapsed']:.2f}s)\n")
        sys.stdout.flush()

    total_elapsed = time.perf_counter() - total_start

    # Table breakdown
    print(f"\n{BOLD}{'=' * 75}{RESET}")
    print(f"{BOLD}{'Tier / Test Suite':<50} {'Total':<6} {'Pass':<6} {'Fail':<6} {'Time':<6}{RESET}")
    print(f"{'-' * 75}")

    total_tests = sum(r["total"] for r in results)
    total_passed = sum(r["passed"] for r in results)
    total_failures = sum(r["failures"] for r in results)
    total_errors = sum(r["errors"] for r in results)

    for r in results:
        pass_color = GREEN if (r["failures"] == 0 and r["errors"] == 0) else RED
        print(f"{r['name']:<50} {r['total']:<6} {pass_color}{r['passed']:<6}{RESET} {r['failures'] + r['errors']:<6} {r['elapsed']:<5.2f}s")

    print(f"{'-' * 75}")
    all_pass = (total_failures == 0 and total_errors == 0)
    summary_color = GREEN if all_pass else RED
    print(f"{BOLD}{'TOTAL':<50} {total_tests:<6} {summary_color}{total_passed:<6}{RESET} {total_failures + total_errors:<6} {total_elapsed:<5.2f}s\n")

    # Print error/failure details if any
    if not all_pass:
        print(f"\n{BOLD}{RED}=== FAILURES & ERRORS ==={RESET}")
        for r in results:
            for test, err in r["failure_details"]:
                print(f"\n{RED}FAIL: {test}{RESET}\n{err}")
            for test, err in r["error_details"]:
                print(f"\n{RED}ERROR: {test}{RESET}\n{err}")

    # Final verdict
    print(f"{'=' * 75}")
    if all_pass:
        print(f"{BOLD}{GREEN}>>> RESULT: ALL PASS ({total_passed}/{total_tests} tests passed, 0 failures, 0 errors in {total_elapsed:.2f}s) <<<{RESET}")
        print(f"{'=' * 75}\n")
        return 0
    else:
        print(f"{BOLD}{RED}>>> RESULT: TEST SUITE FAILED ({total_failures + total_errors} tests failed out of {total_tests}) <<<{RESET}")
        print(f"{'=' * 75}\n")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
