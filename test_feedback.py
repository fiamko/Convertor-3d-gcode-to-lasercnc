import unittest
from nc_core import parse_nc
from milling_core import export_mill,preview_mill

DRILLS="""G21
G90
G0 Z2
G0 X3 Y4
G1 Z-2 F60
G0 Z2
G0 X8 Y9
G1 Z-2
G0 Z2
M2
"""

class MarkingTests(unittest.TestCase):
 def test_plunges_only_extra_and_transform(self):
  d=parse_nc(DRILLS)
  out=export_mill(d,200,.04,2,60,10000,mark_drills=True,drill_extra=.1)
  self.assertEqual(out.count('G1 Z-0.14 F60'),2)
  self.assertFalse(any(line.startswith('G1 X') or line.startswith('G1 Y') for line in out.splitlines()))
  self.assertEqual(preview_mill(out).drill_points,[(3,4),(8,9)])
  flipped=export_mill(d,200,.04,2,60,10000,mark_drills=True,mirror_x=True)
  self.assertEqual(preview_mill(flipped).drill_points,[(8,4),(3,9)])
  self.assertEqual(flipped.count('G1 Z-0.04 F60'),2)
 def test_laser_still_generates_circles(self):
  d=parse_nc(DRILLS,drill_diameter=.3)
  self.assertEqual(sum(s.burn for s in d.strokes),2)
  self.assertTrue(all(len(s.points)>=33 for s in d.strokes if s.burn))
 def test_source_lines(self):
  d=parse_nc('G0 X0 Y0\nM3 S10\nG1 X10 F100\nG1 Y10\nM5\n')
  self.assertEqual(next(s.source_lines for s in d.strokes if s.burn),[3,4])
if __name__=='__main__': unittest.main()
