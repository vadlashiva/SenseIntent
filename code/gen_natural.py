"""Create the natural-language split of WSN-IntentBench.

Same requirements and labels as intents.jsonl, re-phrased the way operators talk: numbers in words,
fractions and compound units, indirect statements of lifetime ("we only visit the site every two years"),
coverage stated as tolerated losses, and latency stated as how late information may arrive.
Usage: python gen_natural.py ../data/intents.jsonl ../data/intents_natural.jsonl [seed]
"""
import sys, json, random
rng = random.Random(int(sys.argv[3]) if len(sys.argv) > 3 else 11)

WORDS = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 9: 'nine', 10: 'ten', 12: 'twelve',
         15: 'fifteen', 18: 'eighteen', 20: 'twenty', 30: 'thirty', 60: 'sixty', 90: 'ninety'}

def w(n):
    return WORDS.get(n, str(n)) if rng.random() < 0.7 else str(n)

def life_txt(days):
    m = round(days / 30.4); y = days / 365
    opts = []
    if abs(y - round(y)) < 0.02 and round(y) >= 1:
        Y = round(y)
        opts += [f"{w(Y)} year{'s' if Y > 1 else ''}", f"{w(Y*12)} months", f"{w(Y)} full year{'s' if Y > 1 else ''} without a battery change"]
        if Y == 1: opts += ['a whole year', 'twelve months straight']
    else:
        opts += [f"{w(m)} months"]
        if m == 6: opts += ['half a year', 'six months, a full growing season']
        if m == 3: opts += ['a quarter of a year', 'three months']
        if m == 18: opts += ['a year and a half', 'eighteen months']
    return rng.choice(opts)

def life_clause(days, cov):
    L = life_txt(days)
    if cov == 1.0:
        c = rng.choice([f"not a single node should go dark for {L}", f"we can't afford to lose any node for {L}",
                        f"we only get to the site every {L}, so nothing may die before then"])
    elif cov == 0.9:
        c = rng.choice([f"we can tolerate losing one node in ten, but no more, over {L}",
                        f"at most a tenth of the nodes may be dead after {L}"])
    elif cov == 0.75:
        c = rng.choice([f"three out of four nodes still need to be working after {L}",
                        f"we can live with a quarter of the nodes failing, as long as it lasts {L}"])
    else:
        c = rng.choice([f"it's fine if half the nodes die, as long as the rest keep going for {L}",
                        f"the network is still useful with half its nodes, and that has to hold for {L}"])
    return c

def dur_txt(s):
    if s < 60: return rng.choice([f"{w(int(s))} seconds", f"{int(s)} secs"])
    m = s / 60
    if m == 1: return rng.choice(['a minute', 'one minute', 'sixty seconds'])
    if m == 15: return rng.choice(['a quarter of an hour', 'fifteen minutes'])
    if m == 30: return rng.choice(['half an hour', 'thirty minutes'])
    if m == 60: return rng.choice(['an hour', 'sixty minutes', 'one hour'])
    if m == 120: return rng.choice(['two hours', 'a couple of hours'])
    return rng.choice([f"{w(int(m))} minutes", f"{int(m)} min"])

def lat_clause(s):
    d = dur_txt(s)
    return rng.choice([f"the control room should hear about any change no more than {d} after it happens",
                       f"data may lag by {d} at most", f"if frost hits, I want to know within {d}",
                       f"information older than {d} is useless to us when it lands"])

def samp_clause(s):
    if s == 10: opts = ['six readings a minute', 'a sample every ten seconds']
    elif s == 30: opts = ['two readings a minute', 'a reading twice a minute', 'one sample per half minute']
    elif s == 60: opts = ['a reading every minute', 'sixty readings an hour']
    elif s == 300: opts = ['twelve readings an hour', 'a sample every five minutes']
    elif s == 600: opts = ['six readings an hour', 'one measurement each ten minutes']
    elif s == 900: opts = ['four readings an hour', 'a reading every quarter hour']
    elif s == 1800: opts = ['two readings an hour', 'one sample per half hour']
    else: opts = [f"a reading at least every {dur_txt(s)}"]
    o = rng.choice(opts); who = rng.choice(['agronomists', 'engineers', 'facility team'])
    return rng.choice([f"we need {o}", f"sensors should record {o}", f"the {who} want {o}"])

PLACE = {'farm': ['our soil sensors on the 1-hectare plot', 'the crop field network'],
         'orchard': ['the orchard sensors', 'our nodes across the orchard'],
         'building': ['the factory-floor sensors', 'the climate nodes in the plant']}

AMBIG = {'lifetime': ['Just make the batteries in {p} last as long as you reasonably can.',
                      '{p} should not need maintenance any time soon.'],
         'latency': ['For {p}, we want to see changes pretty much as they happen.',
                     'Alerts from {p} need to come through fast.'],
         'sampling': ['{p}: sample often enough to catch what matters, and keep it alive for the season.']}

def main(inp, outp):
    out = []
    for it in map(json.loads, open(inp, encoding='utf-8')):
        it = dict(it); p = rng.choice(PLACE[it['deploy']])
        if it['difficulty'] == 'ambiguous':
            t = rng.choice(AMBIG[it['must_ask']]).format(p=p); t = t[0].upper() + t[1:]
        else:
            s = it['schema']; cl = []
            if s['lifetime_days'] is not None: cl.append(life_clause(s['lifetime_days'], s['coverage']))
            if s['latency_max_s'] is not None: cl.append(lat_clause(s['latency_max_s']))
            if s['sampling_max_s'] is not None: cl.append(samp_clause(s['sampling_max_s']))
            rng.shuffle(cl)
            body = '; '.join(cl) if rng.random() < 0.5 else '. '.join(c[0].upper() + c[1:] for c in cl)
            t = rng.choice([f"About {p}: {body}.", f"{body[0].upper() + body[1:]}. This is for {p}.",
                            f"Can you set up {p}? {body[0].upper() + body[1:]}."])
        it['text_template'] = it['text']; it['text'] = t; it['id'] = it['id'].replace('WIB', 'WIBN')
        out.append(it)
    with open(outp, 'w', encoding='utf-8') as fh:
        for r in out: fh.write(json.dumps(r) + '\n')
    print('wrote', len(out))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
