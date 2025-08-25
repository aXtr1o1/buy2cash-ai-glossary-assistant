import subprocess
import sys
import pytest
import os

RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

def run_pytest():
    print("Running unit, integration, system, and regression tests...\n")
    junit_xml = os.path.join(RESULTS_DIR, "pytest_results.xml")
    txt_file = os.path.join(RESULTS_DIR, "pytest_results.txt")
    with open(txt_file, "w") as f:
        exit_code = pytest.main([
            "unit_test.py",
            "integration_test.py",
            "system_test.py",
            "regression_test.py",
            f"--junitxml={junit_xml}",
            "-v"
        ])
    return exit_code

def run_locust():
    print("Running load tests with Locust (headless mode)...\n")
    locust_cmd = [
        "locust",
        "-f", "load_test.py",
        "--headless",
        "--users", "10",
        "--spawn-rate", "2",
        "--run-time", "30s",
        "--host", "http://localhost:8000",
        "--csv", os.path.join(RESULTS_DIR, "locust")
    ]

    txt_file = os.path.join(RESULTS_DIR, "locust_results.txt")
    with open(txt_file, "w") as f:
        result = subprocess.run(locust_cmd, stdout=f, stderr=f)

    return result.returncode

if __name__ == "__main__":
    code = run_pytest()
    load_code = run_locust()
    sys.exit(code or load_code)
