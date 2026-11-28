#!/usr/bin/env python3
"""Topic-adaptive SFX for a cartoon-3d-short: reads the project's narration and places procedural sounds on its words.

  python scripts/generate_sfx.py --project-dir ./my-short            # cue list only (audio/cues.md + audio/cues.json)
  python scripts/generate_sfx.py --project-dir ./my-short --render   # + audio/stem_sfx.wav and audio/mix.wav

Inputs in --project-dir: voice/words.json (word timings from generate_voice.py) and voice/voice.wav; SCRIPT.md is
optional (its text picks the ambience beds when present). An optional audio/music.wav is mixed in at the standard
+3 dB music level and ducked 3 dB under speech.
How it works: every word is matched against a vocabulary of actions (snap, crash, splash, hit, whoosh, creak, chain,
march, cheer, gasp, laugh, bubble, bell...). A match places one procedural sound from templates/audio/sfx_gen.py at that
word (0-3 frames early), at most one event every --min-gap seconds. Ambience beds (night, water, town, nature, wind)
come from the setting words of the whole script and run under the full length.
Standard mix: SFX events -6 dB under the voice, beds about -28 LU under it, voice unchanged; master -15 LUFS integrated,
true peak <= -1.2 dBTP, 48 kHz stereo. Needs numpy + scipy + soundfile (the Chatterbox Python has them)."""
import argparse, json, os, re, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, '..', 'templates', 'audio')
sys.path.insert(0, AUDIO)
import sfx_gen as G  # noqa: E402
from dsp import SR, rng, integrated, momentary_max, true_peak, lp  # noqa: E402

SFX_DB, BED_LU, MUSIC_LU, DUCK_DB = -6.0, -28.0, -10.0, -3.0
LEAD = 2 / 30            # sounds land up to 2 frames before the word

# (regex on the word, name, description, generator(r) -> mono or (2, n), naive level in LU vs the voice)
EVENTS = [
    (r'snap|snapped|broke|break|breaks|bolt|crack(ed|s)?', 'snap', 'metal/wood snap', lambda r: G.bolt_snap(r), -2),
    (r'crash|crashed|collaps\w*|smash\w*|destroy\w*|fell|falls?|drop(ped|s)?', 'crash', 'timber crash', lambda r: np.concatenate([G.wood_crack(r), G.timber_tear(r) * 0.7]), 0),
    (r'splash\w*|plunge\w*|dive|dived|sank|sink', 'splash', 'big splash', lambda r: G.splash_big(r), -1),
    (r'hit|hits|punch\w*|knock\w*|hammer\w*|bang\w*|slam\w*|thud|smack\w*', 'hit', 'heavy hit', lambda r: G.hammer_hit(r, 1.0), -3),
    (r'push\w*|shove\w*|bump\w*', 'push', 'soft thump', lambda r: G.push_thump(r), -6),
    (r'fly|flew|flying|throw\w*|threw|swung|swing\w*|jump\w*|launch\w*|zoom\w*|rush\w*|whoosh', 'whoosh', 'air whoosh', lambda r: G.whoosh(0.55, r), -5),
    (r'creak\w*|groan\w*|bend\w*|bent|sway\w*|wobbl\w*|shak\w*|bounc\w*|vibrat\w*', 'creak', 'wood/metal creak', lambda r: G.creak(1.0, r), -6),
    (r'chain\w*|cable\w*|rope\w*', 'chain', 'chain groan', lambda r: G.chain_groan(1.2, r), -6),
    (r'march\w*|stomp\w*|step\w*|walk\w*|boots?|soldiers?', 'steps', 'footsteps', lambda r: _steps(r), -8),
    (r'cheer\w*|crowd\w*|applau\w*|hooray|hurrah|celebrat\w*', 'cheer', 'crowd applause', lambda r: G.applause(2.0, r), -4),
    (r'gasp\w*|whoa|wow|shock\w*|surpris\w*', 'whoa', 'crowd whoa', lambda r: G.whoa(r), -8),
    (r'ouch|oof|hurt\w*|injur\w*|land(ed|s)?', 'oof', 'oof', lambda r: G.oof(r), -6),
    (r'bubbl\w*|underwater|drown\w*', 'bubbles', 'bubbles', lambda r: G.bubbles(1.0, r, 20), -8),
    (r'bell\w*|coin\w*|glass\w*|clink\w*|key|keys|metal', 'clink', 'small clink', lambda r: G.clink(r), -8),
    (r'squeak\w*|swing', 'squeak', 'swing squeak', lambda r: G.swing_squeak(r), -8),
]
# setting words -> ambience bed generator(dur, r)
BEDS = [
    (r'\b(night|dark|midnight|moon|stars?)\b', 'night', 'crickets + soft wind', lambda d, r: _mix(G.crickets(d, r) * 0.6, G.breeze(d, r, 0.6))),
    (r'\b(river|sea|ocean|lake|water|beach|waves?|bay|harbou?r)\b', 'water', 'water bed', lambda d, r: G.water_bed(d, r, 0.8, 0.7)),
    (r'\b(town|city|street|market|crowd|square|station)\b', 'town', 'distant town babble', lambda d, r: _mix(G.babble(d, r, 150, 1.0) * 0.25, G.breeze(d, r, 0.5))),
    (r'\b(forest|woods|park|garden|field|farm|village|trees?)\b', 'nature', 'birds + breeze', lambda d, r: _mix(G.bird_chirps(d, r, 0.45) * 0.1, G.breeze(d, r, 0.8))),
]


def _st(x):
    x = np.asarray(x, dtype=np.float64)
    return np.vstack([x, x]) if x.ndim == 1 else x


def _mix(*xs):
    xs = [_st(x) for x in xs]; n = max(x.shape[1] for x in xs); out = np.zeros((2, n))
    for x in xs: out[:, :x.shape[1]] += x
    return out


def _steps(r):
    out = np.zeros(int(1.6 * SR))
    for k in range(4):
        b = G.boot(r, 0.8); i = int(k * 0.42 * SR); out[i:i + len(b)] += b[:len(out) - i]
    return out


def gain_to(x, target_lufs, momentary=True):
    st = _st(x)
    cur = momentary_max(st) if momentary else integrated(st)
    if not np.isfinite(cur): return x
    return _st(x) * 10 ** ((target_lufs - cur) / 20)


def limiter(x, ceil_db):
    peak = 10 ** (ceil_db / 20); m = np.max(np.abs(x)) or 1.0
    if m <= peak: return x
    over = np.maximum(np.abs(x).max(axis=0) / peak, 1.0)
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    g = 1 / uniform_filter1d(maximum_filter1d(over, int(0.005 * SR)), int(0.005 * SR))
    return x * g


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--project-dir', required=True); ap.add_argument('--render', action='store_true')
    ap.add_argument('--min-gap', type=float, default=1.2, help='minimum seconds between two events')
    ap.add_argument('--seed', type=int, default=7)
    a = ap.parse_args()
    P = os.path.abspath(os.path.expanduser(a.project_dir)); out = os.path.join(P, 'audio'); os.makedirs(out, exist_ok=True)
    wj = os.path.join(P, 'voice', 'words.json')
    if not os.path.exists(wj): sys.exit(f'missing {wj}: run generate_voice.py first')
    words = json.load(open(wj))
    script = open(os.path.join(P, 'SCRIPT.md'), encoding='utf-8').read() if os.path.exists(os.path.join(P, 'SCRIPT.md')) else ' '.join(w['w'] for w in words)
    vpath = os.path.join(P, 'voice', 'voice.wav')
    import soundfile as sf
    voice, vsr = sf.read(vpath, dtype='float64') if os.path.exists(vpath) else (None, SR)
    if voice is not None and vsr != SR: sys.exit(f'voice.wav must be {SR} Hz')
    dur = (len(voice) / SR if voice is not None else words[-1]['e']) + 1.0

    cues, last = [], -99.0
    for w in words:
        tok = re.sub(r"[^a-z']", '', w['w'].lower())
        for rx, name, desc, gen, naive in EVENTS:
            if re.fullmatch(rx, tok) and w['s'] - last >= a.min_gap:
                cues.append({'t': round(max(0.0, w['s'] - LEAD), 3), 'word': w['w'], 'name': name, 'desc': desc, 'naive': naive, 'kind': 'event'})
                last = w['s']; break
    low = script.lower()
    beds = [{'t': 0.0, 'name': n, 'desc': d, 'kind': 'bed', 'naive': BED_LU} for rx, n, d, _ in BEDS if re.search(rx, low)]
    if not beds: beds = [{'t': 0.0, 'name': 'air', 'desc': 'soft outdoor air', 'kind': 'bed', 'naive': BED_LU}]
    allc = beds + cues
    json.dump(allc, open(os.path.join(out, 'cues.json'), 'w'), indent=1)
    md = ['# SFX cues (generated by scripts/generate_sfx.py)', '', f'Length {dur:.2f} s. Beds run under the whole video; events land on their word.', '',
          '| time | kind | sound | word | level vs voice |', '|---|---|---|---|---|']
    md += [f"| {c['t']:.2f} s | {c['kind']} | {c['desc']} | {c.get('word', '-')} | {c['naive'] + (SFX_DB if c['kind'] == 'event' else 0):+.0f} LU |" for c in allc]
    open(os.path.join(out, 'cues.md'), 'w').write('\n'.join(md) + '\n')
    summary = {'cues': len(cues), 'beds': [b['name'] for b in beds], 'cues_md': os.path.join(out, 'cues.md')}

    if a.render:
        n = int(dur * SR); sfx = np.zeros((2, n))
        vl = integrated(np.vstack([voice, voice])) if voice is not None else -20.0
        R = rng(a.seed)
        for c in allc:
            r = rng(int(R.integers(1 << 30)))
            if c['kind'] == 'bed':
                gen = next((g for rx, nm, d, g in BEDS if nm == c['name']), lambda d, r: G.breeze(d, r, 0.6))
                x = gain_to(gen(dur, r), vl + c['naive'], momentary=False)
            else:
                gen = next(g for rx, nm, d, g, nv in EVENTS if nm == c['name'])
                x = gain_to(gen(r), vl + c['naive'] + SFX_DB)
            i = int(c['t'] * SR); m = min(x.shape[1], n - i)
            if m > 0: sfx[:, i:i + m] += x[:, :m]
        mix = sfx.copy()
        if voice is not None: mix[:, :len(voice)] += voice
        mpath = os.path.join(out, 'music.wav')
        if os.path.exists(mpath):
            mu, msr = sf.read(mpath, dtype='float64', always_2d=True); mu = _st(mu.T)[:, :n]
            mu = gain_to(mu, vl + MUSIC_LU + 3.0, momentary=False)
            env = np.ones(n)
            for w in words: env[int(w['s'] * SR):int(w['e'] * SR)] = 10 ** (DUCK_DB / 20)
            from scipy.ndimage import uniform_filter1d
            env = uniform_filter1d(env, int(0.15 * SR)); mix[:, :mu.shape[1]] += mu * env[:mu.shape[1]]
            summary['music'] = mpath
        mix *= 10 ** ((-15.0 - integrated(mix)) / 20)
        mix = limiter(mix, -1.4)
        sf.write(os.path.join(out, 'stem_sfx.wav'), sfx.T, SR, subtype='PCM_24')
        sf.write(os.path.join(out, 'mix.wav'), mix.T, SR, subtype='PCM_24')
        summary.update(mix=os.path.join(out, 'mix.wav'), lufs=round(float(integrated(mix)), 2), true_peak_dbtp=round(float(true_peak(mix)), 2))
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
