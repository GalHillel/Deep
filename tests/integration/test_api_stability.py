import requests
import json

BASE_URL = "http://127.0.0.1:9010"

def test_endpoint(path, method="GET", data=None):
    url = f"{BASE_URL}{path}"
    print(f"Testing {method} {path}...")
    try:
        if method == "GET":
            resp = requests.get(url)
        else:
            resp = requests.post(url, json=data)
        
        print(f"  Status: {resp.status_code}")
        try:
            res_json = resp.json()
            print(f"  Success: {res_json.get('success')}")
            if not res_json.get('success'):
                print(f"  Error: {res_json.get('error')}")
        except:
            print(f"  Response is not JSON: {resp.text[:100]}")
    except Exception as e:
        print(f"  Failed to connect: {e}")

if __name__ == "__main__":
    # Test health
    test_endpoint("/api/health")
    # Test tree
    test_endpoint("/api/tree")
    # Test work
    test_endpoint("/api/work")
    # Test invalid file
    test_endpoint("/api/file?path=non_existent_file.txt")
    # Test invalid POST
    test_endpoint("/api/commit", method="POST", data={"author": "Test", "message": "Test commit"})
