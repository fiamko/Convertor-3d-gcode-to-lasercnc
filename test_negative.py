import unittest
from nc_core import NCError, negative_fill_lines, test_pattern, parse_nc


class NegativeTest(unittest.TestCase):
    def test_fixed_edges_and_centre_threshold(self):
        cases = [(0.2, [0.1]), (0.3, [0.1, 0.2]), (0.4, [0.1, 0.3]),
                 (0.4002, [0.1, 0.2001, 0.3002]), (0.5, [0.1, 0.25, 0.4]),
                 (0.8, [0.1, 0.26, 0.4, 0.54, 0.7]),
                 (1, [0.1, 0.26, 0.42, 0.58, 0.74, 0.9])]
        for width, expected in cases:
            with self.subTest(width=width):
                actual=negative_fill_lines(width,.2)
                self.assertEqual(len(actual),len(expected))
                for a,b in zip(actual,expected): self.assertAlmostEqual(a,b)
                self.assertAlmostEqual(actual[0],.1)
                self.assertAlmostEqual(actual[-1],width-.1)
                self.assertTrue(all(b-a<=.2+1e-9 for a,b in zip(actual,actual[1:])))

    def test_columns_equal_gaps_and_fixed_board_size(self):
        widths=[.3,.5,.6,1]
        text,legend=test_pattern(5,7,60,50,3,5,1,.2,30,60,1000,2000,
                                trace_widths=widths,negative=True,border_count=2,border_width=.1)
        burns=[s for s in parse_nc(text).strokes if s.burn]
        frames=[s for s in burns if s.points[0]==s.points[-1]]
        self.assertEqual(len(frames),30)
        self.assertEqual(text.splitlines().count('M5'),len(burns)+1)
        cw=(60-2)/3; ch=(50-4)/5; margin=.13
        inner_w=cw-2*margin; inner_h=ch-2*margin
        length=(inner_w-3*.5)/4
        for row in range(5):
            for col in range(3):
                xx=5+col*(cw+1)+margin; yy=7+row*(ch+1)+margin
                for i,w in enumerate(widths):
                    start=round(xx+i*(length+.5)+.1,4)
                    paths=[s for s in burns if s.points[0]!=s.points[-1] and abs(s.points[0][0]-start)<.00001 and yy<=s.points[0][1]<yy+inner_h]
                    n=len(negative_fill_lines(w,.2)); repeats=int((inner_h+1e-9)/(2*w))
                    self.assertEqual(len(paths),repeats*n)
                    last_top=None
                    for r in range(repeats):
                        sample=paths[r*n:(r+1)*n]
                        lo=sample[0].points[0][1]-.1; hi=sample[-1].points[0][1]+.1
                        self.assertAlmostEqual(lo,yy+(2*r+1)*w,places=4)
                        self.assertAlmostEqual(hi-lo,w,places=4)
                        if last_top is not None: self.assertAlmostEqual(lo-last_top,w,places=4)
                        last_top=hi
                        self.assertLessEqual(hi,yy+inner_h+.0001)
                        self.assertEqual(sample[0].feed,1000+row*250)
                        self.assertEqual(sample[0].power,30+col*15)
                    self.assertGreater(yy+(2*repeats+2)*w,yy+inner_h)
        for frame in frames:
            for x,y in frame.points:
                self.assertGreaterEqual(x-.05,5-.0001)
                self.assertLessEqual(x+.05,65+.0001)
                self.assertGreaterEqual(y-.05,7-.0001)
                self.assertLessEqual(y+.05,57+.0001)
        self.assertEqual(len(legend),15)
        self.assertIn('Plocha 60 x 50 mm',text)

    def test_counts_and_configurable_column_gap(self):
        for gap in (.5,1):
            text,_=test_pattern(0,0,12,8.2,1,1,0,.2,30,30,1000,1000,
                                trace_widths=[.6,1],negative=True,negative_gap=gap)
            paths=[s for s in parse_nc(text).strokes if s.burn]
            self.assertEqual(len(paths),6*len(negative_fill_lines(.6,.2))+4*len(negative_fill_lines(1,.2)))
            starts=sorted(set(s.points[0][0] for s in paths))
            end=next(s.points[-1][0] for s in paths if s.points[0][0]==starts[0])
            self.assertAlmostEqual(starts[1]-end-.2,gap,places=4)

    def test_invalid_dimensions(self):
        for w,d in ((.1,.2),(.3,0),(.3,float('nan')),(.3,.00001)):
            with self.subTest(w=w,d=d),self.assertRaises(NCError): negative_fill_lines(w,d)
        for widths,height,width in (([],20,10),([.3],.5,10),([.3],20,.2)):
            with self.assertRaises(NCError):
                test_pattern(0,0,width,height,1,1,0,.2,30,30,1000,1000,trace_widths=widths,negative=True)

if __name__=='__main__': unittest.main()
