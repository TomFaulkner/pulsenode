#!/usr/bin/env python3
"""
Test runner for pulsenode tests.
"""

import sys
import subprocess
import os


def run_command(cmd, description):
    """Run a command and return the result."""
    print(f"\n{'=' * 60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'=' * 60}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stdout:
        print("STDOUT:")
        print(result.stdout)

    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    print(f"Exit code: {result.returncode}")
    return result.returncode == 0


def main():
    """Main test runner."""
    os.chdir(os.path.dirname(__file__))

    commands = [
        (["python", "-m", "pytest", "tests/unit", "-v"], "Running unit tests"),
        (
            ["python", "-m", "pytest", "tests/integration", "-v", "-m", "not slow"],
            "Running integration tests (fast)",
        ),
        (
            [
                "python",
                "-m",
                "pytest",
                "--cov=src/pulsenode",
                "--cov-report=term-missing",
            ],
            "Running tests with coverage",
        ),
    ]

    all_passed = True

    for cmd, description in commands:
        if not run_command(cmd, description):
            all_passed = False

    print(f"\n{'=' * 60}")
    if all_passed:
        print("✅ All tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
