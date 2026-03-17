import subprocess
import sys

def run_test(test_file):
    print(f"Running {test_file}...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-vvv"],
        capture_output=True,
        text=True
    )
    with open("test_debug_out.log", "a", encoding="utf-8") as f:
        f.write(f"=== {test_file} ===\n")
        f.write(result.stdout)
        f.write(result.stderr)
        f.write(f"Return code: {result.returncode}\n\n")

if __name__ == "__main__":
    open("test_debug_out.log", "w").close() # Clear
    run_test("tests/test_architectural_concurrency.py")
    run_test("tests/test_security_audit.py")
