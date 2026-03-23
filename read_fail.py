import sys
with open('network_fail_4.txt', 'rb') as f:
    data = f.read().decode('utf-16le', errors='replace')
    print(data)
