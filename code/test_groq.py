"""Quick connection test for Groq: tries Python's own connection, then curl. Prints the status only (never the key).
Usage (from the code folder):  python test_groq.py
"""
import json, os
import llm
key = os.environ.get('GROQ_API_KEY')
print('key found in .env:', bool(key))
url = llm.BASE['groq'] + '/models'
h = {'Authorization': f'Bearer {key}', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) SensIntent/1.0'}
import urllib.request, urllib.error
for name in ('python', 'curl'):
    if name == 'python':
        req = urllib.request.Request(url, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=30) as r: code, text = r.status, r.read().decode()
        except urllib.error.HTTPError as e: code, text = e.code, e.read().decode(errors='replace')
        except Exception as e: code, text = 0, str(e)
    else:
        import subprocess, shutil
        if not shutil.which('curl'): print('curl: not installed'); continue
        cmd = ['curl', '-sS', url, '-w', '\n__HTTP__%{http_code}'] + sum([['-H', f'{k}: {v}'] for k, v in h.items()], [])
        p = subprocess.run(cmd, capture_output=True); out = p.stdout.decode(errors='replace')
        text, code = (out.rsplit('\n__HTTP__', 1) + ['0'])[:2] if '__HTTP__' in out else (p.stderr.decode(), '0')
    print(f'{name:6s} -> HTTP {code}', '(OK)' if str(code) == '200' else text[:150].replace(key or '#', '***'))
