# SensIntent: code, benchmark and results

Code and data for "SensIntent: An LLM Agent that Turns Operator Intents into Verified,
Energy-Feasible Configurations for Wireless Sensor Networks" (S. Kumar V and C. Shivakeshi).

## Contents
- code/model.py        closed-form energy, lifetime and latency model; configuration grid; optimiser
- code/agent.py        SensIntent and the baselines (default, rule, zeroshot, llm_repair, oracle)
- code/llm.py          minimal OpenAI-compatible LLM client (Groq) and the rule-based parser
- code/run_eval.py     runs one method over the benchmark (resumable)
- code/score.py        metrics table (accuracy, satisfaction, infeasibility P/R/F1, clarification, lifetime ratio)
- code/replan.py       re-applies the tool side to stored results (no LLM calls)
- code/robustness.py   battery-capacity robustness and bootstrap 95% confidence intervals
- code/gt_table.py     builds the ground-truth table with the HCB-XL simulator
- code/gen_intents.py, code/gen_natural.py   generate WSN-IntentBench (template and natural-language splits)
- code/validate.py, code/fig_frontier.py, code/sensitivity.py   closed-form validation and figures
- data/gt_table.csv    simulated lifetimes, latency and sampling for 1,350 configurations x 3 deployments x 5 seeds
- data/intents_natural.jsonl   WSN-IntentBench natural-language split (300 requests with labels); intents.jsonl is the template split
- results/natural_v3/  LLM results reported in the paper (gpt-oss-120b, gpt-oss-20b)
- results/natural/     non-LLM results (default, rule, oracle)

## Reproduce the tables (plain Python 3, no packages needed)
    cd code
    python score.py ../data/intents_natural.jsonl ../results/natural/default.jsonl ../results/natural/rule.jsonl ../results/natural/oracle.jsonl ../results/natural_v3/*.jsonl
    python robustness.py

## Re-run the LLM experiments
1. Copy .env.example to .env and put your own Groq API key after GROQ_API_KEY=.
2. From code/:  python run_eval.py sensintent ../data/intents_natural.jsonl ../results/natural_v3/sensintent_openai_gpt-oss-120b.jsonl --provider groq --model openai/gpt-oss-120b
   (methods: sensintent, zeroshot, llm_repair; on Windows, RUN_GROQ.bat runs everything and SCORE.bat prints the table).
   Runs are resumable; finished requests are skipped.

## Regenerate the ground truth
gt_table.py needs the HCB-XL simulator (https://github.com/vadlashiva/HCB-XL) next to this folder
(../HCB-XL/hcbxl.py) or at HCBXL_PATH, plus numpy and pandas:
    python gt_table.py 5 ../data/gt_table.csv
