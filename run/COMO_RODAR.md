# Como rodar este repositório (runner do template "bridge")

O repositório é uma *skill* (documentos + código-fonte de exemplo), não um app. Para executá-lo eu montei aqui
`run/`: um projeto Remotion mínimo em volta de `templates/bridge/` + os scripts de áudio de `templates/audio/`,
já funcionando neste ambiente.

## O que foi feito

| Item | Estado |
|---|---|
| Projeto Remotion (`run/package.json`, `src/index.ts`, `src/Root.tsx`, `tsconfig.json`) | criado; composição `BridgeShort` 1080x1920, 30 fps, 2025 frames (67,5 s) |
| Código do curta (`run/src/videos/bridge/*` = `templates/bridge/*`) | compila (`npx tsc --noEmit`, só queixas de tipo do `EffectComposer` no original) |
| Assets Kenney CC0 (`run/public/bridge/kenney/*.glb` + `Textures/colormap.png`) | baixados do espelho `shorepine/kenney` (26 props, 468 KB) |
| Navegador headless | o sandbox não tem Chrome e não alcança o CDN da Remotion; compilei NSS/NSPR e usei o Chromium do `@sparticuz/chromium` |
| Still renders | 15 frames (um por cena) renderizados a `--scale 0.5` — `run/out/stills/`, contatos em `run/deliver/contato_15_cenas.jpg` |
| Áudio | narração pt-BR (Piper, voz `pt_BR-castor-v3`, local) + trilha/SFX sintetizados por `mix.py` → `run/audio/mix.wav` (−15,0 LUFS, −1,2 dBTP, 67,500 s) |
| Vídeo final | **não renderizado**: SwiftShader em 2 núcleos leva ~75 s por frame (≈42 h para 2025 frames) |

## Comandos

```bash
# dependências
cd run && npm install

# stills (precisa de um Chromium; aqui usei /tmp/chromium)
export LD_LIBRARY_PATH=/tmp/nssext:/tmp/nssdist/lib
export BROWSER_EXECUTABLE=/tmp/chromium
node scripts/stills.mjs out/stills/x_ 100,400 0.5

# voz pt-BR + words.json
PATH=/tmp:$PATH python3 scripts/voice_pt.py

# trilha (67,5 s, 48 kHz), stems e cues
cd audio && python3 mix.py          # precisa de `ffmpeg` no PATH

# render final (numa máquina com GPU; ~2 min no PC do autor do template)
npx remotion render src/index.ts BridgeShort out/bridge.mp4 --codec h264 --crf 16 --scale 1.3333
ffmpeg -i out/bridge.mp4 -i audio/mix.wav -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 320k out/bridge_final.mp4
```

## Conteúdo em português

- Roteiro adaptado: `run/SCRIPT_ptBR.md` (15 blocos, mesmos fatos de 1831, mesma timeline).
- Narração: 15 blocos sintetizados, cada um encaixado no seu slot (no máximo 18 % mais rápido, sem mudar o tom).
- Mix: música +3 dB relativa à voz, SFX −6 dB, sem legendas e sem citar canal de referência (regras da skill).
