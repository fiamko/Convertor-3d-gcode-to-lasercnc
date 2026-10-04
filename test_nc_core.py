import math
from pathlib import Path
import unittest
from nc_core import NCError, parse_nc, export_nc, test_pattern, merge_drawings


def burn_segments(drawing):
    return [(a, b) for s in drawing.strokes if s.burn for a, b in zip(s.points, s.points[1:])]


class ConversionTests(unittest.TestCase):
    def test_actual_flatcam_drill_file(self):
        path = Path(__file__).parent/'fotogrmachine3-PTH.drl_cnc.nc'
        if not path.exists(): self.skipTest('Optional private drill fixture is not distributed.')
        drawing = parse_nc(path.read_text(encoding='utf-8-sig'),drill_diameter=.3)
        self.assertEqual(len(drawing.drill_points),79)
        self.assertFalse(drawing.pauses)
        result = export_nc(drawing,2000,400)
        lines = result.splitlines()
        self.assertNotIn('M0',lines)
        self.assertFalse(any(line.startswith('T') or 'Z' in line for line in lines))
        marks = [stroke for stroke in parse_nc(result).strokes if stroke.burn]
        self.assertEqual(len(marks),79)
        for (x,y),mark in zip(drawing.drill_points,marks):
            self.assertEqual(mark.points[0],mark.points[-1])
            for point in mark.points:
                self.assertLessEqual(abs(math.dist((x,y),point)-.15),.000071)
            self.assertAlmostEqual(max(p[0] for p in mark.points)-min(p[0] for p in mark.points),.3)
            self.assertAlmostEqual(max(p[1] for p in mark.points)-min(p[1] for p in mark.points),.3)

    def test_drill_marks_only_for_completed_stationary_plunges(self):
        text = ('G0 Z5\nG0 X10 Y20\nG1 Z-1\nG0 Z5\n'
                'G1 Z-2\nG0 Z5\nG0 X30 Y40\nG1 Z-1\nG0 Z5\n'
                'G0 X50 Y60\nG1 Z-1\nG1 X55\nG0 Z5\nG0 X99 Y99')
        d = parse_nc(text,drill_diameter=.3)
        self.assertEqual(d.drill_points,[(10,20),(30,40)])
        self.assertEqual(sum(s.burn for s in d.strokes),3)
        for center,stroke in zip(d.drill_points,d.strokes[-2:]):
            self.assertEqual(stroke.points[0],stroke.points[-1])
            for point in stroke.points: self.assertAlmostEqual(math.dist(center,point),.15)
        self.assertEqual(burn_segments(parse_nc(export_nc(d,2000,400)))[0],((50,60),(55,60)))
        self.assertEqual(parse_nc(text).drill_points,d.drill_points)

    def test_merge_keeps_independent_modes_and_common_transform(self):
        first = parse_nc('G0 X0 Y0\nM3 S100\nG1 X20 Y10\nM5\nM2')
        second = parse_nc('G20\nG0 Z1\nG0 X0.5 Y0.25\nG1 Z-0.1\nG0 Z1\nM30',drill_diameter=.3)
        drawing = merge_drawings([first,second])
        self.assertEqual(second.drill_points,[(12.7,6.35)])
        output = export_nc(drawing,2000,400,mirror_x=True)
        self.assertEqual(output.splitlines().count('M2'),1)
        reread = parse_nc(output)
        self.assertEqual(burn_segments(reread)[0],((20,0),(0,10)))
        mark = [s for s in reread.strokes if s.burn][-1]
        self.assertAlmostEqual((min(p[0] for p in mark.points)+max(p[0] for p in mark.points))/2,7.3)
        self.assertAlmostEqual((min(p[1] for p in mark.points)+max(p[1] for p in mark.points))/2,6.35)
        self.assertEqual(len(burn_segments(reread)),len(burn_segments(first))+len(burn_segments(second)))

    def test_cam_tool_message_pause_removed(self):
        source = ('M5\nG00 Z15.0000\nG00 X0.0000 Y0.0000\nT1\nM6    \n'
                  '(MSG, Change to Tool Dia = 0.1500)\nM0\nG00 Z15.0000\n\n'
                  'M03 S12000.0\nG1 Z-0.1\nG1 X5 Y2\nM0\nG1 X6 Y3\nM5')
        drawing = parse_nc(source)
        output = export_nc(drawing,2000,400)
        self.assertEqual(output.splitlines().count('M0'),1)
        self.assertIn('4–7',drawing.warnings[0])
        self.assertEqual(burn_segments(drawing),[((0,0),(5,2)),((5,2),(6,3))])
        self.assertEqual(burn_segments(parse_nc(output)),burn_segments(drawing))
        for gap, expected in (('\n(msg, change to tool Dia = 1)\n\n',0),
                              ('\n',1),('\n(MSG, Check workpiece)\n',1),
                              ('\n(MSG, Change to Tool Dia = 1)\nG0 X0 Y0\n',1)):
            text = 'G0 X0 Y0\nT1\nM6'+gap+'N78 M00\nM3 S100\nG1 X1'
            with self.subTest(gap=gap):
                self.assertEqual(export_nc(parse_nc(text),2000,400).splitlines().count('M0'),expected)

    def test_pause_keeps_order_and_laser_is_off(self):
        source = 'M0\nG0 X0 Y0\nM3 S100\nG1 X5\nM0\nG1 X5\nG1 Y2\nM5\nM0'
        drawing = parse_nc(source)
        output = export_nc(drawing,2000,400,rotation=90)
        self.assertEqual(output.splitlines().count('M0'),3)
        self.assertEqual(list(parse_nc(output).pauses.values()),[['M0'],['M0'],['M0']])
        on = False
        for line in output.splitlines():
            if line.startswith(('M3 ','M4 ')): on = True
            if line == 'M5': on = False
            if line == 'M0': self.assertFalse(on)
        self.assertEqual(len(burn_segments(parse_nc(output))),2)
        removed = parse_nc('T1\nM0\nM6\nG0 X0 Y0\nM3 S100\nG1 X1')
        self.assertNotIn('M0',export_nc(removed,1000,400))

    def test_tool_change_blocks_removed_before_modal_interpretation(self):
        source = 'T1\nG0 Z100\nG43 H1\nM6\nG0 X10 Y20\nM3 S100\nG1 X30 Y20\nT2\nG91\nG0 X999 Z10\nM6\nG1 Y25\nM5\nT3 M6\nM2'
        drawing = parse_nc(source)
        self.assertEqual(drawing.mode,'spindle')
        self.assertEqual(burn_segments(drawing),[((10,20),(30,20)),((30,20),(30,25))])
        self.assertEqual(len(drawing.warnings),3)
        self.assertIn('1–4',drawing.warnings[0])
        for angle in (0,90,180,270):
            out = export_nc(drawing,1000,400,True,True,rotation=angle)
            self.assertFalse(any(line.startswith('T') or line == 'M6' for line in out.splitlines()))
            self.assertEqual(len(burn_segments(parse_nc(out))),2)

    def test_unpaired_tool_commands_do_not_eat_program(self):
        source = 'T1\nG0 X0 Y0\nM3 S100\nG1 X5\nT2\nT3\nM6\nG1 Y2\nM5\nM6\nM2\nT4\nM6'
        drawing = parse_nc(source)
        self.assertEqual(burn_segments(drawing),[((0,0),(5,0)),((5,0),(5,2))])
        self.assertEqual(len(drawing.warnings),4)
        with self.assertRaisesRegex(NCError,'Řádek 6'):
            parse_nc('T1\nG43 H1\nM6\nG0 X0 Y0\nM3 S100\nG81 X1')
        for command in ('T1 X2','M6 G0 X2','T1\nM6 G0 X2'):
            with self.subTest(command=command),self.assertRaises(NCError):
                parse_nc(command+'\nG0 X0 Y0\nM3 S100\nG1 X1')

    def test_rotation_dimensions_anchor_and_direction(self):
        d = parse_nc('G0 X10 Y20\nM3 S100\nG1 X30 Y20\nY25\nX10\nY20\nM5\nG0 X8 Y18')
        for angle,size in ((0,(20,5)),(90,(5,20)),(180,(20,5)),(270,(5,20))):
            for mx,my in ((False,False),(True,False),(False,True),(True,True)):
                out = parse_nc(export_nc(d,1000,400,mx,my,rotation=angle))
                a,b,c,e = out.bounds()
                self.assertEqual((a,b),(10,20)); self.assertEqual((c-a,e-b),size)
                for before,after in zip(burn_segments(d),burn_segments(out)):
                    self.assertAlmostEqual(math.dist(*before),math.dist(*after))
        left = parse_nc(export_nc(d,1000,400,rotation=90))
        self.assertEqual(burn_segments(left)[0],((15,20),(15,40)))
        self.assertEqual(left.strokes[-1].points[-1],(17,18))
        with self.assertRaises(NCError): export_nc(d,1000,400,rotation=45)

    def test_no_redundant_rapid_or_shutdown(self):
        source = 'G0 X0 Y0\nM3 S100\nG1 X1\nM5\nG0 X2 Y2\nM3 S100\nG1 X3\nM5'
        drawing = parse_nc(source)
        output = export_nc(drawing,2000,400,laser='M4')
        self.assertEqual(output.count('G0 X2 Y2'),1)
        self.assertNotIn('M5\nM5',output)
        self.assertEqual(burn_segments(parse_nc(output)),burn_segments(drawing))
        matrix,_ = test_pattern(0,0,10,10,2,2,1,1,100,200,1000,2000)
        self.assertNotIn('M5\nM5',matrix)

    def test_z_and_modal_coordinates(self):
        source = 'G21 G90\nG0 Z5\nG0 X10 Y20\nG1 Z-0.1\nG1 X11\nY22\nG0 Z5\nG0 X15\n'
        d = parse_nc(source)
        self.assertEqual(d.mode, 'z')
        self.assertEqual(burn_segments(d), [((10,20),(11,20)),((11,20),(11,22))])
        output = export_nc(d, 1200, 400)
        self.assertNotIn('Z', output)
        self.assertEqual(burn_segments(parse_nc(output)),burn_segments(d))

    def test_laser_off_during_rapid(self):
        d = parse_nc('G0 X0 Y0\nM3 S800\nG1 X1\nG0 X2\nG1 X3\nM5\nG1 X4')
        self.assertEqual(len(burn_segments(d)),2)
        out = export_nc(d,2000,500)
        on = False
        for line in out.splitlines():
            if line.startswith('M3'): on = True
            if line == 'M5': on = False
            if line.startswith('G0'): self.assertFalse(on)
        self.assertFalse(on)

    def test_inches_relative_and_zero_power(self):
        d = parse_nc('G20 G90\nG0 X1 Y1\nM4 S10\nG91 G1 X1\nS0\nY1')
        self.assertEqual(burn_segments(d), [((25.4,25.4),(50.8,25.4))])

    def test_mirrors_keep_bounds(self):
        d = parse_nc('G0 X10 Y20\nM3 S100\nG1 X30 Y40\nX12 Y26')
        out = parse_nc(export_nc(d,1000,100,True,True))
        self.assertEqual(d.bounds(),out.bounds())
        self.assertEqual(burn_segments(out), [((30,40),(10,20)),((10,20),(28,34))])

    def test_arcs_and_full_circle(self):
        d = parse_nc('G0 X1 Y0\nM3 S10\nG3 X0 Y1 I-1 J0\nG2 I0 J-1')
        points = [p for s in d.strokes if s.burn for p in s.points]
        self.assertGreater(len(points),40)
        for p in points: self.assertAlmostEqual(math.hypot(*p),1)
        out = parse_nc(export_nc(d,1000,500,True))
        self.assertEqual(len(burn_segments(d)),len(burn_segments(out)))

    def test_reject_unsupported_and_ambiguous(self):
        for text in ('G92 X0', 'G81 X1 Y1 Z-1', 'G0 X0 Y0\nG1 X1 Z-1',
                     'G91 G0 X1 Y1','G0 X0 Y0\nM3 S100\nG2 X1 Y1 R1',
                     'G0 X0 Y0\nG1 X1','G0 X0 Y0\nM7','G0 X0 X1 Y0'):
            if text == 'G0 X0 Y0\nG1 X1':
                with self.assertRaises(NCError): export_nc(parse_nc(text),1000,100)
            else:
                with self.subTest(text=text), self.assertRaises(NCError): parse_nc(text)

    def test_comments_and_reference_header(self):
        d = parse_nc('(Laser (Spindle): 0)\n: 0.0)\nG0 X0 Y0\nM3 S10\nG1 X1 ; comment')
        self.assertEqual(len(d.warnings),1)
        self.assertEqual(len(burn_segments(d)),1)
        with self.assertRaises(NCError): parse_nc('bad header\nG0 X0 Y0')

    def test_pattern_position_parameters_and_limits(self):
        text,legend = test_pattern(85,5,30,20,3,2,2,.3,200,600,1000,2000)
        d = parse_nc(text)
        a,b,c,e = d.bounds()
        self.assertAlmostEqual(a,85); self.assertAlmostEqual(b,5)
        self.assertAlmostEqual(c,115); self.assertLessEqual(e,25)
        self.assertEqual(len(legend),6)
        self.assertEqual({s.power for s in d.strokes if s.burn},{200,400,600})
        self.assertEqual({s.feed for s in d.strokes if s.burn},{1000,2000})
        with self.assertRaises(NCError): test_pattern(0,0,1,1,3,3,2,.1,1,2,1,2)

    def test_supplied_files_preserve_every_burn_segment(self):
        files = list(Path(__file__).parent.glob('laser_*.nc'))
        if not files: self.skipTest('Optional private PCB fixtures are not distributed.')
        self.assertEqual(len(files),2)
        for path in files:
            with self.subTest(file=path.name):
                d = parse_nc(path.read_text(encoding='utf-8-sig'))
                out = parse_nc(export_nc(d,2000,800))
                self.assertEqual(d.bounds(),(-.615,-.625,80.6513,120.615))
                self.assertEqual(burn_segments(d),burn_segments(out))
                mirrored = parse_nc(export_nc(d,2000,800,True,True))
                original = burn_segments(d); flipped = burn_segments(mirrored)
                self.assertEqual(len(original),len(flipped))
                for segment, reflection in zip(original,flipped):
                    for p,q in zip(segment,reflection):
                        self.assertAlmostEqual(p[0]+q[0],80.0363,places=4)
                        self.assertAlmostEqual(p[1]+q[1],119.99,places=4)


if __name__ == '__main__': unittest.main()
