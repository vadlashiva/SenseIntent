"""Ask Groq which models this account can use and print the best large or small chat model.

Usage:  python pick_models.py list     -> prints all available model ids
        python pick_models.py large    -> prints one id (used by RUN_GROQ.bat)
        python pick_models.py small
"""
import sys, json, os, shutil, subprocess, urllib.request, urllib.error
import llm

PREF = {
    'large': ['llama-3.3-70b-versatile', 'openai/gpt-oss-120b', 'meta-llama/llama-4-maverick-17b-128e-instruct',
              'moonshotai/kimi-k2-instruct', 'qwen/qwen3-32b', 'llama3-70b-8192'],
    'small': ['llama-3.1-8b-instant', 'openai/gpt-oss-20b', 'meta-llama/llama-4-scout-17b-16e-instruct',
              'gemma2-9b-it', 'llama3-8b-8192'],
}
SKIP = ('whisper', 'tts', 'guard', 'prompt-guard', 'playai', 'distil', 'compound', 'orpheus', 'safeguard')


def available():
    key = os.environ.get('GROQ_API_KEY')
    h = {'Authorization': f'Bearer {key}', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) SensIntent/1.0'}
    url = llm.BASE['groq'] + '/models'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            data = json.loads(r.read().decode())
    except Exception:
        cmd = ['curl', '-sS', url] + sum([['-H', f'{k}: {v}'] for k, v in h.items()], [])
        data = json.loads(subprocess.run(cmd, capture_output=True).stdout.decode())
    return [m['id'] for m in data.get('data', []) if m.get('active', True) and not any(s in m['id'].lower() for s in SKIP)]


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'list'
    ids = available()
    if what == 'list':
        print('\n'.join(sorted(ids))); sys.exit(0)
    for m in PREF[what]:
        if m in ids:
            print(m); sys.exit(0)
    # fall back: largest-looking id for 'large', smallest for 'small'
    def size(i):
        import re
        n = re.findall(r'(\d+)b', i.lower()); return int(n[-1]) if n else 30
    ids.sort(key=size)
    print(ids[-1] if what == 'large' else ids[0])
