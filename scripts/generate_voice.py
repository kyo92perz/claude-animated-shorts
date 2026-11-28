#!/usr/bin/env python3
"""Narration for a cartoon-3d-short: Chatterbox (Resemble AI, MIT) -> voice.wav (48 kHz mono) + words.json.

  python scripts/generate_voice.py --out-dir ~/my-short/voice --text "Wait, you thought that would work? [chuckle] That is ridiculous."
  python scripts/generate_voice.py --out-dir ~/my-short/voice --script SCRIPT.md
  python scripts/generate_voice.py --out-dir voice --script SCRIPT.md --engine multilingual --exaggeration 0.35

Engines: `turbo` (default; Chatterbox-Turbo, understands [chuckle] [laugh] [sigh] [gasp] [cough] and similar tags, ignores
--exaggeration) and `multilingual` (Chatterbox Multilingual, --exaggeration 0.25 deadpan .. 0.35 natural .. 0.65 theatrical,
tags are removed). Voice: --ref <wav> (6-15 s of clean speech from a voice you own or are licensed to clone); default
templates/audio/voices/mark.wav when that file exists, otherwise the engine's built-in voice.
SCRIPT.md: the narration is every non-empty line after the first blank line that follows the facts block (the
template format); --lines-from-start reads every non-empty line. Each line becomes one take; takes are joined with
--gap seconds of silence. Runs on CUDA when available (float16 alignment), else CPU.
words.json: [{"w": "soldiers", "s": 0.42, "e": 0.88}, ...] from faster-whisper word timestamps (this Python, or the
Python in $WHISPER_PY when this one lacks faster-whisper). Status goes to stderr; a JSON summary to stdout."""
import argparse, json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_REF = os.path.join(ROOT, 'templates', 'audio', 'voices', 'mark.wav')
TAG = re.compile(r'\[(chuckle|laugh|sigh|gasp|cough|groan|pause|clear throat|sniff|shush)\]', re.I)
SR = 48000


def log(*a): print(*a, file=sys.stderr, flush=True)


def script_lines(path, from_start):
    lines = [l.rstrip() for l in open(path, encoding='utf-8')]
    if not from_start:
        start = next((i for i, l in enumerate(lines) if l.strip() == ''), -1) + 1
        lines = lines[start:]
    return [l.strip() for l in lines if l.strip() and not l.startswith('#')]


def device():
    import torch
    return 'cuda' if torch.cuda.is_available() else ('mps' if getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available() else 'cpu')


def synth(lines, engine, ref, exaggeration, cfg, dev):
    import numpy as np, torch, torchaudio.functional as AF
    if engine == 'turbo':
        from chatterbox.tts_turbo import ChatterboxTurboTTS as M
        model = M.from_pretrained(device=dev)
    else:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS as M
        model = M.from_pretrained(device=torch.device(dev))
    takes = []
    for i, text in enumerate(lines):
        say = text if engine == 'turbo' else TAG.sub('', text).replace('  ', ' ').strip()
        log(f'  take {i + 1}/{len(lines)}: {say[:70]}')
        kw = {'audio_prompt_path': ref} if ref else {}
        if engine == 'turbo':
            wav = model.generate(say, **kw)
        else:
            wav = model.generate(say, language_id='en', exaggeration=exaggeration, cfg_weight=cfg, **kw)
        wav = AF.resample(wav.cpu().float(), model.sr, SR).squeeze(0).numpy()
        takes.append(wav)
    return takes


def align(wav_path, dev):
    code = f"""
import json, subprocess, sys
import numpy as np
from faster_whisper import WhisperModel
pcm = subprocess.run(['ffmpeg', '-v', 'error', '-i', sys.argv[1], '-ar', '16000', '-ac', '1', '-f', 'f32le', '-'], capture_output=True, check=True).stdout
audio = np.frombuffer(pcm, dtype=np.float32)
m = WhisperModel('small', device={'"cuda"' if dev == 'cuda' else '"cpu"'}, compute_type={'"float16"' if dev == 'cuda' else '"int8"'})
segs, _ = m.transcribe(audio, language='en', word_timestamps=True)
print(json.dumps([{{'w': w.word.strip(), 's': round(w.start, 3), 'e': round(w.end, 3)}} for s in segs for w in s.words]))
"""
    py = sys.executable
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        py = os.environ.get('WHISPER_PY') or sys.exit('words.json needs faster-whisper: install it here or set WHISPER_PY to a Python that has it')
    out = subprocess.run([py, '-c', code, wav_path], capture_output=True, text=True)
    if out.returncode: sys.exit('alignment failed:\n' + out.stderr[-1500:])
    out = out.stdout
    return json.loads(out.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out-dir', required=True)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--text'); src.add_argument('--script')
    ap.add_argument('--lines-from-start', action='store_true')
    ap.add_argument('--engine', choices=['turbo', 'multilingual'], default='turbo')
    ap.add_argument('--ref', help='reference voice wav (default: templates/audio/voices/mark.wav if present)')
    ap.add_argument('--exaggeration', type=float, default=0.35)
    ap.add_argument('--cfg', type=float, default=0.5)
    ap.add_argument('--gap', type=float, default=0.35, help='silence between script lines (s)')
    ap.add_argument('--no-words', action='store_true', help='skip words.json')
    a = ap.parse_args()

    import numpy as np, soundfile as sf
    out = os.path.expanduser(a.out_dir); os.makedirs(out, exist_ok=True)
    lines = [a.text] if a.text else script_lines(a.script, a.lines_from_start)
    if not lines: sys.exit('no narration lines found')
    ref = a.ref or (DEFAULT_REF if os.path.exists(DEFAULT_REF) else None)
    log(f'voice: {ref or "built-in " + a.engine + " voice (no reference wav found)"}')
    dev = device(); log(f'device: {dev}, engine: {a.engine}, {len(lines)} take(s)')
    takes = synth(lines, a.engine, ref, a.exaggeration, a.cfg, dev)
    gap = np.zeros(int(a.gap * SR), dtype=np.float32)
    audio = np.concatenate([x for t in takes for x in (t.astype(np.float32), gap)][:-1]) if takes else np.zeros(1, np.float32)
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = audio * min(1.0, 0.89 / peak)
    wav = os.path.join(out, 'voice.wav'); sf.write(wav, audio, SR, subtype='PCM_24')
    res = {'voice': wav, 'duration': round(len(audio) / SR, 3), 'takes': len(lines), 'engine': a.engine, 'ref': ref, 'device': dev}
    if not a.no_words:
        words = align(wav, dev); wj = os.path.join(out, 'words.json')
        json.dump(words, open(wj, 'w'), indent=1); res.update(words=wj, word_count=len(words))
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
