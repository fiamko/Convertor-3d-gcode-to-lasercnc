"""PCB isolation milling. Surface Z=0; no height-map compensation here."""
import math
import re
from nc_core import NCError, fmt, positive, parse_nc, test_pattern


def validate(feed, depth, safe, plunge, rpm, delay):
    for value, title in ((feed,'Posuv XY'),(depth,'Ponor'),(safe,'Výška přejezdu'),
                         (plunge,'Posuv Z'),(rpm,'Otáčky')):
        positive(value,title)
    positive(delay,'Rozběh vřetena',zero=True)
    if depth < .0001 or safe < .0001:
        raise NCError('Ponor a výška přejezdu musí být alespoň 0,0001 mm.')


def export_mill(drawing, feed, depth, safe, plunge, rpm, delay=0,
                mirror_x=False, mirror_y=False, rotation=0, per_stroke=False, mark_drills=False, drill_extra=0):
    validate(feed,depth,safe,plunge,rpm,delay)
    positive(drill_extra,'Přídavek ponoru značek',zero=True)
    if rotation not in (0,90,180,270): raise NCError('Neplatné otočení.')
    bounds=drawing.reference_bounds or drawing.bounds()
    def transform(p):
        x=bounds[0]+bounds[2]-p[0] if mirror_x else p[0]
        y=bounds[1]+bounds[3]-p[1] if mirror_y else p[1]
        if rotation:
            x,y=x-bounds[0],y-bounds[1]
            w,h=bounds[2]-bounds[0],bounds[3]-bounds[1]
            if rotation==90: x,y=h-y,x
            elif rotation==180: x,y=w-x,h-y
            else: x,y=y,w-x
            x,y=x+bounds[0],y+bounds[1]
        if not all(math.isfinite(v) for v in (x,y)): raise NCError('Neplatná souřadnice.')
        return x,y
    out=['(CNC PCB - povrch Z0; bez vyskove kompenzace)',
         '(Ponor kladny v nastaveni, zaporne Z ve vystupu)',
         'G21','G90','G17','G94','M5',f'G0 Z{fmt(safe)}']
    running=False; count=0
    def start():
        nonlocal running
        if not running:
            out.append(f'M3 S{fmt(rpm)}')
            if delay: out.append(f'G4 P{fmt(delay)}')
            running=True
    def pause(commands):
        nonlocal running
        if running: out.append('M5'); running=False
        out.extend(commands)
    for index,stroke in enumerate(drawing.strokes):
        if index in drawing.pauses: pause(drawing.pauses[index])
        # Rebuild necessary travel only. Every preceding cut ends above the board.
        if not stroke.burn or len(stroke.points)<2: continue
        d=stroke.power if per_stroke else depth
        f=stroke.feed if per_stroke else feed
        validate(f,d,safe,plunge,rpm,delay)
        pts=[transform(p) for p in stroke.points]
        start()
        out.extend([f'G0 X{fmt(pts[0][0])} Y{fmt(pts[0][1])}',
                    f'G1 Z{fmt(-d)} F{fmt(plunge)}',f'G1 F{fmt(f)}'])
        out.extend(f'G1 X{fmt(x)} Y{fmt(y)}' for x,y in pts[1:])
        out.append(f'G0 Z{fmt(safe)}'); count+=1
    if len(drawing.strokes) in drawing.pauses: pause(drawing.pauses[len(drawing.strokes)])
    if mark_drills:
        seen=set()
        for point in drawing.drill_points:
            x,y=transform(point)
            key=(fmt(x),fmt(y))
            if key in seen: continue
            seen.add(key); start()
            out.extend(['(Znackovaci vpich)', f'G0 X{key[0]} Y{key[1]}',
                        f'G1 Z{fmt(-(depth+drill_extra))} F{fmt(plunge)}',f'G0 Z{fmt(safe)}'])
            count+=1
    if not count: raise NCError('Není co frézovat: chybí pracovní dráhy nebo povolené značkovací vpichy.')
    if running: out.append('M5')
    return '\n'.join(out+['M2',''])


def preview_mill(text):
    # Dwell has no geometry. Original laser parser is intentionally unchanged.
    clean='\n'.join('' if re.fullmatch(r'\s*G0?4\s+P[+\d.]+\s*',line,re.I) else line for line in text.splitlines())
    return parse_nc(clean,'z',0)


def milling_test(x,y,width,height,columns,rows,gap,spacing,
                 depth_min,depth_max,feed_min,feed_max,safe,plunge,rpm,delay=0,
                 trace_widths=None,trace_pass_mode=None,border_count=0,border_width=.2,compare_widths=False,column_gap=.5):
    if type(columns) is not int or type(rows) is not int:
        raise NCError('Počty polí musí být celá čísla.')
    validate(feed_min,depth_min,safe,plunge,rpm,delay)
    validate(feed_max,depth_max,safe,plunge,rpm,delay)
    # Reuse the proven geometry, with temporary S encoding depth, never emit laser code.
    geometry,_=test_pattern(x,y,width,height,columns,rows,gap,spacing,
        depth_min,depth_max,feed_min,feed_max,trace_widths=trace_widths,
        trace_pass_mode=trace_pass_mode,border_count=border_count,border_width=border_width,
        negative=compare_widths,negative_gap=column_gap)
    drawing=parse_nc(geometry,'spindle')
    legend=[]
    for r in range(rows):
        f=feed_min+(feed_max-feed_min)*r/max(1,rows-1)
        for c in range(columns):
            d=depth_min+(depth_max-depth_min)*c/max(1,columns-1)
            legend.append(f'R{r+1} C{c+1}: ponor {fmt(d)} mm / F{fmt(f)}')
    header=['(Test CNC: sloupce zleva ponor / radky zdola posuv)',
            f'(XY plocha: X{fmt(x)} Y{fmt(y)} / {fmt(width)} x {fmt(height)} mm)',
            f'(Otacky S{fmt(rpm)} / Z posuv {fmt(plunge)} / prejezd Z{fmt(safe)})',
            '(Sirka stopy je nominalni; skutecna zavisi na hrotu a hloubce.)']
    # Keep the laser generator's full geometry specification, including widths,
    # repetitions, offsets, overlap and frames, translated to milling terminology.
    notes=geometry.splitlines()[1:]
    for note in notes:
        if note.startswith('(R1 C1:'): break
        note=note.replace('Negativni rezist: laser osvituje budouci med.',
                          'Porovnani 1:1: freza odebere obdelnik W; mezi nimi zustava med W.')
        note=note.replace('S/F','ponor/F')
        header.append(note)
    return '\n'.join(header+[f'({s})' for s in legend])+'\n'+export_mill(
        drawing,feed_min,depth_min,safe,plunge,rpm,delay,per_stroke=True),legend


def milling_seconds(text, rapid):
    """Ideal XYZ time for generated absolute G0/G1 code, excluding unknown approach."""
    positive(rapid,'Rychlost G0')
    pos={}; motion=0; feed=None; seconds=0
    for line in text.splitlines():
        line=re.sub(r'\([^)]*\)','',line).split(';')[0]
        words={k:float(v) for k,v in re.findall(r'([A-Z])([+-]?(?:\d+\.?\d*|\.\d+))',line.upper())}
        g=words.get('G')
        if g==4: seconds+=words.get('P',0); continue
        if g in (0,1): motion=int(g)
        if 'F' in words: feed=words['F']
        axes=[a for a in 'XYZ' if a in words]
        if axes:
            if all(a in pos for a in axes):
                distance=math.sqrt(sum((words[a]-pos[a])**2 for a in axes))
                rate=rapid if motion==0 else feed
                if rate is None or rate<=0: raise NCError('Neznámý posuv.')
                seconds+=60*distance/rate
            pos.update({a:words[a] for a in axes})
    return seconds
