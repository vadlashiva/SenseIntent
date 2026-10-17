"""Run one method over WSN-IntentBench and save one JSON line per intent (resumable).

Examples (from the code folder):
  python run_eval.py default    ../data/intents.jsonl ../results/default.jsonl
  python run_eval.py rule       ../data/intents.jsonl ../results/rule.jsonl
  python run_eval.py oracle     ../data/intents.jsonl ../results/oracle.jsonl
  python run_eval.py sensintent ../data/intents.jsonl ../results/sensintent_llama70b.jsonl --provider groq --model llama-3.3-70b-versatile
  python run_eval.py zeroshot   ../data/intents.jsonl ../results/zeroshot_llama70b.jsonl   --provider groq --model llama-3.3-70b-versatile
  python run_eval.py llm_repair ../data/intents.jsonl ../results/repair_llama70b.jsonl     --provider groq --model llama-3.3-70b-versatile
  add --limit 20 for a quick trial. If the free-tier daily limit is reached, run the same command again
  later: finished intents are skipped.
"""
import argparse, json, os, sys, time, traceback
from agent import run_method, Verifier
from llm import LLM

ap = argparse.ArgumentParser()
ap.add_argument('method'); ap.add_argument('intents'); ap.add_argument('out')
ap.add_argument('--provider', default='groq'); ap.add_argument('--model', default='llama-3.3-70b-versatile')
ap.add_argument('--table', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'gt_table.csv'))
ap.add_argument('--limit', type=int, default=0); ap.add_argument('--explain', action='store_true')
a = ap.parse_args()

os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
done = set()
if os.path.exists(a.out):
    done = {json.loads(l)['id'] for l in open(a.out, encoding='utf-8') if l.strip()}
intents = [json.loads(l) for l in open(a.intents, encoding='utf-8')]
if a.limit: intents = intents[:a.limit]
ver = Verifier(a.table)
llm = LLM(a.provider, a.model) if a.method in ('zeroshot', 'llm_repair', 'sensintent') else None

with open(a.out, 'a', encoding='utf-8') as fh:
    for k, it in enumerate(intents):
        if it['id'] in done: continue
        c0 = llm.calls if llm else 0; t0 = time.time()
        try:
            res = run_method(a.method, it, ver, llm, explain=a.explain)
        except RuntimeError as e:
            print('stopped:', e); sys.exit(2)     # e.g. missing key or daily limit reached; rerun later
        except Exception:
            res = dict(decision='error', error=traceback.format_exc()[-400:])
        res.update(id=it['id'], method=a.method, model=(a.model if llm else None),
                   llm_calls=(llm.calls - c0) if llm else 0, seconds=round(time.time() - t0, 2))
        fh.write(json.dumps(res, default=str) + '\n'); fh.flush()
        print(f"{k+1}/{len(intents)} {it['id']} {it['difficulty']:10s} -> {res['decision']}")
if llm:
    print(f'LLM calls {llm.calls}, prompt tokens {llm.prompt_tokens}, completion tokens {llm.completion_tokens}')
