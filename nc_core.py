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


@dataclass
class Drawing:
    strokes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    mode: str = ""
    pauses: dict = field(default_factory=dict)
    drill_points: list = field(default_factory=list)

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
                                and last.power == power and last.points[-1] == start):
                            last.points.extend(points[1:])
                        else:
                            drawing.strokes.append(Stroke(points, burn, feed, power))
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
    merged = Drawing(mode='spojené soubory')
    for drawing in drawings:
        offset = len(merged.strokes)
        for index,pauses in drawing.pauses.items():
            merged.pauses.setdefault(offset+index,[]).extend(pauses)
        merged.strokes.extend(drawing.strokes)
        merged.drill_points.extend(drawing.drill_points)
        merged.warnings.extend(drawing.warnings)
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
    bounds = drawing.bounds()
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


def test_pattern(x, y, width, height, columns, rows, gap, spacing,
                 min_power, max_power, min_feed, max_feed, laser='M3'):
    for v, label in ((width, 'Šířka'), (height, 'Výška'), (spacing, 'Rozteč čar'),
                     (min_power, 'Výkon od'), (max_power, 'Výkon do'),
                     (min_feed, 'Rychlost od'), (max_feed, 'Rychlost do')):
        positive(v, label)
    positive(gap, 'Mezera', zero=True)
    if not all(math.isfinite(v) for v in (x, y)):
        raise NCError("Neplatný počátek obrazce.")
    if not 1 <= columns <= 20 or not 1 <= rows <= 20:
        raise NCError("Počet řádků a sloupců musí být 1 až 20.")
    if max_power < min_power or max_feed < min_feed:
        raise NCError("Horní mez musí být větší nebo rovna dolní.")
    cw, ch = (width - (columns-1)*gap)/columns, (height - (rows-1)*gap)/rows
    if cw <= 0 or ch <= 0:
        raise NCError("Zadané mezery se nevejdou do plochy obrazce.")
    if rows * columns * (int(ch / spacing) + 1) > 50000:
        raise NCError("Příliš hustý obrazec; zvětšete rozteč čar.")
    out = ['(PrevodnikNC - test matrix, columns S / rows F)', 'G21', 'G90', 'G17', 'G94', 'M5']
    legend = []
    if laser not in ('M3', 'M4'): raise NCError('Neplatný režim laseru.')
    for row in range(rows):
        feed = min_feed + (max_feed-min_feed)*row/max(1, rows-1)
        for col in range(columns):
            power = min_power + (max_power-min_power)*col/max(1, columns-1)
            xx, yy = x + col*(cw+gap), y + row*(ch+gap)
            label = f'R{row+1} C{col+1}: S{fmt(power)} / F{fmt(feed)}'
            legend.append(label)
            out.append(f'({label})')
            for n in range(int(ch/spacing)+1):
                a, b = (xx, xx+cw) if n % 2 == 0 else (xx+cw, xx)
                out += [f'G0 X{fmt(a)} Y{fmt(yy+n*spacing)}', f'{laser} S{fmt(power)}',
                        f'G1 X{fmt(b)} Y{fmt(yy+n*spacing)} F{fmt(feed)}', 'M5']
    return '\n'.join(out + ['M2', '']), legend
