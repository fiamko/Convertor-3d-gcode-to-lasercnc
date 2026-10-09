import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from nc_core import Drawing,Stroke,NCError,export_nc,parse_nc,merge_drawings
from contour_tools import Copper,CopperShape,parse_copper,analyze_contours,omit_strokes,find_copper_file,copper_outlines
from recovery import atomic_write_text,write_snapshot,read_snapshot

HEADER='%TF.FileFunction,Copper,L2,Bot*%\n%FSLAX45Y45*%\n%MOMM*%\n%LPD*%\n'

def circles():
    strokes=[]
    for cx in (0,10):
        for r in (1.13,1.05,1.09):
            points=[(cx+r*math.cos(i*2*math.pi/256),r*math.sin(i*2*math.pi/256)) for i in range(257)]
            strokes.append(Stroke(points,True,120,100))
    return Drawing(strokes)

class Contours(unittest.TestCase):
    def test_geometric_layers_not_nc_order(self):
        d=circles(); copper=Copper([CopperShape('capsule',(x,0),(x,0),1) for x in (0,10)])
        a=analyze_contours(d,copper)
        self.assertEqual(a.selected(1),{1,4})
        self.assertEqual(a.selected(2),{1,2,4,5})
        self.assertEqual(a.uncertain,[])
        for actual,expected in zip(a.levels,(.05,.09,.13)): self.assertAlmostEqual(actual,expected,places=3)
        d.strokes.append(Stroke([(0,0),(1,0),(2,0)],True))
        d.strokes.append(Stroke([(0,0),(2,0),(2,2),(0,0)],True))
        a=analyze_contours(d,copper)
        self.assertEqual(a.uncertain,[6,7])
        self.assertFalse(a.selected(2)&{6,7})

    def test_omission_preserves_transform_anchor_and_pauses(self):
        d=circles(); d.pauses={1:['M0'],2:['M0'],6:['M0']}
        excluded={0,3} # deliberately remove outermost: bounds would shrink
        trimmed=omit_strokes(d,excluded)
        self.assertEqual(trimmed.reference_bounds,d.bounds())
        self.assertEqual(sum(map(len,trimmed.pauses.values())),3)
        for rotation in (0,90,180,270):
            original=parse_nc(export_nc(d,2600,430,True,True,'M4',rotation))
            filtered=parse_nc(export_nc(trimmed,2600,430,True,True,'M4',rotation))
            self.assertEqual([s.points for i,s in enumerate(s for s in original.strokes if s.burn) if i not in excluded],
                             [s.points for s in filtered.strokes if s.burn])
        merged=merge_drawings([trimmed,Drawing([Stroke([(30,30),(31,30)],True)])])
        self.assertEqual(merged.reference_bounds[0],d.bounds()[0])
        with self.assertRaises(NCError): omit_strokes(d,range(6))
        with self.assertRaises(NCError): omit_strokes(d,[99])

    def test_gerber_standard_apertures_and_modal_coordinates(self):
        c=parse_copper(HEADER+'%ADD10C,2*%\n%ADD11R,2X4*%\n%ADD12O,4X2*%\nD10*\nX0Y0D03*\nX1000000Y0D02*\nX1200000D01*\nD11*\nX2000000Y0D03*\nD12*\nX3000000Y0D03*\nM02*')
        self.assertEqual(len(c.shapes),4)
        self.assertAlmostEqual(c.distance((1.05,0)),.05)
        self.assertAlmostEqual(c.distance((11,1.09)),.09)
        self.assertAlmostEqual(c.distance((21.13,0)),.13)
        self.assertAlmostEqual(c.distance((32.05,0)),.05)

    def test_reject_unsupported_or_non_copper_gerber(self):
        base=HEADER+'%ADD10C,2*%\nD10*\nX0Y0D03*\nM02*'
        for text in (base.replace('LPD','LPC'),base.replace('Copper','Profile'),
                     base.replace('X0Y0D03','G02X0Y0D01'),base.replace('M02*',''),
                     base.replace('C,2','C,2X1'),base.replace('M02*','%SRX2Y2I1J1*%\nM02*')):
            with self.subTest(text=text),self.assertRaises(NCError): parse_copper(text)

    def test_gerber_arc_directions_modal_state_and_full_circle(self):
        # Upper CCW semicircle, then modal CCW lower semicircle.
        text=HEADER+'%ADD10C,0.2*%D10*X100000Y0D02*G75*G03*X-100000Y0I-100000J0D01*X100000Y0I100000J0D01*G01*X200000Y0D01*M02*'
        c=parse_copper(text)
        self.assertEqual([s.kind for s in c.shapes],['arc','arc','capsule'])
        self.assertAlmostEqual(c.shapes[0].distance((0,1.3)),.2)
        self.assertGreater(c.shapes[0].distance((0,-1)),1)
        self.assertAlmostEqual(c.shapes[1].distance((0,-1.3)),.2)
        self.assertAlmostEqual(c.distance((1.5,.3)),.2)
        cw=parse_copper(text.replace('G03*','G02*'))
        self.assertAlmostEqual(cw.shapes[0].distance((0,-1.3)),.2)
        self.assertGreater(cw.shapes[0].distance((0,1)),1)
        full=parse_copper(HEADER+'%ADD10C,0.2*%D10*X100000Y0D02*G75*G02I-100000J0D01*M02*')
        for point in ((0,1.3),(0,-1.3),(1.3,0),(-1.3,0)):
            self.assertAlmostEqual(full.distance(point),.2)
        self.assertTrue(copper_outlines(full))

    def test_nc_arc_export_transform_all_mirror_rotation_combinations(self):
        drawing=parse_nc('G0 X3 Y2\nM3 S100\nG3 X1 Y4 I-2 J0 F1000\nG2 X3 Y2 I2 J0\nM5\nM2')
        x0,y0,x1,y1=drawing.bounds()
        for mx in (False,True):
            for my in (False,True):
                for rotation in (0,90,180,270):
                    text=export_nc(drawing,1000,100,mx,my,rotation=rotation)
                    self.assertFalse(any(line.startswith(('G2 ','G3 ')) for line in text.splitlines()))
                    actual=[p for stroke in parse_nc(text).strokes if stroke.burn for p in stroke.points]
                    expected=[]
                    for stroke in drawing.strokes:
                        if not stroke.burn: continue
                        for x,y in stroke.points:
                            x=x0+x1-x if mx else x; y=y0+y1-y if my else y
                            u,v=x-x0,y-y0; w,h=x1-x0,y1-y0
                            if rotation==90: x,y=x0+h-v,y0+u
                            elif rotation==180: x,y=x0+w-u,y0+h-v
                            elif rotation==270: x,y=x0+v,y0+w-u
                            expected.append((x,y))
                    self.assertEqual(len(actual),len(expected))
                    for a,b in zip(actual,expected): self.assertLess(math.dist(a,b),.00008)

    def test_arc_units_endcaps_and_validation(self):
        body='%ADD10C,0.2*%D10*X100000Y0D02*G75*G03X0Y100000I-100000J0D01*M02*'
        c=parse_copper(HEADER+body)
        self.assertAlmostEqual(c.distance((1,-.4)),.3)
        inches=parse_copper((HEADER+body).replace('MOMM','MOIN'))
        self.assertAlmostEqual(inches.distance((25.4,-10.16)),7.62)
        for invalid in (body.replace('G75*',''),body.replace('G75','G74'),
                        body.replace('I-100000J0','I0J0'),body.replace('I-100000J0','I-50000J0'),
                        body.replace('I-100000J0','I-100000'),body.replace('G03X','G01X'),
                        body.replace('D01*M02','D02*M02')):
            with self.subTest(invalid=invalid),self.assertRaises(NCError): parse_copper(HEADER+invalid)

    def test_find_only_matching_unambiguous_copper(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder); nc=folder/'board-B_Cu.gbrl.nc'
            copper=folder/'board-B_Cu.gbr'
            unrelated=folder/'other-B_Cu.gbr'; unrelated.write_text(HEADER)
            self.assertIsNone(find_copper_file(nc))
            copper.write_text(HEADER)
            self.assertEqual(find_copper_file(nc),copper)
            self.assertEqual(find_copper_file(folder/'board-B_Cu.nc'),copper)
            alt=folder/'board-B_Cu.GBRL'; alt.write_text(HEADER)
            self.assertIsNone(find_copper_file(nc))
            alt.write_text(HEADER.replace('Copper','Profile'))
            self.assertEqual(find_copper_file(nc),copper)
            copper.write_text(HEADER.replace('Copper','Profile'))
            self.assertIsNone(find_copper_file(nc))

    def test_roundrect_macro_is_verified_not_trusted_by_name(self):
        macro=['4,1,4,$2,$3,$4,$5,$6,$7,$8,$9,$2,$3,0']
        macro += [f'1,1,$1+$1,${a},${a+1}' for a in (2,4,6,8)]
        macro += [f'20,1,$1+$1,${a},${a+1},${b},${b+1},0' for a,b in ((2,4),(4,6),(6,8),(8,2))]
        text=HEADER+'%AMRoundRect*'+'*'.join(macro)+'*%\n%ADD10RoundRect,0.25X-1X-1X1X-1X1X1X-1X1X0*%\nD10*X0Y0D03*M02*'
        c=parse_copper(text)
        self.assertAlmostEqual(c.distance((1.3,0)),.05)
        self.assertAlmostEqual(c.distance((1.3,1.4)),.25)
        with self.assertRaises(NCError): parse_copper(text.replace('4,1,4,','4,0,4,'))

class Recovery(unittest.TestCase):
    def test_atomic_failure_preserves_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'data.nc'; path.write_text('original')
            with patch('recovery.os.replace',side_effect=PermissionError('blocked')):
                with self.assertRaises(PermissionError): atomic_write_text(path,'new')
            self.assertEqual(path.read_text(),'original')
            self.assertEqual(list(Path(folder).iterdir()),[path])
            atomic_write_text(path,'new\r\ntext\n')
            self.assertEqual(path.read_bytes(),b'new\r\ntext\n')

    def test_snapshot_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'snapshot.json'
            data=dict(version=1,documents=[],document_index=0,input='',output='text',test='',settings={},recipe_name='',recipe_note='česká poznámka')
            write_snapshot(path,data); self.assertEqual(read_snapshot(path),data)
            data['documents']=[dict(path='x',text='text',excluded=[-1])]
            write_snapshot(path,data)
            with self.assertRaises(ValueError): read_snapshot(path)

if __name__=='__main__': unittest.main()
