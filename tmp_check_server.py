import urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8083/', timeout=5) as r:
        print('STATUS', r.status)
        print(r.read(200).decode('utf-8', errors='replace'))
except Exception as exc:
    print('ERROR', repr(exc))
