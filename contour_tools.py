"""Conservative Gerber clearance analysis; standard library only.

Supports positive, dark-only Gerber with circular-aperture linear and G75 arc draws, C/R/O flashes
and the explicitly verified KiCad RoundRect macro. Unsupported image operations
fail closed, never silently approximate a different copper image.
"""
from dataclasses import dataclass
import math
import re
import statistics
from pathlib import Path
from nc_core import NCError, Drawing


@dataclass(frozen=True)
class CopperShape:
    # Capsule for tracks/circles; rounded box for pads.
    kind: str
    a: tuple
    b: tuple
    radius: float

    def distance(self, p):
        x,y = p
        if self.kind == 'capsule':
            ax,ay = self.a; bx,by = self.b
            dx,dy = bx-ax,by-ay
            t = max(0,min(1,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy))) if dx or dy else 0
            return math.hypot(x-ax-t*dx,y-ay-t*dy)-self.radius
        cx,cy = self.a; hx,hy = self.b
        qx,qy = abs(x-cx)-hx,abs(y-cy)-hy
        return math.hypot(max(qx,0),max(qy,0))+min(max(qx,qy),0)-self.radius

    def bounds(self):
        if self.kind == 'capsule':
            return (min(self.a[0],self.b[0])-self.radius,min(self.a[1],self.b[1])-self.radius,
                    max(self.a[0],self.b[0])+self.radius,max(self.a[1],self.b[1])+self.radius)
        x,y = self.a; hx,hy = self.b; r = self.radius
        return x-hx-r,y-hy-r,x+hx+r,y+hy+r


@dataclass(frozen=True)
class CopperArc:
    start: tuple
    end: tuple
    center: tuple
    path_radius: float
    angle: float
    sweep: float
    radius: float
    kind: str = 'arc'

    def distance(self, point):
        dx,dy=point[0]-self.center[0],point[1]-self.center[1]
        angle=math.atan2(dy,dx)
        delta=((angle-self.angle) if self.sweep>0 else (self.angle-angle)) % math.tau
        if delta <= abs(self.sweep)+1e-12:
            return abs(math.hypot(dx,dy)-self.path_radius)-self.radius
        return min(math.dist(point,self.start),math.dist(point,self.end))-self.radius

    def bounds(self):
        # Full-circle bounds are conservative, including the aperture end caps.
        x,y=self.center; r=max(self.path_radius,math.dist(self.center,self.end))+self.radius
        return x-r,y-r,x+r,y+r

    def display_segments(self):
        step=min(math.pi/18,2*math.acos(max(-1,1-.002/self.path_radius)))
        count=max(1,math.ceil(abs(self.sweep)/max(step,1e-8)))
        if count>100000: raise NCError('Gerber: oblouk je příliš velký pro náhled.')
        points=[self.start]+[(self.center[0]+self.path_radius*math.cos(self.angle+self.sweep*i/count),
                             self.center[1]+self.path_radius*math.sin(self.angle+self.sweep*i/count)) for i in range(1,count)]+[self.end]
        return [CopperShape('capsule',a,b,self.radius) for a,b in zip(points,points[1:])]


def make_copper_arc(start,end,i,j,clockwise,width,tolerance):
    center=(start[0]+i,start[1]+j); radius=math.hypot(i,j)
    if radius<=0 or abs(math.dist(center,end)-radius)>tolerance:
        raise NCError('Gerber: nekonzistentní poloměr oblouku I/J.')
    angle=math.atan2(-j,-i)
    finish=math.atan2(end[1]-center[1],end[0]-center[0])
    sweep=((angle-finish) if clockwise else (finish-angle)) % math.tau
    if start==end: sweep=math.tau
    return CopperArc(start,end,center,radius,angle,-sweep if clockwise else sweep,width/2)


def find_copper_file(nc_path):
    """Only an unambiguous same-name copper Gerber in the NC directory."""
    if not nc_path: return None
    path=Path(nc_path); stem=path.stem
    extensions=('.gbr','.gbrl','.gbl','.gtl')
    embedded=Path(stem).suffix.lower()
    if embedded in extensions: stem=stem[:-len(embedded)]
    names={ (stem+suffix).casefold() for suffix in extensions }
    try: candidates=[p for p in path.parent.iterdir() if p.is_file() and p.name.casefold() in names]
    except OSError: return None
    matches=[]
    for candidate in candidates:
        try: text=candidate.read_text(encoding='utf-8-sig')
        except (OSError,UnicodeError): continue
        if re.search(r'%TF\.FileFunction,Copper(?:,|\*)',text): matches.append(candidate)
    return matches[0] if len(matches)==1 else None


class Copper:
    def __init__(self, shapes):
        self.shapes = shapes
        self.boxes = [s.bounds() for s in shapes]

    def distance(self, point):
        # Bounding-box pruning: shapes cannot be closer than their bounding box.
        x,y = point; best = float('inf')
        for shape,(x0,y0,x1,y1) in zip(self.shapes,self.boxes):
            dx,dy = max(x0-x,0,x-x1),max(y0-y,0,y-y1)
            if best > 0 and dx*dx+dy*dy < best*best:
                best = min(best,shape.distance(point))
            if best <= 0: return best
        return best


def _roundrect_macro(body):
    words = [re.sub(r'\s+','',s) for s in body if s.strip() and not s.strip().startswith('0 ')]
    expected = ['4,1,4,$2,$3,$4,$5,$6,$7,$8,$9,$2,$3,0']
    expected += [f'1,1,$1+$1,${a},${a+1}' for a in (2,4,6,8)]
    expected += [f'20,1,$1+$1,${a},${a+1},${b},${b+1},0' for a,b in ((2,4),(4,6),(6,8),(8,2))]
    return words == expected


def parse_copper(text):
    shapes = []; apertures = {}; macros = {}
    decimals = None; unit = None; selected = None; x = y = None
    operation = None; copper = False; ended = False
    interpolation = 1; multi_quadrant = False
    # Keep extended blocks intact (macros contain embedded '*' delimiters).
    tokens = re.findall(r'%[^%]*%|[^%*]+\*',text)
    residue = re.sub(r'%[^%]*%|[^%*]+\*','',text).strip()
    if residue: raise NCError('Gerber: neúplný příkaz.')
    for token in tokens:
        token = token.strip()
        if token.startswith('%'):
            body = token[1:-1].strip().rstrip('*'); parts = body.split('*'); cmd = parts[0].strip()
            if cmd.startswith('AM'):
                macros[cmd[2:]] = _roundrect_macro(parts[1:]); continue
            if len(parts) != 1: raise NCError('Gerber: nepodporovaný sdružený příkaz.')
            match = re.fullmatch(r'FSLAX([1-6])([1-6])Y([1-6])([1-6])',cmd)
            if match:
                if shapes or decimals is not None: raise NCError('Gerber: opakovaná změna formátu.')
                decimals = (int(match[2]),int(match[4])); continue
            if cmd in ('MOMM','MOIN'):
                if shapes or unit is not None: raise NCError('Gerber: opakovaná změna jednotek.')
                unit = 1 if cmd == 'MOMM' else 25.4; continue
            if cmd == 'TF.FilePolarity,Negative': raise NCError('Gerber: záporná polarita není podporována.')
            if cmd.startswith('TF.FileFunction,'):
                copper = cmd.split(',')[1] == 'Copper'; continue
            if cmd.startswith(('TF.','TA.','TO.','TD')): continue
            if cmd == 'LPD': continue
            match = re.fullmatch(r'ADD(\d+)([^,]+),(.+)',cmd)
            if match:
                if unit is None: raise NCError('Gerber: chybí jednotky před definicí apertury.')
                name = match[2]
                try: values = [float(v)*unit for v in match[3].split('X')]
                except ValueError: raise NCError('Gerber: neplatná apertura.')
                if any(not math.isfinite(v) for v in values): raise NCError('Gerber: neplatné rozměry.')
                if name == 'C' and len(values)==1 and values[0]>0: spec = ('C',values)
                elif name in ('R','O') and len(values)==2 and min(values)>0: spec = (name,values)
                elif macros.get(name) and len(values)==10 and values[-1]==0:
                    r = values[0]; coords = list(zip(values[1:9:2],values[2:9:2]))
                    xs = sorted(set(v[0] for v in coords)); ys = sorted(set(v[1] for v in coords))
                    if r<=0 or len(xs)!=2 or len(ys)!=2 or set(coords)!={(xx,yy) for xx in xs for yy in ys}:
                        raise NCError('Gerber: nepodporovaný tvar RoundRect.')
                    if any(a[0]!=b[0] and a[1]!=b[1] for a,b in zip(coords,coords[1:]+coords[:1])):
                        raise NCError('Gerber: nepodporované pořadí rohů RoundRect.')
                    spec = ('RR',[(xs[0]+xs[1])/2,(ys[0]+ys[1])/2,(xs[1]-xs[0])/2,(ys[1]-ys[0])/2,r])
                else: raise NCError(f'Gerber: nepodporovaná apertura {name}; automatický výběr nelze bezpečně provést.')
                if int(match[1]) in apertures: raise NCError('Gerber: opakovaná apertura.')
                apertures[int(match[1])] = spec; continue
            raise NCError(f'Gerber: nepodporovaná operace {cmd[:60]}. Automatický výběr nebyl proveden.')
        cmd = token[:-1].strip()
        if cmd.startswith('G04'): continue
        if cmd == 'G75': multi_quadrant=True; continue
        if cmd == 'G74':
            raise NCError('Gerber: starší oblouky G74 nejsou podporovány; exportujte v režimu G75.')
        modal=re.match(r'^G0?([123])',cmd)
        if modal:
            interpolation=int(modal[1]); cmd=cmd[modal.end():]
            if not cmd: continue
        if cmd in ('M02','M2'): ended = True; break
        match = re.fullmatch(r'D(\d+)',cmd)
        if match and int(match[1])>=10:
            selected = apertures.get(int(match[1]))
            if selected is None: raise NCError('Gerber: neznámá apertura.')
            continue
        match = re.fullmatch(r'(?:X([+-]?\d+))?(?:Y([+-]?\d+))?(?:I([+-]?\d+))?(?:J([+-]?\d+))?(?:D0?([123]))?',cmd)
        if not match or not cmd: raise NCError(f'Gerber: nepodporovaný příkaz {cmd[:60]}.')
        if decimals is None or unit is None: raise NCError('Gerber: chybí formát nebo jednotky.')
        nx = x if match[1] is None else int(match[1])*unit/10**decimals[0]
        ny = y if match[2] is None else int(match[2])*unit/10**decimals[1]
        operation = int(match[5]) if match[5] else operation
        if (match[3] is not None or match[4] is not None) and (operation!=1 or interpolation==1):
            raise NCError('Gerber: I/J mimo kreslení oblouku.')
        if nx is None or ny is None or operation is None: raise NCError('Gerber: neúplná poloha/operace.')
        if operation in (1,3):
            if selected is None: raise NCError('Gerber: není vybrána apertura.')
            kind,v = selected
            if operation == 1:
                if x is None or y is None or kind!='C': raise NCError('Gerber: tah vyžaduje známý počátek a kruhovou aperturu.')
                if interpolation==1:
                    shapes.append(CopperShape('capsule',(x,y),(nx,ny),v[0]/2))
                else:
                    if not multi_quadrant: raise NCError('Gerber: oblouk vyžaduje režim G75.')
                    if match[3] is None or match[4] is None: raise NCError('Gerber: oblouk vyžaduje oba posuny I a J.')
                    i=int(match[3])*unit/10**decimals[0]
                    j=int(match[4])*unit/10**decimals[1]
                    shapes.append(make_copper_arc((x,y),(nx,ny),i,j,interpolation==2,v[0],
                                                  max(.0001,2*unit/10**min(decimals))))
            elif kind == 'C': shapes.append(CopperShape('capsule',(nx,ny),(nx,ny),v[0]/2))
            elif kind == 'R': shapes.append(CopperShape('box',(nx,ny),(v[0]/2,v[1]/2),0))
            elif kind == 'O':
                r=min(v)/2; dx=max(0,(v[0]-v[1])/2); dy=max(0,(v[1]-v[0])/2)
                shapes.append(CopperShape('capsule',(nx-dx,ny-dy),(nx+dx,ny+dy),r))
            else: shapes.append(CopperShape('box',(nx+v[0],ny+v[1]),(v[2],v[3]),v[4]))
        x,y = nx,ny
    if not ended or not copper or not shapes:
        raise NCError('Vyberte úplný pozitivní Gerber mědi (FileFunction Copper).')
    return Copper(shapes)



@dataclass
class ContourAnalysis:
    levels: list
    by_stroke: dict
    uncertain: list
    clearances: dict

    def selected(self, count):
        return {index for index,level in self.by_stroke.items() if level < count}


def analyze_contours(drawing, copper, tolerance=.008):
    """Propose whole closed paths grouped by clearance, never by file order.

    Vertices and intermediate samples <=0.25 mm apart are checked. A preview
    is required: this is not a proof of CAM pass provenance or a general offset
    reconstruction. Nonuniform/open/intersecting paths remain unselected.
    """
    stable=[]; uncertain=[]; clearances={}
    for index,stroke in enumerate(drawing.strokes):
        if not stroke.burn: continue
        if len(stroke.points)<4 or math.dist(stroke.points[0],stroke.points[-1])>.001:
            uncertain.append(index); continue
        samples=[]
        for a,b in zip(stroke.points,stroke.points[1:]):
            steps=max(1,math.ceil(math.dist(a,b)/.25))
            if steps>100000: raise NCError('Příliš dlouhý úsek pro analýzu kontur.')
            samples.extend((a[0]+(b[0]-a[0])*j/steps,a[1]+(b[1]-a[1])*j/steps) for j in range(steps))
        values=[copper.distance(point) for point in samples]
        middle=statistics.median(values); clearances[index]=middle
        if min(values)<=.001 or max(values)-min(values)>tolerance:
            uncertain.append(index)
        else: stable.append((middle,index))
    # A cluster cannot exceed the tolerance even through a chain of nearby values.
    groups=[]
    for value,index in sorted(stable):
        if not groups or value-groups[-1][0][0]>tolerance: groups.append([])
        groups[-1].append((value,index))
    levels=[statistics.median(v for v,i in group) for group in groups]
    # Ambiguous adjacent bands are not treated as separate passes.
    if any(b-a < tolerance*2 for a,b in zip(levels,levels[1:])):
        raise NCError('Vzdálenosti kontur netvoří oddělené vrstvy. Automatický výběr není jednoznačný.')
    if not groups: raise NCError('Nenalezeny rovnoměrně odsazené uzavřené kontury. Ověřte Gerber a orientaci NC.')
    return ContourAnalysis(levels,{i:level for level,group in enumerate(groups) for v,i in group},uncertain,clearances)


def omit_strokes(drawing, excluded):
    excluded=set(excluded)
    if any(not isinstance(i,int) or i<0 or i>=len(drawing.strokes) or not drawing.strokes[i].burn for i in excluded):
        raise NCError('Výběr kontur neodpovídá tomuto vstupu. Proveďte výběr znovu.')
    result=Drawing(warnings=list(drawing.warnings),mode=drawing.mode,drill_points=list(drawing.drill_points))
    result.reference_bounds=drawing.reference_bounds or drawing.bounds()
    for index,stroke in enumerate(drawing.strokes):
        if index in drawing.pauses:
            result.pauses.setdefault(len(result.strokes),[]).extend(drawing.pauses[index])
        if index not in excluded: result.strokes.append(stroke)
    if len(drawing.strokes) in drawing.pauses:
        result.pauses.setdefault(len(result.strokes),[]).extend(drawing.pauses[len(drawing.strokes)])
    result.warnings.append(f'Vynecháno {len(excluded)} kontur podle výběru od mědi.')
    if not any(s.burn for s in result.strokes): raise NCError('Výběr by odstranil všechny pracovní dráhy.')
    return result


def copper_outlines(copper):
    """Polygons for a lightweight Tk background; analysis uses exact primitives."""
    result=[]
    display=[part for shape in copper.shapes for part in (shape.display_segments() if shape.kind=='arc' else [shape])]
    for shape in display:
        points=[]
        if shape.kind=='capsule':
            ax,ay=shape.a; bx,by=shape.b
            angle=math.atan2(by-ay,bx-ax)
            for cx,cy,start in ((bx,by,angle-math.pi/2),(ax,ay,angle+math.pi/2)):
                points.extend((cx+shape.radius*math.cos(start+math.pi*i/16),cy+shape.radius*math.sin(start+math.pi*i/16)) for i in range(17))
        else:
            x,y=shape.a; hx,hy=shape.b; r=shape.radius
            for sx,sy,start in ((1,1,0),(-1,1,math.pi/2),(-1,-1,math.pi),(1,-1,3*math.pi/2)):
                points.extend((x+sx*hx+r*math.cos(start+math.pi*i/16),y+sy*hy+r*math.sin(start+math.pi*i/16)) for i in range(9))
        result.append(points)
    return result
