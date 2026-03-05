import xml.etree.ElementTree as ET
import sys
from collections import defaultdict

tree = ET.parse(sys.argv[1])
root = tree.getroot()

failures = defaultdict(list)
errors = defaultdict(list)

for testcase in root.iter("testcase"):
    file_path = testcase.get("file")
    name = testcase.get("name")
    
    for fail in testcase.iter("failure"):
        failures[file_path].append((name, fail.get("message")))
        
    for err in testcase.iter("error"):
        errors[file_path].append((name, err.get("message")))

with open("pytest_summary.txt", "w", encoding="utf-8") as f:
    f.write("=== FAILURES ===\n")
    for fp, fails in failures.items():
        f.write(f"\n{fp}:\n")
        for name, msg in fails:
            first_line = msg.split('\n')[0] if msg else "Unknown"
            f.write(f"  - {name}: {first_line}\n")
            
    f.write("\n=== ERRORS ===\n")
    for fp, errs in errors.items():
        f.write(f"\n{fp}:\n")
        # group by error message purely to summarize
        err_types = defaultdict(int)
        for name, msg in errs:
            first_line = msg.split('\n')[0] if msg else "Unknown"
            err_types[first_line] += 1
        for t, c in err_types.items():
            f.write(f"  {c} tests errored: {t}\n")
