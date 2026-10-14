import unittest
import math
from nc_core import parse_nc, export_nc, NCError, test_pattern, negative_fill_lines
from milling_core import export_mill, preview_mill, milling_test, milling_seconds

SOURCE="""G21
G90
G0 Z2
G0 X0 Y0
G1 Z-0.1 F40
G1 X10 Y0 F100
G0 Z2
M0
G0 X0 Y5
G1 Z-0.1
G1 X10 Y5
G0 Z2
M2
"""

class MillingTests(unittest.TestCase):
    def test_motion_sequence_and_pause(self):
        out=export_mill(parse_nc(SOURCE),150,.04,2,60,12000,2)
        z=None; spindle=False; cut=0
        for line in out.splitlines():
            if line.startswith('G0 Z'): z=float(line[4:])
            if line.startswith('G1 Z'):
                self.assertTrue(spindle); z=float(line.split()[1][1:]); self.assertEqual(z,-.04)
                self.assertIn('F60',line)
            if line.startswith('G0 X'): self.assertEqual(z,2)
            if line.startswith('G1 X'):
                self.assertEqual(z,-.04); self.assertTrue(spindle); cut+=1
            if line=='M0': self.assertEqual(z,2); self.assertFalse(spindle)
            if line.startswith('M3'): spindle=True
            if line=='M5': spindle=False
        self.assertEqual(cut,2); self.assertFalse(spindle); self.assertEqual(z,2)
        self.assertEqual(out.count('G4 P2'),2)
        self.assertEqual(sum(s.burn for s in preview_mill(out).strokes),2)

    def test_matrix_depth_feed_and_bounds(self):
        out,legend=milling_test(40,80,20,12,3,2,2,.5,.02,.06,100,200,2,60,10000,1)
        self.assertEqual(len(legend),6)
        self.assertEqual(out.count('M3 S10000'),1)
        self.assertTrue(all(f'G1 Z-{d}' in out for d in ('0.02','0.04','0.06')))
        self.assertIn('G1 F100',out); self.assertIn('G1 F200',out)
        a,b,c,d=preview_mill(out).bounds()
        self.assertGreaterEqual(a,40); self.assertGreaterEqual(b,80)
        self.assertLessEqual(c,60); self.assertLessEqual(d,92)

    def test_transform_matches_laser(self):
        drawing=parse_nc(SOURCE)
        for rotation in (0,90,180,270):
            for mx in (False,True):
                laser=parse_nc(export_nc(drawing,100,50,mx,True,rotation=rotation))
                mill=preview_mill(export_mill(drawing,100,.04,2,60,10000,mirror_x=mx,mirror_y=True,rotation=rotation))
                self.assertEqual([s.points for s in laser.strokes if s.burn],[s.points for s in mill.strokes if s.burn])

    def test_time_includes_vertical_and_dwell(self):
        seconds=milling_seconds('G0 Z2\nG0 X0 Y0\nG4 P2\nG1 Z-0.04 F60\nG1 X10 F100\nG0 Z2\n',3000)
        self.assertAlmostEqual(seconds,2+2.04+6+2.04/50)

    def test_bad_settings(self):
        drawing=parse_nc(SOURCE)
        for index in range(5):
            values=[100,.04,2,60,10000,2]; values[index]=0
            with self.assertRaises(NCError): export_mill(drawing,*values)
        with self.assertRaises(NCError): export_mill(drawing,100,math.nan,2,60,10000)
        with self.assertRaises(NCError): milling_test(0,0,1,1,3,2,2,.2,.02,.06,100,200,2,60,10000)

    def test_trace_samples(self):
        out,_=milling_test(0,0,30,20,1,1,2,.2,.04,.04,100,100,2,60,10000,
            trace_widths=[.3,.5,.8,1],trace_pass_mode='adjacent',border_count=2)
        self.assertTrue(any(s.burn for s in preview_mill(out).strokes))
        self.assertEqual(out.count('M3 S10000'),1)

class ComparisonTests(unittest.TestCase):
    def test_exact_laser_geometry_and_depth_per_cut(self):
        for mode in ('compare','traces','adjacent','area'):
            for frames in (0,1,2):
                with self.subTest(mode=mode,frames=frames):
                    widths=[.3,.5,.8,1] if mode!='area' else None
                    options=dict(trace_widths=widths,trace_pass_mode='adjacent' if mode=='adjacent' else None,
                                 border_count=frames,border_width=.1)
                    args=(5,7,60,50,3,2,2,.2,.02,.06,100,200)
                    laser,_=test_pattern(*args,**options,negative=mode=='compare',negative_gap=.7)
                    out,legend=milling_test(*args,2,60,10000,1,**options,compare_widths=mode=='compare',column_gap=.7)
                    expected=[s for s in parse_nc(laser).strokes if s.burn]
                    actual=[s for s in preview_mill(out).strokes if s.burn]
                    self.assertEqual([s.points for s in expected],[s.points for s in actual])
                    self.assertEqual([s.feed for s in expected],[s.feed for s in actual])
                    depths=[-float(line.split()[1][1:]) for line in out.splitlines() if line.startswith('G1 Z')]
                    self.assertEqual(depths,[s.power for s in expected])
                    z=None
                    for line in out.splitlines():
                        if line.startswith(('G0 Z','G1 Z')): z=float(line.split()[1][1:])
                        if line.startswith('G0 X'): self.assertEqual(z,2)
                    self.assertEqual(len(legend),6)
                    self.assertEqual(out.count('M3 S10000'),1)
                    if mode=='compare':
                        self.assertIn('Sloupecek 1: W 0.3 mm / mezera 0.3 mm',out)
                        self.assertIn('Porovnani 1:1',out)
                        self.assertNotIn('laser osvituje',out)

    def test_actual_widths_equal_removed_and_retained(self):
        widths=[.3,.5,.8,1]
        out,_=milling_test(0,0,12,8,1,1,0,.2,.04,.04,100,100,2,60,10000,
                           trace_widths=widths,compare_widths=True)
        paths=[s for s in preview_mill(out).strokes if s.burn]
        starts=sorted(set(s.points[0][0] for s in paths))
        self.assertEqual(len(starts),len(widths))
        for x,w in zip(starts,widths):
            lines=[s.points[0][1] for s in paths if s.points[0][0]==x]
            n=len(negative_fill_lines(w,.2))
            last_top=0
            self.assertEqual(len(lines),int(8/(2*w))*n)
            for i in range(0,len(lines),n):
                bottom=lines[i]-.1; top=lines[i+n-1]+.1
                self.assertAlmostEqual(top-bottom,w,places=4)
                self.assertAlmostEqual(bottom-last_top,w,places=4)
                last_top=top
        changed,_=milling_test(0,0,12,8,1,1,0,.2,.04,.04,100,100,2,60,10000,
                              trace_widths=[.4,.6,.9,1.2],compare_widths=True)
        self.assertNotEqual([s.points for s in paths],[s.points for s in preview_mill(changed).strokes if s.burn])

if __name__=='__main__': unittest.main()
