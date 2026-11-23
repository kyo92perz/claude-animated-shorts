# Narração pt-BR do curta: sintetiza cada bloco com Piper (modelo pt_BR-castor-v3), encaixa cada bloco no seu slot
# (só aceleração suave via atempo, no máximo 18%, sem mudar o tom), monta voice/voice.wav (48 kHz estéreo) e um
# words.json aproximado (tempo proporcional por fonema) — o mesmo contrato que mix.py espera.
# Roda: python3 scripts/voice_pt.py
import json, os, subprocess, tempfile, wave
import numpy as np
from piper import PiperVoice

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VOICE = os.path.join(ROOT, "voice")
MODEL = "/tmp/piper_models/pt_BR-castor-v3.onnx"
SR_OUT = 48000
FFMPEG = "ffmpeg"
DUR = 2025 / 30.0
MAX_SPEED = 1.18  # atempo máximo aceitável (18% mais rápido)

# (id, texto, início do slot, fim do slot) — slots casados com os cortes de story.ts
BLOCKS = [
    ("01", "Setenta e quatro soldados derrubaram uma ponte de ferro só caminhando sobre ela.", 0.20, 4.40),
    ("02", "É mil oitocentos e trinta e um, e a ponte novinha é o orgulho da cidade inteira.", 4.60, 9.20),
    ("03", "Os homens marcham de quatro em quatro, cada bota batendo na tábua no mesmo instante.", 9.40, 14.40),
    ("04", "No meio do caminho, a ponte começa a balançar sob os pés deles.", 14.80, 18.20),
    ("05", "Uma pessoa normal diminuiria o passo, mas eles acham a maior graça.", 18.30, 21.75),
    ("06", "Alguém assobia uma marcha, e a coluna inteira pisa no ritmo, cada vez mais forte.", 21.80, 26.00),
    ("07", "O balanço aumenta, as correntes gemem, e ninguém quer quebrar o passo.", 27.50, 31.20),
    ("08", "Um único parafuso estala, e a ponta da ponte cai no rio.", 32.00, 36.20),
    ("09", "Por sorte, o rio tinha só sessenta centímetros.", 37.80, 40.55),
    ("10", "Azar: o rio tinha só sessenta centímetros.", 40.75, 43.40),
    ("11", "Toda ponte tem um ritmo natural de balanço.", 43.60, 46.10),
    ("12", "Já empurrou uma criança no balanço? Cada empurrão é pequeno, mas se chegam na hora certa, o balanço sobe cada vez mais.", 46.30, 52.60),
    ("13", "Setenta e quatro homens pisando juntos empurravam aquela ponte assim.", 54.10, 57.75),
    ("14", "Ninguém morreu, mas criaram uma regra: nunca atravessar ponte em passo de marcha.", 57.95, 62.20),
    ("15", "Hoje os soldados mais disciplinados do mundo cruzam cada ponte como turistas.", 62.40, 66.60),
]


def synth(voice, text):
    chunks = list(voice.synthesize(text))
    audio = np.concatenate([c.audio_float_array.astype(np.float64) for c in chunks])
    return audio, chunks[0].sample_rate, chunks


def fit(x, sr, max_sec):
    """acelera até max_sec se preciso (atempo, teto MAX_SPEED) e reamostra para 48 kHz. Retorna (audio48k, factor)."""
    dur = len(x) / sr
    tempo = 1.0
    if dur > max_sec:
        tempo = min(MAX_SPEED, dur / max(max_sec, 0.05))
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "in.wav"), os.path.join(d, "out.wav")
        with wave.open(a, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
        chain = []
        t = tempo
        while t > 2.0:
            chain.append("atempo=2.0"); t /= 2.0
        if abs(t - 1.0) > 0.005:
            chain.append(f"atempo={t:.6f}")
        chain.append(f"aresample={SR_OUT}")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", a, "-af", ",".join(chain), b], check=True)
        with wave.open(b, "rb") as w:
            raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, "<i2").astype(np.float64) / 32768.0, tempo


def main():
    os.makedirs(VOICE, exist_ok=True)
    voice = PiperVoice.load(MODEL, MODEL + ".json")
    N = int(round(DUR * SR_OUT))
    out = np.zeros(N)
    words, report = [], []
    for bid, text, t0, t1 in BLOCKS:
        audio, sr, chunks = synth(voice, text)
        natural = len(audio) / sr
        x, tempo = fit(audio, sr, t1 - t0)
        start = int(round(t0 * SR_OUT))
        end = min(N, start + len(x))
        out[start:end] += x[: end - start]
        span = (end - start) / SR_OUT
        ph = chunks[0].phonemes
        groups, cur = [], []
        for p in ph:
            if p == " ":
                if cur: groups.append(cur); cur = []
            else:
                cur.append(p)
        if cur: groups.append(cur)
        total = sum(len(g) for g in groups) or 1
        acc = 0
        for g in groups:
            s = t0 + span * acc / total
            acc += len(g)
            words.append({"w": "".join(g), "s": round(s, 3), "e": round(t0 + span * acc / total, 3)})
        report.append((bid, round(natural, 2), round(spam := span, 2), round(tempo, 3), "OK" if span <= (t1 - t0) + 0.02 else "ESTOUROU"))
        print(f"[voz] {bid}: natural {natural:.2f}s -> {t0:.2f}-{t0+span:.2f}s (tempo {tempo:.3f}) {'ok' if span <= (t1-t0)+0.02 else 'ESTOUROU'}", flush=True)

    out = out / max(np.abs(out).max(), 1e-9) * 0.7
    stereo = np.stack([out, out])
    with wave.open(os.path.join(VOICE, "voice.wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR_OUT)
        w.writeframes((np.clip(stereo.T, -1, 1) * 32767).astype("<i2").tobytes())
    json.dump(words, open(os.path.join(VOICE, "words.json"), "w"), ensure_ascii=False)
    bad = [r for r in report if r[4] != "OK"]
    print(f"voice.wav 48 kHz, {len(words)} palavras, blocos com estouro: {bad if bad else 'nenhum'}")


if __name__ == "__main__":
    main()
