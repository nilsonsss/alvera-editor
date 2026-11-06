# ONE-TIME migration (already run; v5 is deleted, do not re-run): built performance + brand EDLs from the v5 edl: retimes everything around the two VO cuts
# (removed "even the same movements" and "luxury"), then applies each version's look.
import json, copy, os
E = os.path.expanduser('~/Documents/claude-alvera/video-editor/edits')
P = f'{E}/2026-10-31_alvera_logotax-performance'; B = f'{E}/2026-10-31_alvera_logotax-brand'
C = f'{P}/elements/clips/'
v5 = json.load(open(f'{P}/edl.json'))
# timeline cuts (VO time + 0.5): [start, end, removed seconds incl. crossfade]
CUTS = [(9.36, 10.30, 0.955), (18.44, 18.97, 0.545)]
def R(t):
    s = 0
    for a, b, d in CUTS:
        if t <= a: break
        if t < b: return round(a - s, 3)
        s += d
    return round(t - s, 3)
# sound peaks (s after file start) so hits stay locked to their cut
PEAK = {'Hint of Metal': .32, 'Grand Hit B': .56, 'Universe Boom A': 1.02, 'rm whoosh': .69, 'wind-swoosh-1471': .43,
        'swoosh-1468': .30, 'Short Whoosh': .47, 'BUILD-UP': 1.63, 'whoosh-6316': .09, 'cash ting': .24, 'space-impact': .06,
        'metal-hit-woosh': .09, 'glass-hit': .06, 'Subsonic A': .11, 'metal-click': .04, 'gun-click': .04, 'rm click': .04}
def base():
    e = copy.deepcopy(v5)
    e['vo'] = f'{P}/vo_cut.wav'
    for s in e['segments']:
        s['at'], s['end'] = R(s['at']), R(s['end'])
        s['src'] = C + os.path.basename(s['src'])
    e['segments'] = [s for s in e['segments'] if s['end'] - s['at'] > 0.2]
    for x in e['text']:
        x['at'], x['end'] = R(x['at']), R(x['end'])
    for x in e['sfx']:
        name = os.path.basename(x['path']); pk = next((v for k, v in PEAK.items() if k in name), None)
        if 'BUILD-UP' in name:  # riser peaks on the cut to black
            black = [s for s in e['segments'] if s['src'].endswith('black.mp4')][0]['at']
            x['at'] = round(black - 1.63, 3)
        elif pk is not None:
            x['at'] = round(R(x['at'] + pk) - pk, 3)
        else:  # beds: keep start and end on the timeline
            end = R(x['at'] + x['len']); x['at'] = R(x['at']); x['len'] = round(end - x['at'], 3)
    return e
def common(e, version):
    seg = {os.path.basename(s['src']).split('.')[0]: s for s in e['segments']}
    for k in ('06', '08'):
        seg[k]['src'] = C + f'{k}r.mp4'; seg[k]['why'] += ' · rotated 180° so ALVERA on the dial is not upside down'
    e['caption_style'] = {**e.get('caption_style', {}), 'replace': {'five to ten grand?': '5-10K?', 'height': 'hype'}}
    # labels bigger, IBM Plex Mono per brand book
    e['fonts']['Label'] = ['IBM Plex Mono Medium', 58]
    # hook from frame 1
    end_text = [x for x in e['text'] if x['text'] in ('Find your direction.', 'NO.1 — $360', 'ALVERAWATCHES.COM')]
    e['text'] = [x for x in e['text'] if x not in end_text]
    last = e['segments'][-1]['at']
    e['text'] += [
        {'at': 0.0, 'end': 2.45, 'style': 'Big', 'text': "What you're really\\Npaying for.", 'pos': [540, 470], 'keep_captions': True},
        {'at': last + 1.0, 'end': e['segments'][-1]['end'], 'style': 'Big', 'text': 'Find your direction.', 'pos': [540, 1450]},
        {'at': last + 1.5, 'end': e['segments'][-1]['end'], 'style': 'Label', 'text': '{\\fs76\\fsp10}SHOP — $360', 'pos': [540, 1560]},
        {'at': last + 1.7, 'end': e['segments'][-1]['end'], 'style': 'Label', 'text': '{\\fs40}ALVERAWATCHES.COM', 'pos': [540, 1680]}]
    e['name'] = f'ALVERA No.1 — logo tax — {version}'
    return e

# ---- performance: the loud v5 look + fixes
p = common(base(), 'performance')
seg = {os.path.basename(s['src']).split('.')[0]: s for s in p['segments']}
seg['02_fx']['src'] = C + '02r_fx.mp4'
X = [x for x in p['text'] if x.get('keep_captions') and '\\p1' in x['text']][0]; X['pos'] = [540, 990]
json.dump(p, open(f'{P}/edl.json', 'w'), indent=1, ensure_ascii=False)

# ---- brand: the brand book (Helvetica + Plex Mono, Ink/Paper only, quiet motion)
b = common(base(), 'brand')
seg = {os.path.basename(s['src']).split('.')[0]: s for s in b['segments']}
seg['01b_fx']['src'] = C + '01b.mp4'; seg['02_fx']['src'] = C + '02r.mp4'
b['fonts'] = {'Cap': ['Helvetica Neue Medium', 80], 'Big': ['Helvetica Neue Medium', 104],
              'Label': ['IBM Plex Mono Medium', 58], 'Pop': ['Helvetica Neue Medium', 190]}
b['caption_style'] = {'replace': b['caption_style']['replace']}   # sentence case, one colour
b.pop('ass_raw', None)                                              # no flying $
for x in b['text']:
    if x['style'] == 'Pop':
        x.pop('color', None); x['quiet'] = True
        if '\\p1' in x['text']:  # thinner white ✕
            x['text'] = "{\\frz45\\p1}m 156 0 l 184 0 l 184 156 l 340 156 l 340 184 l 184 184 l 184 340 l 156 340 l 156 184 l 0 184 l 0 156 l 156 156{\\p0}"
            x['pos'] = [540, 990]
b['sfx'] = [x for x in b['sfx'] if not any(k in x['path'] for k in ('cash ting', 'metal-hit-woosh-1485.wav'))
            or ('metal-hit-woosh' in x['path'] and x['at'] < 0.1)]
for x in b['sfx']:
    if 'space-impact' in x['path']: x['volume_db'] = -13
json.dump(b, open(f'{B}/edl.json', 'w'), indent=1, ensure_ascii=False)
for e in (p, b):
    print(e['name'], 'total', e['segments'][-1]['end'], len(e['segments']), 'segs', len(e['sfx']), 'sfx')
