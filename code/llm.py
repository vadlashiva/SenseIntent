"""Minimal LLM client for SensIntent (standard library only).

Providers (all OpenAI-compatible chat endpoints):
  groq    https://api.groq.com/openai/v1        key: GROQ_API_KEY
  github  https://models.github.ai/inference    key: GITHUB_TOKEN
  ollama  http://localhost:11434/v1             no key
  rule    no LLM: a regular-expression parser, used as a non-LLM baseline and for testing

Keys are read from environment variables or from a file named .env in the SensIntent folder
(one KEY=value per line). Never paste keys into the code or the paper.
"""
import os, json, re, time, shutil, subprocess, urllib.request, urllib.error

BASE = {'groq': 'https://api.groq.com/openai/v1', 'github': 'https://models.github.ai/inference',
        'ollama': 'http://localhost:11434/v1'}
KEYVAR = {'groq': 'GROQ_API_KEY', 'github': 'GITHUB_TOKEN', 'ollama': None}


def _load_env():
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, '..', '.env'), os.path.join(here, '.env')):
        if os.path.exists(path):
            for line in open(path, encoding='utf-8'):
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.strip().split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
_load_env()


class LLM:
    def __init__(self, provider='groq', model='llama-3.3-70b-versatile', temperature=0.0, min_interval=2.1,
                 reasoning_effort=None, tpm=7500):
        self.provider, self.model, self.temperature = provider, model, temperature
        # gpt-oss models think before answering; a low effort keeps answers complete and within free-tier token limits
        self.reasoning_effort = reasoning_effort or ('low' if 'gpt-oss' in model else None)
        self.tpm = tpm                              # stay under the free tier's tokens-per-minute limit
        self.min_interval = min_interval            # seconds between calls (Groq free tier: 30 per minute)
        self.calls = 0; self.prompt_tokens = 0; self.completion_tokens = 0; self._last = 0.0
        self.use_curl = os.environ.get('SENSINTENT_CURL') == '1'   # switched on automatically after a Cloudflare 1010 block

    @staticmethod
    def _post_urllib(url, data, headers):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors='replace')
        except urllib.error.URLError as e:
            return 0, f'connection failed: {e.reason}'

    @staticmethod
    def _post_curl(url, data, headers):
        cmd = [shutil.which('curl') or 'curl', '-sS', '-X', 'POST', url, '--max-time', '120', '--data-binary', '@-',
               '-w', '\n__HTTP__%{http_code}']
        for k, v in headers.items():
            cmd += ['-H', f'{k}: {v}']
        p = subprocess.run(cmd, input=data, capture_output=True)
        out = p.stdout.decode(errors='replace')
        if '__HTTP__' not in out:
            return 0, 'curl failed: ' + p.stderr.decode(errors='replace')[:300]
        text, code = out.rsplit('\n__HTTP__', 1)
        return int(code or 0), text

    def chat(self, system, user, max_tokens=2000):
        if self.provider == 'rule':
            raise RuntimeError('rule provider has no chat')
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0: time.sleep(wait)
        body = dict(model=self.model, temperature=self.temperature, max_tokens=max_tokens,
                    messages=[dict(role='system', content=system), dict(role='user', content=user)])
        if self.reasoning_effort and self.provider == 'groq':
            body['reasoning_effort'] = self.reasoning_effort; body['include_reasoning'] = False
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
                   # Cloudflare in front of some APIs rejects the default Python-urllib agent (error 1010)
                   'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) SensIntent/1.0'}
        kv = KEYVAR[self.provider]
        if kv:
            key = os.environ.get(kv)
            if not key: raise RuntimeError(f'Set {kv} in the environment or in SensIntent/.env')
            headers['Authorization'] = f'Bearer {key}'
        url = BASE[self.provider] + '/chat/completions'; data = json.dumps(body).encode()
        for attempt in range(12):
            code, text = self._post_curl(url, data, headers) if self.use_curl else self._post_urllib(url, data, headers)
            if code == 403 and '1010' in text and not self.use_curl and shutil.which('curl'):
                self.use_curl = True; continue           # Cloudflare blocked Python's connection: use curl instead
            if code == 429 and re.search(r'per day|TPD|RPD', text):
                raise RuntimeError('daily free-tier limit reached for ' + self.model + ' - run again tomorrow')
            if code in (429, 500, 502, 503) and attempt < 11:
                time.sleep(min(60, 10 + 5 * attempt)); continue
            if code != 200:
                raise RuntimeError(f'{self.provider} HTTP {code}: {text[:300]}')
            out = json.loads(text); break
        self.calls += 1
        u = out.get('usage', {}); self.prompt_tokens += u.get('prompt_tokens', 0); self.completion_tokens += u.get('completion_tokens', 0)
        # pace calls so that tokens per minute stay under the free-tier limit
        used = u.get('total_tokens', u.get('prompt_tokens', 0) + u.get('completion_tokens', 0))
        self._last = time.time() + max(0.0, used * 60.0 / self.tpm - self.min_interval)
        return out['choices'][0]['message'].get('content') or ''


def extract_json(text):
    """Return the first JSON object found in a model reply."""
    text = re.sub(r'```(json)?', '', text)
    depth = 0; start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0: start = i
            depth += 1
        elif ch == '}' and depth:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = None
    return None


# ---------------- rule-based parser (non-LLM baseline) ----------------
_UNIT = {'second': 1, 'seconds': 1, 'minute': 60, 'minutes': 60, 'hour': 3600, 'hours': 3600,
         'day': 86400, 'days': 86400, 'week': 604800, 'weeks': 604800, 'month': 2629800, 'months': 2629800,
         'year': 31557600, 'years': 31557600}
_DUR = r'(\d+(?:\.\d+)?)\s*(seconds?|minutes?|hours?|days?|weeks?|months?|years?)'


def rule_parse(text):
    t = text.lower(); s = dict(lifetime_days=None, coverage=None, latency_max_s=None, sampling_max_s=None, missing=[])
    for clause in re.split(r',| and |--', t):
        m = re.search(_DUR, clause)
        if not m: continue
        sec = float(m.group(1)) * _UNIT[m.group(2)]
        if re.search(r'last|alive|running|run flat|die', clause):
            s['lifetime_days'] = sec / 86400
            if re.search(r'every sensor|all nodes|no sensor', clause): s['coverage'] = 1.0
            elif re.search(r'90%|nine out of ten', clause): s['coverage'] = 0.9
            elif re.search(r'75%|three quarters', clause): s['coverage'] = 0.75
            elif re.search(r'half', clause): s['coverage'] = 0.5
            else: s['coverage'] = 1.0
        elif re.search(r'reach|report|alert|arrive', clause):
            s['latency_max_s'] = sec
        elif re.search(r'reading|sample|measurement', clause):
            s['sampling_max_s'] = sec
    if s['lifetime_days'] is None and re.search(r'long as possible|long time|not die|season', t): s['missing'].append('lifetime')
    if s['latency_max_s'] is None and re.search(r'quickly|real-time|real time', t): s['missing'].append('latency')
    if s['sampling_max_s'] is None and re.search(r'often enough', t): s['missing'].append('sampling')
    return s
