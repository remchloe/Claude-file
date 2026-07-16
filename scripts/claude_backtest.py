# -*- coding: utf-8 -*-
import os, re, sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def extract_signal(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
    except:
        return None
    if 'SIGNAL =' not in text:
        return None
    # 找到 signals 部分的行，提取 code -> signal 映射
    lines = text.split('\n')
    result = {}
    in_signals = False
    date = ''
    phase = ''
    for line in lines:
        if 'SIGNAL =' in line:
            continue
        if '"date"' in line:
            m = re.search(r'"([\d-]+)"', line)
            if m: date = m.group(1)
        if '"market_phase"' in line:
            m = re.search(r'"([^"]+)"', line.split('"market_phase"')[1])
            if m: phase = m.group(1)[:30]
        if '"signals"' in line:
            in_signals = True
            continue
        if '}' in line and in_signals:
            in_signals = False
            continue
        if in_signals:
            m = re.search(r'"([\d.]+XSHG|[\d.]+XSHE)"\s*:\s*(-?\d+)', line)
            if m:
                code = m.group(1)
                sval = int(m.group(2))
                result[code] = sval
    if not result:
        return None
    return {'date': date, 'market_phase': phase, 'signals': result}

def load_signals():
    signals = []
    if not os.path.exists('reports'):
        return signals
    for f in sorted(os.listdir('reports')):
        if not f.endswith('.md'):
            continue
        sig = extract_signal(os.path.join('reports', f))
        if sig and len(sig.get('signals', {})) > 0:
            signals.append(sig)
            print('  [OK] %s: %d signals' % (f, len(sig['signals'])))
        else:
            print('  [!] %s: no SIGNAL' % f)
    return signals

def actual_data():
    return {
        '2026-07-13': {'510300.XSHG':-1.76,'510880.XSHG':0.69,'512800.XSHG':1.56,'588000.XSHG':-4.93,'512170.XSHG':-1.58},
        '2026-07-14': {'510300.XSHG':1.96,'510880.XSHG':2.35,'512800.XSHG':0.26,'588000.XSHG':1.19,'512170.XSHG':2.57},
        '2026-07-15': {'510300.XSHG':0.02,'510880.XSHG':1.50,'512800.XSHG':1.15,'588000.XSHG':-4.56,'512170.XSHG':4.08},
    }

print('=' * 60)
print('Claude Signal Backtest v1.0')
print('=' * 60)
signals = load_signals()
if not signals:
    print('No historical SIGNAL found.')
    sys.exit(0)

actual = actual_data()
all_results = []
for sig in signals:
    date = sig.get('date', '')
    day_data = actual.get(date, {})
    if not day_data:
        continue
    results = {}
    for code, sval in sig['signals'].items():
        ret = day_data.get(code)
        if ret is None:
            continue
        if sval == 1: correct = ret > 0.5
        elif sval == -1: correct = ret < -0.5
        else: correct = -1 < ret < 1
        results[code] = (sval, ret, correct)
    all_results.append({'date': date, 'results': results})

if not all_results:
    print('No matching price data.')
    sys.exit(0)

print('\nBacktest %d days' % len(all_results))

# By sector
stats = {}
for day in all_results:
    for code, r in day['results'].items():
        if code not in stats: stats[code] = [0,0]
        stats[code][0] += 1
        if r[2]: stats[code][1] += 1

print('\n%-10s %-5s %-5s %-6s' % ('Sector', 'Total', 'Hit', 'Rate'))
for code in sorted(stats.keys()):
    t, c = stats[code]
    print('%-10s %-5d %-5d %5.1f%%' % (code.split('.')[0], t, c, c/t*100))

tt = sum(s[0] for s in stats.values())
tc = sum(s[1] for s in stats.values())
print('%-10s %-5d %-5d %5.1f%%' % ('TOTAL', tt, tc, tc/tt*100))

# By direction
sst = {1:[0,0], -1:[0,0], 0:[0,0]}
for day in all_results:
    for code, r in day['results'].items():
        sst[r[0]][0] += 1
        if r[2]: sst[r[0]][1] += 1

print('\nBy direction:')
for s in [1, -1, 0]:
    lbl = {1:'Buy', -1:'Sell', 0:'Hold'}[s]
    t, c = sst[s]
    print('  %s: %d/%d (%.1f%%)' % (lbl, c, t, c/max(t,1)*100))

# Simulated returns
print('\nSimulated returns:')
rets = {}
for code in ['510300.XSHG','510880.XSHG','512800.XSHG','588000.XSHG','512170.XSHG']:
    c = 20000
    for day in all_results:
        ret = actual.get(day['date'], {}).get(code, 0)
        sig = None
        for s in signals:
            if s.get('date') == day['date']:
                sig = s['signals'].get(code, 0)
                break
        exp = {1:1.0, -1:0.5, 0:0.8}.get(sig, 0.8)
        c *= (1 + ret * exp / 100)
    rets[code] = c

total = sum(rets.values())
print('  100000 -> %.0f (%+.2f%%)' % (total, (total-100000)/100000*100))
for code, val in rets.items():
    print('    %s: %+.2f%%' % (code.split('.')[0], (val-20000)/20000*100))
