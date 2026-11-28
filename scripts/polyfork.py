#!/usr/bin/env python3
"""Polyfork catalog CLI (stdlib only): search, browse kits, download GLBs and print three.js snippets.
The catalog index lives in references/polyfork/catalog.json (refresh it with `update`). Models download from
https://polyfork.dev/cdn/<id>.glb (free for personal and commercial use, no attribution required; mesh files are
also CC BY 4.0; see https://polyfork.dev/licensing).

  python scripts/polyfork.py search "house" --kit medieval-village-kit-ca0b43
  python scripts/polyfork.py search "car" --type vehicle --max-triangles 1500 --limit 10
  python scripts/polyfork.py kits --search train          python scripts/polyfork.py kit countryside-railway-9b4c57
  python scripts/polyfork.py info a-frame-cabin-6cb550     python scripts/polyfork.py download a-frame-cabin-6cb550 --out-dir ./public/models
  python scripts/polyfork.py snippet a-frame-cabin-6cb550  python scripts/polyfork.py update
Status goes to stderr; --json prints machine-readable output to stdout."""
import argparse, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(HERE, '..', 'references', 'polyfork', 'catalog.json')
RAW = 'https://raw.githubusercontent.com/lucas-martinic/polyfork-catalog/main/catalog.json'


def load():
    if not os.path.exists(CATALOG):
        sys.exit(f'no catalog at {CATALOG}: run `python scripts/polyfork.py update` first')
    return json.load(open(CATALOG, encoding='utf-8'))


def fetch(url, out):
    req = urllib.request.Request(url, headers={'User-Agent': 'polyfork-cli/1.0'})
    with urllib.request.urlopen(req, timeout=60) as r, open(out + '.part', 'wb') as f:
        while True:
            b = r.read(1 << 16)
            if not b: break
            f.write(b)
    os.replace(out + '.part', out)


def find(cat, mid):
    for a in cat['assets']:
        if a['id'] == mid: return a
    sys.exit(f'unknown model id: {mid} (try `search`)')


def emit(rows, as_json, fmt):
    if as_json: print(json.dumps(rows, indent=1)); return
    for r in rows: print(fmt(r))
    print(f'{len(rows)} result(s)', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--json', action='store_true', help='machine-readable output')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('search'); s.add_argument('query', nargs='?', default=''); s.add_argument('--kit'); s.add_argument('--type')
    s.add_argument('--max-triangles', type=int); s.add_argument('--limit', type=int, default=25)
    k = sub.add_parser('kits'); k.add_argument('--search', default='')
    k1 = sub.add_parser('kit'); k1.add_argument('kit_id')
    i = sub.add_parser('info'); i.add_argument('id')
    d = sub.add_parser('download'); d.add_argument('ids', nargs='+'); d.add_argument('--out-dir', default='./public/models')
    sn = sub.add_parser('snippet'); sn.add_argument('id')
    sub.add_parser('types'); sub.add_parser('update')
    a = ap.parse_args()

    if a.cmd == 'update':
        os.makedirs(os.path.dirname(CATALOG), exist_ok=True); fetch(RAW, CATALOG)
        print(f"catalog updated: {load()['models']} models", file=sys.stderr); return
    cat = load()
    if a.cmd == 'search':
        words = a.query.lower().split()
        rows = [x for x in cat['assets'] if all(w in (x['title'] + ' ' + x['id'] + ' ' + x.get('type', '')).lower() for w in words)
                and (not a.kit or x.get('kit') == a.kit) and (not a.type or x.get('type') == a.type)
                and (not a.max_triangles or x.get('triangles', 0) <= a.max_triangles)][:a.limit]
        emit(rows, a.json, lambda x: f"{x['id']:<42} {x['title']:<32} {x.get('type',''):<12} {x.get('triangles','?'):>5} tris  kit={x.get('kit','')}")
    elif a.cmd == 'kits':
        rows = [x for x in cat['kits'] if a.search.lower() in (x['title'] + x['id']).lower()]
        emit(rows, a.json, lambda x: f"{x['id']:<42} {x['title']:<36} {x.get('parts','?'):>4} parts")
    elif a.cmd == 'kit':
        rows = [x for x in cat['assets'] if x.get('kit') == a.kit_id]
        emit(rows, a.json, lambda x: f"{x['id']:<42} {x['title']:<32} {x.get('type',''):<12} {x.get('triangles','?'):>5} tris")
    elif a.cmd == 'types':
        from collections import Counter
        c = Counter(x.get('type', '?') for x in cat['assets'])
        emit(sorted(c.items(), key=lambda t: -t[1]), a.json, lambda t: f'{t[0]:<20} {t[1]}')
    elif a.cmd == 'info':
        print(json.dumps(find(cat, a.id), indent=1))
    elif a.cmd == 'download':
        os.makedirs(a.out_dir, exist_ok=True); done = []
        for mid in a.ids:
            m = find(cat, mid); out = os.path.join(a.out_dir, mid + '.glb')
            if os.path.exists(out) and os.path.getsize(out) > 0:
                print(f'cached {out}', file=sys.stderr)
            else:
                print(f"downloading {m['title']} -> {out}", file=sys.stderr); fetch(m['glb'], out)
            done.append({'id': mid, 'path': out, 'bytes': os.path.getsize(out)})
        print(json.dumps(done, indent=1))
    elif a.cmd == 'snippet':
        m = find(cat, a.id)
        print(f"""// {m['title']} ({m.get('triangles','?')} tris) from Polyfork, {m['page']}
// file: public/models/{m['id']}.glb  (python scripts/polyfork.py download {m['id']} --out-dir ./public/models)
import {{ GLTFLoader }} from 'three/examples/jsm/loaders/GLTFLoader.js';
import {{ staticFile }} from 'remotion';
const gltf = await new GLTFLoader().loadAsync(staticFile('models/{m['id']}.glb'));
const model = gltf.scene;                       // Y-up, metres, centred at y = 0
model.position.set(0, 0, 0); model.scale.setScalar(1); model.rotation.y = 0;
scene.add(model);
// in the cartoon-3d-short templates: placePolyforkProp(batch, model, x, y, z, height, yaw) recolours it to two-tone shading""")


if __name__ == '__main__':
    main()
