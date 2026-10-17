"""SensIntent agent and baselines.

Methods (each returns a dict with decision 'configure' | 'infeasible' | 'clarify'):
  default     fixed default configuration, no LLM
  zeroshot    LLM reads the request and picks the configuration directly
  llm_repair  LLM picks a configuration, sees closed-form predictions and violations, repairs (<= 3 rounds)
  sensintent  LLM parses the request into the schema; the optimiser ranks configurations with the closed
              form; candidates are verified in simulation; infeasible requests get a certificate and the
              closest feasible configuration (shortlisted by the closed form, chosen in simulation);
              the LLM can write a short explanation (off in the benchmark runs)
  oracle      gold schema + optimiser + verification (upper bound that isolates parsing errors)
  rule        regular-expression parser + optimiser + verification (non-LLM baseline)
"""
import json, csv
import model as M
from llm import LLM, extract_json, rule_parse

DEPLOY_DESC = {
    'farm': '100 nodes, 100 m x 100 m field, base station at the centre, two AA cells per node',
    'orchard': '100 nodes, 150 m x 150 m field, base station at the centre, two AA cells per node',
    'building': '50 nodes, 50 m x 50 m floor, base station at the centre, two AA cells per node',
}

PARAMS_TXT = """Configuration parameters and allowed values:
- p: fraction of nodes elected cluster head each round {0.05, 0.1, 0.2}
- Tr: round length in seconds {30, 60, 300, 900, 3600}; data is flushed once per round
- F: readings per node per round {1, 5, 10, 30}; sampling period = Tr/F
- B: readings packed per packet {1, 5, 10, 30} (1 = no buffering)
- Tci: MAC check interval in seconds {0.125, 0.25, 0.5, 1, 2}; radio duty cycle = 0.0025/Tci; each packet also pays a wake-up preamble of Tci/2
- a: adaptive holding {0, 1}; 1 lets low-energy nodes delay data by one extra round
Worst-case reporting latency = (1+a)*Tr + 2*Tci."""

SCHEMA_SYS = """You convert a wireless sensor network operator's request into a JSON constraint record.
Return only JSON with these keys:
  "lifetime_days": required battery lifetime in days, or null if not stated (1 month = 30.4 days, 1 year = 365 days)
  "coverage": fraction of nodes that must still be alive at that time (1.0 for every/all/no node may die, 0.9, 0.75, 0.5 for half), or null if no lifetime
  "latency_max_s": maximum time in seconds for a reading or alert to reach the gateway, or null
  "sampling_max_s": maximum time in seconds between readings, or null
  "missing": list of requirements the operator mentions only vaguely, without a number ("lifetime", "latency", "sampling"); empty if none
Do not invent numbers. A vague phrase such as "as long as possible", "quickly", "near real-time" or "often enough" goes in "missing"."""

CONFIG_SYS = """You configure a battery-powered clustered wireless sensor network (LEACH clustering, low-power-listening MAC) to meet an operator's request.
""" + PARAMS_TXT + """
Return only JSON: {"feasible": true or false, "config": {"p": .., "Tr": .., "F": .., "B": .., "Tci": .., "a": ..}, "reason": "one sentence"}.
Set "feasible" to false if you believe no configuration can meet the request; still give the closest configuration."""

EXPLAIN_SYS = """You explain a sensor-network configuration decision to a non-expert operator in at most three sentences.
Use the numbers given. Do not invent numbers."""


class Verifier:
    """Stage-2 verification: simulated results (worst of five seeds), cached from gt_table.csv."""
    COLS = ('life_c100_days', 'life_c90_days', 'life_c75_days', 'life_c50_days', 'latency_max_s', 'sampling_s')

    def __init__(self, table_csv):
        self.T = {}
        with open(table_csv, newline='', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                k = (r['deploy'], int(r['cid'])); v = {c: float(r[c]) for c in self.COLS}
                self.T[k] = v if k not in self.T else {c: min(self.T[k][c], v[c]) for c in self.COLS}
        self.sim_calls = 0

    def row(self, dep, cid):
        return self.T[(dep, int(cid))]

    def check(self, dep, cid, s):
        self.sim_calls += 1
        r = self.row(dep, cid)
        cov = s.get('coverage') or 1.0
        cov = min([1.0, 0.9, 0.75, 0.5], key=lambda c: abs(c - cov))
        pred = dict(lifetime_days=r[f'life_c{int(cov*100)}_days'], latency_max_s=r['latency_max_s'],
                    sampling_s=r['sampling_s'])
        return pred, M.violations(pred, s)


def _schema_from_gold(g):
    return dict(lifetime_days=g['lifetime_days'], coverage=g['coverage'], latency_max_s=g['latency_max_s'],
                sampling_max_s=g['sampling_max_s'], missing=[])


def _clean_schema(s):
    s = s or {}
    out = {}
    for k in ('lifetime_days', 'coverage', 'latency_max_s', 'sampling_max_s'):
        v = s.get(k)
        try: out[k] = float(v) if v is not None else None
        except (TypeError, ValueError): out[k] = None
    if out['lifetime_days'] is not None and out['coverage'] is None: out['coverage'] = 1.0
    out['missing'] = [m for m in (s.get('missing') or []) if m in ('lifetime', 'latency', 'sampling')]
    return out


def plan_with_tools(s, dep, ver, max_verify=5, max_closest=20):
    """Optimiser + verification shared by sensintent, oracle and rule."""
    if s['missing']:
        return dict(decision='clarify', ask=s['missing'], schema=s)
    if all(s[k] is None for k in ('lifetime_days', 'latency_max_s', 'sampling_max_s')):
        return dict(decision='clarify', ask=['lifetime'], schema=s)
    cands, closest = M.optimise(s, dep, k=max_verify)
    for cid, c, pr in cands:
        sim, viol = ver.check(dep, cid, s)
        if not viol:
            return dict(decision='configure', cid=cid, config=c, predicted=pr, simulated=sim, schema=s)
    if cands:     # closed form said feasible but simulation disagreed for the top candidates
        cid, c, pr = cands[0]
        return dict(decision='configure', cid=cid, config=c, predicted=pr, schema=s, note='unverified')
    # Infeasible: the closed form shortlists the max_verify configurations needing the smallest relaxation
    # (it is pessimistic for some configurations, e.g. with adaptive holding), and simulation picks among them.
    best = None
    for rho_cf, cid, c, pr, _ in M.closest_ranked(s, dep, k=max_closest):
        sim, _ = ver.check(dep, cid, s)
        rho, bind, _ = M.relaxation(sim, s)
        if best is None or rho < best[0] - 1e-9:
            best = (rho, bind, cid, c, pr, sim)
    rho, bind, cid, c, pr, sim = best
    return dict(decision='infeasible', cid=cid, config=c, predicted=pr, simulated=sim,
                binding=bind, relaxation=round(rho, 3), schema=s)


def ask_json(llm, system, user, tries=2):
    """Call the LLM and return its JSON object; retry once; None if no JSON came back."""
    for _ in range(tries):
        out = extract_json(llm.chat(system, user))
        if out is not None:
            return out
    return None


def run_method(method, intent, ver, llm=None, explain=False):
    dep = intent['deploy']; text = intent['text']
    if method == 'default':
        cid, c = M.snap(M.DEFAULT)
        return dict(decision='configure', cid=cid, config=c)
    if method == 'oracle':
        if intent['difficulty'] == 'ambiguous':
            return dict(decision='clarify', ask=[intent['must_ask']])
        return plan_with_tools(_schema_from_gold(intent['schema']), dep, ver)
    if method == 'rule':
        return plan_with_tools(_clean_schema(rule_parse(text)), dep, ver)
    user = f"Deployment: {DEPLOY_DESC[dep]}.\nOperator request: {text}"
    if method == 'zeroshot':
        out = ask_json(llm, CONFIG_SYS, user)
        if out is None or not isinstance(out.get('config'), dict):
            return dict(decision='parse_fail', raw=out)
        cid, c = M.snap(out['config'])
        return dict(decision='configure' if out.get('feasible', True) else 'infeasible', cid=cid, config=c, raw=out)
    if method == 'llm_repair':
        raw = ask_json(llm, SCHEMA_SYS, user)
        if raw is None:
            return dict(decision='parse_fail')
        s = _clean_schema(raw)
        if s['missing']:
            return dict(decision='clarify', ask=s['missing'], schema=s)
        hist = ''
        for rnd in range(3):
            out = ask_json(llm, CONFIG_SYS, user + hist)
            if out is None or not isinstance(out.get('config'), dict):
                return dict(decision='parse_fail', rounds=rnd + 1, schema=s)
            cid, c = M.snap(out['config'])
            pr = M.predict(c, dep); viol = M.violations(pr, s)
            if not viol:
                return dict(decision='configure', cid=cid, config=c, predicted=pr, rounds=rnd + 1, schema=s)
            if out.get('feasible') is False and rnd >= 1:
                return dict(decision='infeasible', cid=cid, config=c, predicted=pr, rounds=rnd + 1, schema=s)
            hist += (f"\nAttempt {rnd+1}: {json.dumps({k: c[k] for k in ('p','Tr','F','B','Tci','a')})} gives predicted "
                     f"lifetime {pr['lifetime_days']:.0f} days, latency {pr['latency_max_s']:.0f} s, sampling {pr['sampling_s']:.0f} s. "
                     f"Violated: {viol}. Propose a better configuration or declare it infeasible.")
        return dict(decision='infeasible', cid=cid, config=c, predicted=pr, rounds=3, schema=s)
    if method == 'sensintent':
        raw = ask_json(llm, SCHEMA_SYS, user)
        if raw is None:
            return dict(decision='parse_fail')
        s = _clean_schema(raw)
        res = plan_with_tools(s, dep, ver)
        if explain and res['decision'] != 'clarify':
            facts = dict(decision=res['decision'], schema=s, config=res['config'], predicted=res.get('predicted'),
                         binding=res.get('binding'), relaxation=res.get('relaxation'))
            res['explanation'] = llm.chat(EXPLAIN_SYS, user + '\nFacts: ' + json.dumps(facts, default=str), max_tokens=200)
        return res
    raise ValueError(method)
