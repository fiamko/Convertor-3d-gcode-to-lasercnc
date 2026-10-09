"""NC geometry and laser export. Millimetres internally; no machine connection."""
from dataclasses import dataclass, field
import math
import re


class NCError(ValueError):
    pass


@dataclass
class Stroke:
    points: list
    burn: bool
    feed: float = 0
    power: float = 0
    rapid: bool = True


@dataclass
class Drawing:
    strokes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    mode: str = ""
    pauses: dict = field(default_factory=dict)
    drill_points: list = field(default_factory=list)
    reference_bounds: tuple | None = None

    def bounds(self):
        pts = [p for s in self.strokes if s.burn for p in s.points]
        if not pts:
            pts = [p for s in self.strokes for p in s.points]
        if not pts:
            raise NCError("Soubor neobsahuje žádné zobrazitelné pohyby XY.")
        return (min(p[0] for p in pts), min(p[1] for p in pts),
                max(p[0] for p in pts), max(p[1] for p in pts))


WORD = re.compile(r"([A-Za-z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))")


def blocks(text):
    result, warnings = [], []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip().lstrip('\ufeff')
        # Known broken header in the supplied reference. Nothing else is repaired.
        if line == ': 0.0)':
            warnings.append(f"Řádek {number}: vynechán poškozený zbytek hlavičky ': 0.0)'.")
            continue
        clean, depth = [], 0
        for char in line:
            if char == ';' and depth == 0: break
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth < 0: raise NCError(f"Řádek {number}: nepárová závorka komentáře.")
            elif depth == 0:
                clean.append(char)
        if depth: raise NCError(f"Řádek {number}: neuzavřený komentář.")
        line = ''.join(clean).strip()
        if not line or line == '%':
            continue
        words = list(WORD.finditer(line))
        residue = WORD.sub('', line).strip()
        if residue:
            raise NCError(f"Řádek {number}: nerozpoznaný zápis {residue!r}.")
        values = [(m[1].upper(), float(m[2])) for m in words]
        if any(not math.isfinite(v) for _, v in values):
            raise NCError(f"Řádek {number}: neplatné číslo.")
        result.append((number, values))
    return result, warnings


def arc_points(start, end, i, j, clockwise):
    cx, cy = start[0] + i, start[1] + j
    radius = math.hypot(i, j)
    other = math.hypot(end[0] - cx, end[1] - cy)
    if radius < 1e-9 or abs(radius - other) > max(.01, radius * .001):
        raise NCError("Nekonzistentní poloměr oblouku I/J.")
    a = math.atan2(start[1] - cy, start[0] - cx)
    b = math.atan2(end[1] - cy, end[0] - cx)
    sweep = (a - b if clockwise else b - a) % (2 * math.pi)
    if math.dist(start, end) < 1e-9:
        sweep = 2 * math.pi
    # Maximum chord error 0.005 mm and maximum angle 10 degrees.
    step = min(math.pi / 18, 2 * math.acos(max(-1, 1 - .005 / radius)))
    count = max(1, math.ceil(sweep / max(step, 1e-8)))
    if count > 200000:
        raise NCError("Oblouk je příliš velký pro bezpečné zpracování.")
    sign = -1 if clockwise else 1
    points = [(cx + radius * math.cos(a + sign * sweep * k / count),
               cy + radius * math.sin(a + sign * sweep * k / count))
              for k in range(1, count + 1)]
    points[-1] = end
    return points


def strip_tool_changes(lines, source_text=''):
    """Remove T...M6 blocks before modal interpretation; keep source line numbers."""
    kept, warnings = [], []
    source_lines = source_text.splitlines()
    def follows_tool_pause(end):
        if end+1 >= len(lines): return False
        pause_number,pause_words = lines[end+1]
        gap = '\n'.join(source_lines[lines[end][0]-1:pause_number])
        return ([word for word in pause_words if word[0] != 'N'] == [('M',0)]
                and re.search(r'\(\s*MSG\s*,\s*Change\s+to\s+Tool\b',gap,re.IGNORECASE) is not None)
    index = 0
    while index < len(lines):
        number, words = lines[index]
        has_t = any(k == 'T' for k,_ in words)
        has_m6 = ('M',6) in words
        if has_t or has_m6:
            if any(k not in ('N','T') and (k,v) != ('M',6) for k,v in words):
                raise NCError(f'Řádek {number}: příkaz výměny nástroje je smíchaný s jinými příkazy; oddělte jej na vlastní řádek.')
            end = index if has_m6 else None
            if has_t and not has_m6:
                for candidate in range(index+1,len(lines)):
                    _, values = lines[candidate]
                    if any(k == 'T' or (k == 'M' and v in (2,30)) for k,v in values): break
                    if ('M',6) in values:
                        if any(k != 'N' and (k,v) != ('M',6) for k,v in values):
                            raise NCError(f'Řádek {lines[candidate][0]}: M6 je smíchané s jinými příkazy; oddělte jej na vlastní řádek.')
                        end = candidate
                        break
            if end is None and follows_tool_pause(index): end = index
            if end is not None:
                suffix = ''
                if follows_tool_pause(end):
                    end += 1
                    suffix = ' včetně navazující pauzy M0 s hlášením Change to Tool'
                warnings.append(f'Řádky {number}–{lines[end][0]}: vynechána výměna nástroje{suffix}.')
                index = end+1
            else:
                warnings.append(f'Řádek {number}: vynecháno samotné T bez následujícího M6; ostatní řádky zachovány.')
                index += 1
            continue
        kept.append((number,words))
        index += 1
        if any(k == 'M' and v in (2,30) for k,v in words):
            break
    return kept,warnings


def parse_nc(text, mode='auto', threshold=0.0, drill_diameter=0.0):
    if mode not in ('auto', 'z', 'spindle') or not math.isfinite(threshold):
        raise NCError("Neplatný režim nebo hranice Z.")
    lines, warnings = blocks(text)
    lines, tool_warnings = strip_tool_changes(lines,text)
    warnings.extend(tool_warnings)
    if mode == 'auto':
        mode = 'z' if any(k == 'Z' for _, ws in lines for k, _ in ws) else 'spindle'
    drawing = Drawing(warnings=warnings, mode=mode)
    positive(drill_diameter, 'Průměr značky', zero=True)
    drill_candidate = None
    drilled = set()
    x = y = z = None
    motion, absolute, unit = 0, True, 1.0
    spindle, power, feed = False, 0.0, 0.0
    split = True
    allowed_g = {0, 1, 2, 3, 17, 20, 21, 90, 91, 91.1, 94}
    for number, ws in lines:
        try:
            if ('M',0) in ws:
                if sum(k == 'M' for k,_ in ws) != 1 or any(k != 'N' and (k,v) != ('M',0) for k,v in ws):
                    raise NCError('M0 s dalšími příkazy na jednom řádku: oddělte pauzu na vlastní řádek.')
                drawing.pauses.setdefault(len(drawing.strokes),[]).append('M0')
                split = True
                continue
            gs = [v for k, v in ws if k == 'G']
            ms = [v for k, v in ws if k == 'M']
            if any(g not in allowed_g for g in gs):
                raise NCError(f"Nepodporovaný G příkaz: {gs}. (Podporováno G0–G3, G17, G20/21, G90/91, G91.1, G94.)")
            if any(m not in {3, 4, 5, 2, 30} for m in ms):
                raise NCError(f"Nepodporovaný M příkaz: {ms}.")
            if any(k not in 'NGMXYZIJSF' for k, _ in ws):
                raise NCError("Nepodporovaná adresa; cykly, korekce, R oblouky a změny počátku zatím nelze převést.")
            vals = {k: v for k, v in ws if k not in 'NGM'}
            if len(vals) != len([k for k, _ in ws if k not in 'NGM']):
                raise NCError("Opakovaná souřadnice nebo parametr na jednom řádku.")
            for group in ({0, 1, 2, 3}, {20, 21}, {90, 91}):
                if len([g for g in gs if g in group]) > 1:
                    raise NCError("Konfliktní G příkazy na jednom řádku.")
            if len(ms) > 1:
                raise NCError("Více M příkazů na jednom řádku není podporováno.")
            if 20 in gs: unit = 25.4
            if 21 in gs: unit = 1.0
            if 90 in gs: absolute = True
            if 91 in gs: absolute = False
            for g in gs:
                if g in (0, 1, 2, 3): motion = int(g)
            if 'S' in vals: power = vals['S']
            if 'F' in vals: feed = vals['F'] * unit
            if power < 0 or feed < 0:
                raise NCError("Záporný výkon nebo posuv.")
            if any(m in ms for m in (3, 4)): spindle = True; split = True
            if 5 in ms: spindle = False; split = True
            if any(m in ms for m in (2, 30)):
                if any(k in vals for k in 'XYZIJ'):
                    raise NCError("Pohyb na řádku ukončení programu.")
                break
            def coord(key, old):
                if key not in vals: return old
                if not absolute and old is None:
                    raise NCError("Relativní pohyb bez známé počáteční souřadnice.")
                return vals[key] * unit + (0 if absolute else old)
            nx, ny, nz = coord('X', x), coord('Y', y), coord('Z', z)
            xy = any(k in vals for k in 'XYIJ')
            if xy and 'Z' in vals and z != nz:
                raise NCError("Současný pohyb XY a Z vyžaduje zvláštní pravidlo převodu; není automaticky zploštěn.")
            if xy and x is not None and y is not None and ((nx,ny) != (x,y) or motion in (2,3)):
                # A plunge followed by cutting in XY is a contour entry, not a hole.
                drill_candidate = None
            if 'Z' in vals and nz is not None:
                if nz > threshold and drill_candidate is not None:
                    if drill_candidate not in drilled:
                        drawing.drill_points.append(drill_candidate)
                        drilled.add(drill_candidate)
                    drill_candidate = None
                elif (motion == 1 and z is not None and z > threshold >= nz
                      and nx is not None and ny is not None and not xy):
                    drill_candidate = (nx,ny)
            if xy:
                if nx is None or ny is None:
                    raise NCError("Před prvním pohybem musí být známy obě souřadnice X a Y.")
                if mode == 'z' and motion != 0 and nz is None:
                    raise NCError("Pracovní pohyb bez známé výšky Z.")
                burn = motion != 0 and (nz <= threshold if mode == 'z' else spindle and power > 0)
                end = (nx, ny)
                if x is None or y is None:
                    if motion != 0:
                        raise NCError("První XY poloha musí být zadána rychloposuvem G0.")
                    drawing.strokes.append(Stroke([end], False, feed, power))
                else:
                    start = (x, y)
                    points = [start]
                    if motion in (2, 3):
                        if not any(k in vals for k in 'IJ'):
                            raise NCError("Oblouk vyžaduje relativní střed I/J.")
                        points += arc_points(start, end, vals.get('I', 0) * unit,
                                             vals.get('J', 0) * unit, motion == 2)
                    else:
                        if any(k in vals for k in 'IJ'):
                            raise NCError("I/J mimo oblouk.")
                        points.append(end)
                    if start != end or len(points) > 2:
                        last = drawing.strokes[-1] if drawing.strokes else None
                        if (not split and len(drawing.strokes) not in drawing.pauses
                                and last and last.burn == burn and last.feed == feed
                                and last.power == power and last.rapid == (motion == 0) and last.points[-1] == start):
                            last.points.extend(points[1:])
                        else:
                            drawing.strokes.append(Stroke(points, burn, feed, power, motion == 0))
                split = False
            if 'Z' in vals and z != nz:
                split = True
            x, y, z = nx, ny, nz
        except NCError as e:
            raise NCError(f"Řádek {number}: {e}") from e
    if drill_diameter and drawing.drill_points:
        radius = drill_diameter/2
        # Closed polygons, maximum radial chord error 0.002 mm, at least 32 sides.
        count = max(32,math.ceil(math.pi/math.acos(max(-1,1-min(.002/radius,1)))))
        if count > 10000: raise NCError('Průměr vrtací značky je příliš velký.')
        for cx,cy in drawing.drill_points:
            points = [(cx+radius*math.cos(2*math.pi*i/count),cy+radius*math.sin(2*math.pi*i/count))
                      for i in range(count)]
            points.append(points[0])
            drawing.strokes.append(Stroke(points,True))
        drawing.warnings.append(f'Vytvořeno {len(drawing.drill_points)} značek děr Ø {fmt(drill_diameter)} mm (na konci drah tohoto souboru).')
    elif drawing.drill_points:
        drawing.warnings.append(f'Nalezeno {len(drawing.drill_points)} vrtacích bodů; zapněte značky děr pro jejich převod.')
    drawing.bounds()
    if not any(s.burn for s in drawing.strokes):
        drawing.warnings.append("Žádné pracovní dráhy. Zkontrolujte režim, hranici Z a vstupní výkon S.")
    return drawing


def merge_drawings(drawings):
    """Join independent documents, preserving absolute coordinates and operation order."""
    drawings = list(drawings)
    if not drawings: raise NCError('Žádné vstupní výkresy ke spojení.')
    merged = Drawing(mode='spojené soubory')
    for drawing in drawings:
        offset = len(merged.strokes)
        for index,pauses in drawing.pauses.items():
            merged.pauses.setdefault(offset+index,[]).extend(pauses)
        merged.strokes.extend(drawing.strokes)
        merged.drill_points.extend(drawing.drill_points)
        merged.warnings.extend(drawing.warnings)
    boxes = [d.reference_bounds or d.bounds() for d in drawings]
    merged.reference_bounds = (min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
    merged.bounds()
    return merged


def fmt(value):
    return f'{value:.4f}'.rstrip('0').rstrip('.') if abs(value) >= .00005 else '0'


def positive(value, name, zero=False):
    if not math.isfinite(value) or (value < 0 if zero else value <= 0):
        raise NCError(f"{name}: zadejte {'nezáporné' if zero else 'kladné'} konečné číslo.")


def export_nc(drawing, feed, power, mirror_x=False, mirror_y=False, laser='M3', rotation=0):
    positive(feed, 'Rychlost')
    positive(power, 'Výkon')
    if laser not in ('M3', 'M4'):
        raise NCError("Režim laseru musí být M3 nebo M4.")
    if rotation not in (0,90,180,270):
        raise NCError("Otočení musí být 0, 90, 180 nebo 270 stupňů.")
    bounds = drawing.reference_bounds or drawing.bounds()
    def transform(p):
        x = bounds[0] + bounds[2] - p[0] if mirror_x else p[0]
        y = bounds[1] + bounds[3] - p[1] if mirror_y else p[1]
        if rotation == 0: return x,y
        x,y = x-bounds[0],y-bounds[1]
        width,height = bounds[2]-bounds[0],bounds[3]-bounds[1]
        if rotation == 90: x,y = height-y,x
        elif rotation == 180: x,y = width-x,height-y
        else: x,y = y,width-x
        return bounds[0]+x,bounds[1]+y
    out = ['(PrevodnikNC 0.4 - mm)', 'G21', 'G90', 'G17', 'G94', 'M5']
    position = None
    def rapid(p):
        nonlocal position
        target = (fmt(p[0]), fmt(p[1]))
        if target != position:
            out.append(f'G0 X{target[0]} Y{target[1]}')
            position = target
    burns = 0
    for index,stroke in enumerate(drawing.strokes):
        out.extend(drawing.pauses.get(index,[]))  # All preceding strokes end with laser off.
        pts = [transform(p) for p in stroke.points]
        if not stroke.burn:
            for p in pts[1:] if len(pts) > 1 else pts:
                rapid(p)
            continue
        if len(pts) < 2: continue
        burns += 1
        rapid(pts[0])
        out += [f'{laser} S{fmt(power)}', f'G1 F{fmt(feed)}']
        out += [f'G1 X{fmt(p[0])} Y{fmt(p[1])}' for p in pts[1:]]
        position = (fmt(pts[-1][0]), fmt(pts[-1][1]))
        out.append('M5')
    if not burns:
        raise NCError("Není co převést: vstup neobsahuje pracovní dráhy.")
    out.extend(drawing.pauses.get(len(drawing.strokes),[]))
    out += ['M2', '']  # Laser already off after every working stroke.
    return '\n'.join(out)


def negative_fill_lines(width, diameter):
    """Fixed edge offsets and 80% steps inward; only the centre is exceptional."""
    positive(width, 'Šířka spoje')
    positive(diameter, 'Rozteč čar')
    if diameter < .001:
        raise NCError('Rozteč čar musí být alespoň 0,001 mm.')
    if width < diameter - 1e-9:
        raise NCError('Šířka spoje nesmí být menší než D (Rozteč čar). Zmenšete D.')
    if width / diameter > 50000:
        raise NCError('Příliš hustý obrazec; zvětšete rozteč čar.')
    left, right = diameter / 2, width - diameter / 2
    lines = [left]
    if right - left <= 1e-9:
        return lines
    lines.append(right)
    step = .8 * diameter
    while right - left > diameter + 1e-9:
        if right - left <= 2 * step + 1e-9:
            lines.append((left + right) / 2)
            break
        left += step
        right -= step
        lines.extend((left, right))
    return sorted(lines)


def test_pattern(x, y, width, height, columns, rows, gap, spacing,
                 min_power, max_power, min_feed, max_feed, laser='M3', trace_widths=None,
                 trace_pass_mode=None, border_count=0, border_width=.2, negative=False, negative_gap=.5):
    for v, label in ((width, 'Šířka'), (height, 'Výška'), (spacing, 'Rozteč čar'),
                     (min_power, 'Výkon od'), (max_power, 'Výkon do'),
                     (min_feed, 'Rychlost od'), (max_feed, 'Rychlost do')):
        positive(v, label)
    positive(gap, 'Mezera', zero=True)
    if not all(math.isfinite(v) for v in (x, y)):
        raise NCError('Neplatný počátek obrazce.')
    if not 1 <= columns <= 20 or not 1 <= rows <= 20:
        raise NCError('Počet řádků a sloupců musí být 1 až 20.')
    if max_power < min_power or max_feed < min_feed:
        raise NCError('Horní mez musí být větší nebo rovna dolní.')
    if trace_pass_mode not in (None,'adjacent'):
        raise NCError('Neplatný režim průjezdů.')
    if laser not in ('M3', 'M4'): raise NCError('Neplatný režim laseru.')
    cw, ch = (width - (columns-1)*gap)/columns, (height - (rows-1)*gap)/rows
    if cw <= 0 or ch <= 0:
        raise NCError('Zadané mezery se nevejdou do plochy obrazce.')
    if type(border_count)!=int or border_count not in (0,1,2):
        raise NCError('Počet obrysů musí být 0, 1 nebo 2.')
    if negative:
        trace_pass_mode=None
    margin=0
    if border_count:
        positive(border_width,'Šířka stopy obrysu')
        if border_width<.001: raise NCError('Šířka stopy obrysu musí být alespoň 0,001 mm.')
        border_step=.8*border_width
        margin=(border_count-1)*border_step+border_width/2
    # Reserve the whole nominal beam footprint inside the requested area.
    if not negative and border_count and (rows>1 or columns>1) and gap+1e-9<2*margin:
        raise NCError(f'Obrysy se nevejdou do oddělení polí. Zvětšete mezeru polí alespoň na {math.ceil(2*margin*100)/100:g} mm.')
    if negative:
        # Each frame fits inside its own fixed cell; never enlarge the board.
        cell_width,cell_height=cw,ch
        cw-=2*margin; ch-=2*margin
    else:
        cw-=2*margin/columns; ch-=2*margin/rows
        cell_width,cell_height=cw,ch
    if min(cw,ch)<=0: raise NCError('Obrys se nevejde do pole; zvětšete plochu nebo zmenšete šířku stopy obrysu.')
    trace_widths = tuple(trace_widths or ())
    if trace_pass_mode and not trace_widths: raise NCError('Porovnání průjezdů vyžaduje šířky spojů.')
    if len(trace_widths)>12: raise NCError('Zadejte nejvýše 12 šířek spojů.')
    for value in trace_widths:
        positive(value,'Šířka spoje')
        if value<.0001: raise NCError('Šířka spoje je menší než přesnost výstupu 0,0001 mm.')
    notes=[]; groups=[]
    if negative:
        if not trace_widths:
            raise NCError('Negativní test vyžaduje šířky spojů.')
        positive(negative_gap, 'Mezera sloupečků', zero=True)
        length=(cw-(len(trace_widths)-1)*negative_gap)/len(trace_widths)
        if length <= spacing:
            raise NCError('Sloupečky se nevejdou do šířky pole. Zmenšete jejich mezeru, D nebo počet šířek spojů.')
        notes=['(Negativni rezist: laser osvituje budouci med.)',
               '(Sirky sloupecku zleva v mm: '+' / '.join(fmt(v) for v in trace_widths)+')',
               f'(Plocha {fmt(width)} x {fmt(height)} mm; pole {fmt(cell_width)} x {fmt(cell_height)} mm.)',
               f'(Prostor uvnitr ramu {fmt(cw)} x {fmt(ch)} mm; mezera sloupecku {fmt(negative_gap)} mm.)',
               '(Kazdy sloupecek: mezera W, obdelnik W, mezera W; opakovani po cele vysce.)',
               '(Neuplny horni obdelnik se vynecha; posledni horni mezera neni porovnavaci.)',
               f'(D {fmt(spacing)} mm; osy D/2 dovnitr od hran; pevny krok {fmt(.8*spacing)} mm; prekryti 20 procent.)',
               '(Vypln od obou hran; zbyvajici vzdalenost os <= D bez dalsi drahy, > D doplnena uprostred.)',
               f'(Nominalni delka obdelniku {fmt(length)} mm; delka drahy {fmt(length-spacing)} mm.)']
        total=0
        for index, trace_width in enumerate(trace_widths):
            offsets=negative_fill_lines(trace_width, spacing)
            repeats=math.floor((ch+1e-9)/(2*trace_width))
            if repeats < 1:
                raise NCError(f'Spoj {fmt(trace_width)} mm se do výšky pole nevejde ani jednou s dolní mezerou. Zmenšete počet řádků nebo šířku spoje.')
            total+=repeats*len(offsets)
            if rows*columns*total>50000:
                raise NCError('Příliš hustý obrazec; zvětšete rozteč čar.')
            notes.append(f'(Sloupecek {index+1}: W {fmt(trace_width)} mm / mezera {fmt(trace_width)} mm / obdelniku {repeats} / drah na obdelnik {len(offsets)} / osy od dolni hrany: '+
                         ' / '.join(fmt(v) for v in offsets)+')')
            for repeat in range(repeats):
                base=(2*repeat+1)*trace_width
                groups.append((f'W{fmt(trace_width)} vzorek {repeat+1}',index*(length+negative_gap)+spacing/2,length-spacing,
                               [base+v for v in offsets],False))
    elif trace_widths:
        notes=['(Test spoju: vodorovne zbytky medi; sirky zdola nahoru v mm)',
               '('+' / '.join(fmt(v) for v in trace_widths)+')',
               '(Sirky jsou nominalni sirky medi; prvni osa je vne hrany o polovinu zadane roztece.)']
        if trace_pass_mode:
            separation=max(.5,2*spacing)
            length=(cw-2*separation)/3
            if length<2:
                minimum=columns*(6+2*separation)+(columns-1)*gap+2*margin
                raise NCError(f'Porovnání 1/2/3 se nevejde. Zvětšete šířku plochy alespoň na {math.ceil(minimum*100)/100:g} mm.')
            step=.8*spacing
            extent=spacing/2+2*step
            # Reserve nominal footprints and .3 mm clear space between rectangles.
            required=sum(trace_widths)+len(trace_widths)*(2*extent+spacing)+(len(trace_widths)-1)*.3
            if ch<required:
                minimum=rows*required+(rows-1)*gap+2*margin
                raise NCError(f'Vodorovné spoje se nevejdou. Zvětšete výšku plochy alespoň na {math.ceil(minimum*100)/100:g} mm.')
            notes+=['(V kazdem poli tri vzorky zleva: 1 / 2 / 3 prujezdy)',
                    '(Prvni osa od hrany '+fmt(spacing/2)+' mm; dalsi drahy krok '+fmt(step)+' mm; prekryti 20 procent)']
            notes+=['(Kazdy obdelnik ma vlastni sadu drah pod i nad sebou.)',
                    '(Mezi nominalnimi stopami sousednich sad zustava 0.3 mm; drahy se nesdileji.)']
            for passes in (1,2,3):
                # Identical nominal copper rectangles in all three columns.
                bottom=(ch-required)/2+spacing/2+extent
                lines=[]
                for trace_width in trace_widths:
                    top=bottom+trace_width
                    lines.extend(sorted(bottom-spacing/2-n*step for n in range(passes)))
                    lines.extend(top+spacing/2+n*step for n in range(passes))
                    bottom=top+2*extent+spacing+.3
                groups.append((f'P{passes}',(passes-1)*(length+separation),length,lines,False))
        else:
            step=.8*spacing
            lane=(ch-sum(trace_widths)-len(trace_widths)*spacing)/(len(trace_widths)+1)
            if lane<2*spacing:
                minimum=rows*(sum(trace_widths)+len(trace_widths)*spacing+(len(trace_widths)+1)*2*spacing)+(rows-1)*gap+2*margin
                raise NCError(f'Spoje a mezery se nevejdou do polí. Zvětšete výšku plochy alespoň na {math.ceil(minimum*100)/100:g} mm.')
            if columns*rows*((ch-sum(trace_widths))/spacing+2*(len(trace_widths)+1))>50000:
                raise NCError('Příliš hustý obrazec; zvětšete rozteč čar.')
            lines=[]; bottom=0
            for index in range(len(trace_widths)+1):
                top=bottom+lane
                lines.extend(bottom+n*step for n in range(math.floor(lane/step)+1))
                if top-lines[-1]>.00005: lines.append(top)
                if index<len(trace_widths): bottom=top+trace_widths[index]+spacing
            groups=[('rastr',0,cw,lines,True)]
    else:
        if rows*columns*(int(ch/spacing)+1)>50000:
            raise NCError('Příliš hustý obrazec; zvětšete rozteč čar.')
        groups=[('plocha',0,cw,[n*spacing for n in range(int(ch/spacing)+1)],True)]
    if rows*columns*sum(len(g[3]) for g in groups)>50000:
        raise NCError('Příliš hustý obrazec; zvětšete rozteč čar.')
    if border_count:
        notes += [f'(Oddeleni celeho pole S/F: {border_count} uzavrene obrysy, prekryti stop 20 procent)',
                  f'(Sirka stopy obrysu {fmt(border_width)} mm; roztec obrysu {fmt(border_step)} mm)',
                  ('(Ram pouze kolem celeho S/F pole.)' if negative else '(Vnitrni propojeni vzorku 1/2/3 zustavaji zachovana.)'),
                  '(Vnejsi obrysy vcetne zadane sirky stopy zustavaji uvnitr zadane plochy.)']
    out=['(PrevodnikNC - test matrix, columns S / rows F)','G21','G90','G17','G94','M5']
    legend=[]
    for row in range(rows):
        feed=min_feed+(max_feed-min_feed)*row/max(1,rows-1)
        for col in range(columns):
            power=min_power+(max_power-min_power)*col/max(1,columns-1)
            xx,yy=x+col*(cell_width+gap)+margin,y+row*(cell_height+gap)+margin
            label=f'R{row+1} C{col+1}: S{fmt(power)} / F{fmt(feed)}'
            legend.append(label); out.append(f'({label})')
            for group,offset,length,lines,zigzag in groups:
                if trace_pass_mode or negative: out.append(f'({label} / {group})')
                for n,line_y in enumerate(lines):
                    a,b=(xx+offset,xx+offset+length)
                    if zigzag and n%2: a,b=b,a
                    out += [f'G0 X{fmt(a)} Y{fmt(yy+line_y)}',f'{laser} S{fmt(power)}',
                            f'G1 X{fmt(b)} Y{fmt(yy+line_y)} F{fmt(feed)}','M5']
            if border_count:
                # Exactly one perimeter set per entire S/F cell, never around
                # its three sub-samples: the internal bridges are intentional.
                for ring in range(border_count):
                    delta=ring*border_step
                    left,right=xx-delta,xx+cw+delta
                    bottom,top=yy-delta,yy+ch+delta
                    out += [f'({label} / obrys celeho pole {ring+1})',
                            f'G0 X{fmt(left)} Y{fmt(bottom)}',f'{laser} S{fmt(power)}',f'G1 F{fmt(feed)}',
                            f'G1 X{fmt(right)} Y{fmt(bottom)}',f'G1 X{fmt(right)} Y{fmt(top)}',
                            f'G1 X{fmt(left)} Y{fmt(top)}',f'G1 X{fmt(left)} Y{fmt(bottom)}','M5']
    header=['(Rozpis testu: sloupce zleva S, radky zdola F; F v mm/min)']+notes+[f'({label})' for label in legend]
    return '\n'.join(header+out+['M2','']),legend


def drawing_statistics(drawing, rapid_feed):
    """Lengths in mm and ideal XY seconds; unknown initial approach and pauses excluded."""
    positive(rapid_feed, 'Rychlost G0')
    burn = travel = seconds = 0.0
    count = 0
    unknown = False
    for stroke in drawing.strokes:
        length = sum(math.dist(a,b) for a,b in zip(stroke.points,stroke.points[1:]))
        if stroke.burn:
            burn += length
            count += int(length > 0)
            if length and stroke.feed <= 0: unknown = True
            elif length: seconds += length / stroke.feed * 60
        else:
            travel += length
            if length and not stroke.rapid and stroke.feed <= 0: unknown = True
            elif length: seconds += length / (rapid_feed if stroke.rapid else stroke.feed) * 60
    return burn,travel,count,None if unknown else seconds


def check_alignment(base, candidate):
    """Extent screening only: NC contours do not prove copper/pad identity."""
    if not candidate.drill_points:
        return 'gray','Soubor nemá rozpoznané vrtací body. Shodu ověřte v překrytém náhledu.'
    if not any(s.burn for s in base.strokes):
        return 'gray','Chybí pracovní obrysy pro porovnání vrtání.'
    x0,y0,x1,y1 = base.bounds()
    outside = sum(not (x0-.5 <= x <= x1+.5 and y0-.5 <= y <= y1+.5) for x,y in candidate.drill_points)
    if outside:
        return 'red',f'Podezření na nesoulad: {outside} z {len(candidate.drill_points)} otvorů leží mimo rozsah obrysů (tolerance 0,5 mm). Ověřte soubor, počátek a orientaci.'
    return 'amber',f'{len(candidate.drill_points)} otvorů je v rozsahu obrysů. Zrcadlení ani správnost desky tím nejsou potvrzeny — ověřte překrytí.'
