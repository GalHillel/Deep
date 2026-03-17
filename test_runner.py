import os
from pathlib import Path
from tests.test_super_status import test_porcelain_status, test_ahead_behind_metrics
import traceback
import shutil

orig_dir = os.getcwd()

def run_test(test_func):
    os.chdir(orig_dir)
    p = Path("tmp_test_repo_" + test_func.__name__)
    if p.exists(): shutil.rmtree(p)
    p.mkdir()
    try:
        test_func(p.absolute())
        print(f"{test_func.__name__} passed")
    except Exception as e:
        print(f"{test_func.__name__} FAILED")
        traceback.print_exc()
    finally:
        os.chdir(orig_dir)
        if p.exists(): shutil.rmtree(p)

run_test(test_porcelain_status)
run_test(test_ahead_behind_metrics)
