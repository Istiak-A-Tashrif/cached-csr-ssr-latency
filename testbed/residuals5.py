"""v4 residuals pooled over all already-used RTT>0 conditions; linear fit per (mode, action, outcome)."""
import json
from collections import defaultdict
from lib import load, mean
from model4 import predict
F = json.load(open('results/model4.frozen.json')); tcp0 = F['tcp0']
T0 = {tuple(k.split('|')): v for k, v in F['T0'].items()}; B = F['bytes']

def inputs(r):
    p = r['tcpPre']
    return ((p['client_web'] - tcp0['client_web'] + p['client_api'] - tcp0['client_api']) / 2, max(0.0, p['web_api'] - tcp0['web_api']))

def pooled(tags=('prosp3', 'prosp4', 'diag')):
    out = []
    for tag in tags:
        acts, runs, _, _ = load(f'{tag}.jsonl', f'{tag}-runs.jsonl')
        for a in acts:
            r = runs[a['runId']]
            if not r.get('tcpPre'): continue
            c, i = inputs(r)
            out.append(dict(a, c=c, i=i, res=a['latencyMs'] - predict(a['mode'], a['action'], a['o'], c, i, T0, B, 10e6)))
    return out

def lstsq(X, y):
    """Normal equations for small k (stdlib)."""
    k = len(X[0]); A = [[sum(x[p] * x[q] for x in X) for q in range(k)] for p in range(k)]
    b = [sum(x[p] * yy for x, yy in zip(X, y)) for p in range(k)]
    for col in range(k):  # Gaussian elimination
        piv = max(range(col, k), key=lambda r: abs(A[r][col])); A[col], A[piv] = A[piv], A[col]; b[col], b[piv] = b[piv], b[col]
        for r in range(k):
            if r != col and A[col][col]:
                f = A[r][col] / A[col][col]; A[r] = [a - f * c for a, c in zip(A[r], A[col])]; b[r] -= f * b[col]
    return [b[i] / A[i][i] if A[i][i] else 0.0 for i in range(k)]

if __name__ == '__main__':
    P = pooled()
    cells = defaultdict(list)
    for a in P: cells[(a['mode'], a['action'], a['o'], a['rtt'], a['irtt'])].append(a)
    print("mode action outcome     | residual by (client RTT, internal RTT)")
    groups = defaultdict(list)
    for k, v in cells.items(): groups[k[:3]].append((k[3], k[4], mean(x['res'] for x in v), len(v)))
    for g in sorted(groups):
        print(f"{g[0]} {g[1]:7} {g[2]:9} | " + "  ".join(f"({c},{i}):{r:+6.1f}" for c, i, r, n in sorted(groups[g])))
