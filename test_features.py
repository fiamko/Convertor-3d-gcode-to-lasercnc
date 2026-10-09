import unittest
from nc_core import Drawing, Stroke, drawing_statistics, check_alignment, NCError, parse_nc, test_pattern

class Features(unittest.TestCase):
    def test_statistics(self):
        d = Drawing([Stroke([(0,0),(3,4)],True,60),Stroke([(3,4),(6,8)],False),Stroke([(6,8),(6,10)],True,120)])
        self.assertEqual(drawing_statistics(d,300),(7,5,2,7))
        with self.assertRaises(NCError): drawing_statistics(d,0)
        d.strokes[0].feed = 0
        self.assertIsNone(drawing_statistics(d,300)[3])

    def test_off_feed_is_not_rapid(self):
        d = parse_nc('G0 X0 Y0\nG0 X10 Y0\nG1 X20 Y0 F60\nM3 S100\nG1 X30 Y0 F120\nM5')
        self.assertEqual(drawing_statistics(d,600),(10,20,1,16))

    def test_alignment_is_not_proof(self):
        base = Drawing([Stroke([(0,0),(10,10)],True)])
        self.assertEqual(check_alignment(base,Drawing(drill_points=[(5,5)]))[0],'amber')
        self.assertEqual(check_alignment(base,Drawing(drill_points=[(15,5)]))[0],'red')
        self.assertEqual(check_alignment(base,Drawing())[0],'gray')

    def test_horizontal_trace_matrix_preserves_widths(self):
        widths=[.3,.5,.8,1]
        text,_=test_pattern(5,7,20,14,2,2,2,.2,100,280,1000,1600,trace_widths=widths)
        drawing=parse_nc(text); lane=(6-sum(widths)-len(widths)*.2)/5
        for row in range(2):
            for col in range(2):
                xx,yy=5+col*11,7+row*8
                strokes=[s for s in drawing.strokes if s.burn and xx-.0001<=s.points[0][0]<=xx+9+.0001 and yy-.0001<=s.points[0][1]<=yy+6+.0001]
                self.assertTrue(strokes)
                ys=sorted(s.points[0][1] for s in strokes)
                large_gaps=[b-a for a,b in zip(ys,ys[1:]) if b-a>.2001]
                for a,b in zip(large_gaps,widths): self.assertAlmostEqual(a,b+.2,places=4)
                self.assertEqual(len(large_gaps),4)
                for stroke in strokes:
                    self.assertAlmostEqual(abs(stroke.points[-1][0]-stroke.points[0][0]),9)
                    self.assertEqual(stroke.points[-1][1],stroke.points[0][1])
                    self.assertEqual(stroke.power,100+180*col)
                    self.assertEqual(stroke.feed,1000+600*row)
                bottom=yy
                for width in widths:
                    a,b=bottom+lane,bottom+lane+width+.2
                    self.assertFalse(any(a+.0001<y<b-.0001 for y in ys))
                    bottom=b
        self.assertIn('(0.3 / 0.5 / 0.8 / 1)',text.split('G21')[0])
        self.assertIn('vodorovne',text)

    def test_pass_comparison_counts_spacing_widths(self):
        widths=[.3,.5,.8,1]
        text,_=test_pattern(5,7,12,10,1,1,0,.2,460,460,2600,2600,trace_widths=widths,trace_pass_mode='adjacent')
        burns=[s for s in parse_nc(text).strokes if s.burn]
        self.assertEqual(len(burns),48)
        groups={}
        for stroke in burns:
            self.assertEqual(stroke.points[0][1],stroke.points[-1][1])
            self.assertGreater(stroke.points[-1][0],stroke.points[0][0])
            self.assertEqual((stroke.power,stroke.feed),(460,2600))
            groups.setdefault(stroke.points[0][0],[]).append(stroke.points[0][1])
        self.assertEqual(len(groups),3)
        for passes,(xx,ys) in enumerate(sorted(groups.items()),1):
            self.assertEqual(len(ys),8*passes)
            self.assertEqual(len(set(ys)),len(ys))
            for index,width in enumerate(widths):
                below=ys[index*2*passes:(index*2+1)*passes]
                above=ys[(index*2+1)*passes:(index*2+2)*passes]
                for band in (below,above):
                    for a,b in zip(band,band[1:]): self.assertAlmostEqual(b-a,.16,places=4)
                self.assertAlmostEqual(above[0]-below[-1],width+.2,places=4)
                if index<3:
                    gap=ys[(index+1)*2*passes]-above[-1]-.2
                    self.assertGreaterEqual(gap,.3-.0001)
                    if passes==3: self.assertAlmostEqual(gap,.3,places=4)
            if passes==1:
                reference=[(ys[i*2]+.1,ys[i*2+1]-.1) for i in range(4)]
            else:
                for i,(bottom,top) in enumerate(reference):
                    self.assertAlmostEqual(ys[(i*2+1)*passes-1]+.1,bottom,places=4)
                    self.assertAlmostEqual(ys[(i*2+1)*passes]-.1,top,places=4)
        self.assertIn('1 / 2 / 3',text.split('G21')[0])
        self.assertEqual(text.splitlines().count('M5'),49)

    def test_nominal_half_mm_by_eight_mm_trace(self):
        text,_=test_pattern(0,0,25,4,1,1,0,.2,660,660,1800,1800,
                            trace_widths=[.5],trace_pass_mode='adjacent')
        burns=[s for s in parse_nc(text).strokes if s.burn]
        expected=((1.65,2.35),(1.49,1.65,2.35,2.51),(1.33,1.49,1.65,2.35,2.51,2.67))
        for start,ys in zip((0,8.5,17),expected):
            paths=[s for s in burns if s.points[0][0]==start]
            self.assertEqual(len(paths),len(ys))
            for path,y in zip(paths,ys):
                self.assertAlmostEqual(path.points[0][1],y,places=4)
                self.assertAlmostEqual(path.points[-1][0]-start,8,places=4)
            n=len(ys)//2
            # Half of a nominal .2 mm tool on each side leaves exactly .5 mm.
            self.assertAlmostEqual((ys[n]-.1)-(ys[n-1]+.1),.5,places=4)

    def test_perimeters_close_overlap_and_preserve_internal_bridges(self):
        for count in (1,2):
            text,_=test_pattern(5,7,30,30,3,3,2,.2,100,460,1000,2000,
                                trace_widths=[.3,.5,.8,1],trace_pass_mode='adjacent',border_count=count,border_width=.2)
            drawing=parse_nc(text)
            closed=[s for s in drawing.strokes if s.burn and s.points[0]==s.points[-1]]
            hatch=[s for s in drawing.strokes if s.burn and s.points[0]!=s.points[-1]]
            self.assertEqual(len(closed),9*count) # only whole S/F cells
            self.assertEqual(len(hatch),432)
            for index in range(0,len(closed),count):
                rings=closed[index:index+count]
                for ring in rings:
                    self.assertEqual(len(ring.points),5) # one complete lap
                    for x,y in ring.points:
                        self.assertGreaterEqual(x-.1,5-.0001); self.assertLessEqual(x+.1,35+.0001)
                        self.assertGreaterEqual(y-.1,7-.0001); self.assertLessEqual(y+.1,37+.0001)
                for inner,outer in zip(rings,rings[1:]):
                    self.assertAlmostEqual(inner.points[0][0]-outer.points[0][0],.16,places=4)
                    self.assertAlmostEqual(inner.points[0][1]-outer.points[0][1],.16,places=4)
                inner=rings[0]; left,bottom=inner.points[0]; right,top=inner.points[2]
                cell=[s for s in hatch if left-.0001<=s.points[0][0]<=right+.0001 and bottom-.0001<=s.points[0][1]<=top+.0001]
                self.assertEqual(len(cell),48)
                starts=sorted(set(s.points[0][0] for s in cell))
                ends=sorted(set(s.points[-1][0] for s in cell))
                self.assertEqual(len(starts),3)
                self.assertAlmostEqual(starts[0],left,places=4)
                self.assertAlmostEqual(ends[-1],right,places=4)
                # Vertical cuts only on the two outer sides, never at inner ends.
                for ring in rings:
                    vertical_x=[a[0] for a,b in zip(ring.points,ring.points[1:]) if a[0]==b[0]]
                    self.assertFalse(any(starts[0]+.0001<x<ends[-1]-.0001 for x in vertical_x))
                self.assertTrue(all((s.power,s.feed)==(inner.power,inner.feed) for s in cell))
            self.assertIn('prekryti stop 20 procent',text.split('G21')[0])
            self.assertIn('Vnitrni propojeni',text.split('G21')[0])

    def test_bad_perimeter_parameters_and_repeat_are_rejected(self):
        for kwargs in (dict(border_count=3),dict(border_count=4),dict(border_count=3,border_width=0),dict(border_count=3,border_width=2),dict(trace_pass_mode='repeat')):
            with self.subTest(kwargs=kwargs),self.assertRaises(NCError):
                test_pattern(0,0,30,20,3,3,2,.2,100,200,1000,2000,trace_widths=[.3,.5,.8,1],**kwargs)

    def test_trace_matrix_rejects_invalid_or_cramped_widths(self):
        for widths in ([0],[-1],[float('nan')],[float('inf')],[.1]*13,[3.3,.5,.8,1]):
            with self.subTest(widths=widths),self.assertRaises(NCError):
                test_pattern(0,0,10,10,2,2,2,.2,100,200,1000,2000,trace_widths=widths)
        for width,height in ((5,10),(10,2)):
            with self.assertRaises(NCError): test_pattern(0,0,width,height,1,1,0,.2,100,200,1000,2000,trace_widths=[.3,.5,.8,1],trace_pass_mode='adjacent')

    def test_legend_before_commands(self):
        text, legend = test_pattern(0,0,20,20,2,2,2,.3,100,200,1000,2000)
        for line in legend: self.assertLess(text.index('('+line+')'),text.index('G21'))
        self.assertTrue(parse_nc(text).strokes)

if __name__ == '__main__': unittest.main()
