# PrevodnikNC 0.6 — user manual

PCB toolpath editing for laser and CNC milling. The application reads and
writes files; it does not connect to a machine or start a laser or spindle.
The interface is in Czech. This manual is included in the EXE: choose
Návod / F1 or press F1. Escape closes the manual window.

## 1. Run it and move it to another computer

Download PrevodnikNC.exe for 64-bit Windows from the GitHub release. Copy it
to a drive or USB stick and double-click the EXE directly. No Python install,
installer, _internal directory or adjacent configuration file is required.
It starts without a console window. The icon and both manuals are embedded.
The source .cmd launcher is for development, not the portable application.

At startup, bundled libraries are extracted to the system TEMP directory.
They are removed after a normal exit. Startup can take a moment. Write access
to TEMP and the current user's profile is needed. Windows may display its
usual warning when an unsigned executable is downloaded.

Settings and recovery data are created automatically on the computer in use:
%APPDATA%\UpravaNC_Laser_CNC

- nastaveni.json: field values, last directory and selected tabs;
- recepty.json: named process recipes;
- obnova: recovery snapshots of work in progress.

These files are not needed beside the EXE and are independent of its location.
Moving only the EXE does not move settings or NC projects. To move the profile
as well, close the application and copy this directory to the other user's
profile, backing up any existing profile first. Old project paths may require
reopening the data. Store manufacturing files in any writable directory, for
example C:\My documents. The application does not bypass Windows folder
protection.

## 2. First conversion

1. Otevřít NC… (Open NC) loads the first file. Try examples/obrys.nc.
2. Choose the input interpretation mode and output technology.
3. Enter laser feed and power, or the CNC settings described below.
4. Optionally mirror, rotate or exclude contours.
5. Konvert creates the right preview and output G-code.
6. Uložit NC… (Save NC) saves the actual right editor text, including edits.

The left preview shows the original geometry in blue, including paths excluded
from output. The right preview is parsed from the generated NC. The panes are
approximately equal in width. The divider can be dragged; resizing the window
centres it again. Changing settings does not overwrite existing output: use
Konvert again.

Suggested new output names are project-grb_drl.nc for laser and
project-grb_cnc.nc for milling. For example, verze7.drl_cnc.nc becomes
verze7-grb_drl.nc for laser. Known trailing CAM suffixes are removed. For
multiple inputs, the first input supplies the project name. grb_drl is the
agreed laser naming convention, not a guarantee that drilling is present.
You can choose another name; subsequent saves of the same output retain it.

## 3. Input interpretation

- Automaticky (Automatic): use Z-based interpretation when Z is present;
  otherwise use M3/M4, M5 and S.
- Podle Z (By Z): G1/G2/G3 is working motion at or below the configured Z
  threshold. G0 is travel, not cutting.
- Podle M3/M5 a S: working motion requires an active spindle/laser and S > 0.
  Use this for laser inputs where Z is only a focus adjustment.

Each added input has independent units and modal state. I/J arcs are converted
to line segments for display and output. Supported commands include G0/G1,
G2/G3 in G17 with relative I/J centres, G20/G21, G90/G91, G91.1, G94,
M3/M4/M5, M0 and M2/M30. Tool changes T…M6 and their recognised Change to Tool
messages are removed; other M0 pauses remain. Unsupported commands and
ambiguous moves report a line number. G81/G83 drilling cycles, R arcs, cutter
compensation and simultaneous changing XY/Z motion are not supported.
An Excellon .drl is not an NC input: drilling must be expanded into ordinary
G-code moves.

## 4. Laser output, merged files and drill marks

Leave CNC frézka unchecked. Set XY feed in mm/min, S power according to your
controller's range, and M3 or M4. S is not a percentage. The output feed and
power replace the input values. The laser is turned off before travel and
after working paths. Laser output contains no Z commands.

Přidat soubor… (Add file) adds another NC, such as drill marks. The active-file
selector determines the left editor and the source used by Ubrat kontury.
The left graphical preview shows the assembly. Odebrat removes an input from
the assembly, not from disk. Inputs are exported in their added order into
one program. They are not automatically aligned and must share an origin
and orientation. Manual drill positions can be marked with circles of the
chosen diameter, initially 0.3 mm.

Mirroring uses the common bounds. Rotation by 90/180/270 degrees follows
mirroring and preserves the minimum X/Y position. Excluding contours does not
shift the original transformation reference frame.

## 5. CNC milling

Check CNC frézka and set:

- XY feed: cutting feed in mm/min;
- Ponor: positive depth below surface Z0; 0.04 produces Z-0.04;
- Přejezd Z: positive travel height above the surface;
- Posuv Z: plunge feed in mm/min;
- Otáčky: spindle S value;
- Rozběh: spindle startup delay in seconds;
- Vpich navíc: additional depth for marking plunges.

The output lifts Z, travels in XY, plunges at the configured Z feed, follows
the working path and retracts before the next travel. The spindle stays on
throughout the job except at M0 pauses and program end. After a pause it
restarts with the specified delay. Drill marking makes vertical plunges
instead of laser circles; it does not automatically drill through the board.

Use source NC before height compensation. This application neither calculates
nor applies a height map: conversion assigns its own working depth. Any
required autoleveling belongs in a subsequent processing step or controller.

## 6. Remove contours and resume editing

Select the active track NC and click Ubrat kontury… (Remove contours). The
application looks for a matching copper Gerber by name and asks you to choose
if the match is ambiguous. The Gerber identifies distances from existing paths
to copper; it does not generate new CAM toolpaths. Move the corresponding
Gerber along with the NC when relocating a project.

On first opening, the dialog suggests removing 1–4 layers closest to copper.
Ambiguous paths are kept automatically. You can adjust the proposal:

- Double-click a path to toggle keep / exclude.
- Blue means keep; dashed red means exclude.
- A single click selects in orange; Delete excludes the selected path.
- Double-click a table row to toggle the same setting. Odebrat shows ANO
  (yes) or — (keep).
- Drag with the right mouse button to pan; use the wheel to zoom.
- Double-clicking empty space does nothing. Celý výkres fits the whole drawing.

Použít a převést (Apply and convert) stores the selection and generates output
when the process settings are valid. Otherwise the selection is stored; fill
in the required settings and press Konvert. Zrušit cancels the changes made
in the currently open dialog.

Reopening Ubrat kontury restores the current input's previous exclusions.
Continue removing missed fragments or restore excluded paths without starting
over. Explicitly changing the layer count creates a new automatic proposal.
You may restore all paths, but cannot confirm removing every working path.
Vrátit kontury on the main screen clears the active input's exclusion mask;
use Konvert to regenerate output.

The main left preview remains the original blue geometry. It still supports
click/Ctrl+click selection, Delete and Ctrl+Z to undo the last manual exclusion.
These changes affect output only after Konvert. A click can highlight matching
G-code lines. In text editors, keys retain their normal text-editing meaning.
Changing input text, interpretation mode or Z threshold invalidates the old
contour selection so stale path indices cannot be applied.

## 7. Equal-width comparison tests

Test laseru and Test frézování are separate tabs. Every requested width W gets
its own subcolumn in each parameter cell. Equal-height bars W and gaps W
alternate vertically. Widths appear left to right in the entered order,
for example 0.3; 0.5; 0.8; 1. This lets you compare retained copper with cleared
areas without precise width measurement.

Set the X/Y origin, total width/height, cell counts, cell gaps, trace widths,
subcolumn gap and nominal footprint D. Edge fill centres are D/2 inside each
bar; the fill step is 0.8 D. Choose 0/1/2 whole-cell frames with a separate
nominal frame footprint. Board dimensions are never enlarged automatically.
Impossible settings produce an error. Incomplete top bars are omitted; the
remaining top space is not a comparison gap.

Laser: cell columns vary S power; rows increase feed from bottom to top.
Negativní rezist is an independent technology option. Checked: exposed bars
become copper. Unchecked: laser exposure removes paint / positive resist in
future gaps. Both bands have equal width in a 1:1 pattern, so the XY geometry
is the same while the meaning of exposed areas changes. This option does not
invert arbitrary imported NC.

CNC: cell columns vary depth and rows vary feed. RPM is constant across the
test; travel uses the chosen safe Z. The test's startup delay is fixed at
2 seconds. There is no resist option. A V-bit's actual cut width depends on
depth; the entered widths and footprint are nominal. Repeated XY geometry
across cells is intentional so depth and feed effects can be compared.

Vytvořit test creates the preview and editable G-code. Each tab has its own
test save button. Power/depth, feed, widths and path counts are recorded in
NC comments; they do not occupy a panel below the preview or get engraved.

## 8. Editors, recipes, recovery and saving

Editors provide line numbers, Ctrl+G navigation, Ctrl+A and Ctrl+Z. Refresh the
relevant preview after manual edits. Saving uses the exact editor text even
if preview parsing failed. Konvert reads input editor text and replaces the
output after any required unsaved-change confirmation. Kopírovat vše (Copy all)
lets you preserve the text through another application.

A recipe stores named process settings and a note. Ordinary field settings
persist across restarts. Obnovit práci (Recover work) reads timestamped
snapshots containing inputs, output, tests and selections. Recovery is not
automatic reopening of the previous project: choose the appropriate snapshot.

NC saving writes a temporary file in the destination directory and then
replaces the target. You therefore need permission to create and replace files
there. If saving fails, text stays in the editor: use another directory or
Copy all. Output cannot overwrite an input NC currently loaded in the project.

Time statistics are estimates without acceleration or unknown initial travel.
The CNC estimate also includes Z motion and spindle startup delay. These are
not measured machine run times.

## 9. Limits and checks before machining

This application is not a CAM replacement or machine sender and cannot measure
the actual tool footprint. Check orientation, origin, occupied area, units,
power/RPM, depth and safe travel height. Example inputs are synthetic geometry,
not calibrated machine settings. Copper Gerber support is limited to shapes
understood by the local parser; unsupported content is reported, not guessed.

Source and releases: https://github.com/fiamko/Convertor-3d-gcode-to-lasercnc
The project licence is provided in LICENSE and in the manual's Licence tab.
