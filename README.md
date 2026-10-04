# PrevodnikNC

[English](#english) · [Česky](#česky)

![PrevodnikNC icon](PrevodnikNC.png)

## English

A desktop NC/G-code converter with a Czech user interface that turns milling toolpaths into laser paths for GRBL/LaserGRBL. It was developed for PCB fabrication: removing paint around copper traces and marking positions for manual drilling. It also merges files, mirrors and rotates paths, and provides two G-code editors.

**Version 0.4 · Python + Tkinter · no third-party Python libraries.** The application only generates files; it does not connect to a machine or start the laser.

The interface is currently in Czech. The instructions below include the actual Czech button labels alongside their English meanings.

### Features

- Input and output path previews, millimetre rulers, zoom and pan.
- Conversion based on Z height or M3/M4, M5 and S power values.
- Configurable output power and feed rate, with M3/M4 selection.
- X/Y mirroring and 90°, 180° or 270° rotation.
- Multiple NC inputs combined into one output in the order they were added.
- Circular drill-position marks, with a default diameter of 0.3 mm.
- Two editors with line numbers, Ctrl+G, Ctrl+Z and error-line highlighting.
- A separate power/feed-rate test matrix generator.
- Standard open/save dialogs and protection against losing unsaved changes.

### Running the application

Windows is the primary platform. Install Python 3.10 or later with Tkinter, then run:

```console
python PrevodnikNC.py
```

On Windows, you can also double-click `spustit_PrevodnikNC.cmd`. The launcher first checks for an existing Python installation in an adjacent SVG_to_G-code project; otherwise, it uses `py -3`. That adjacent folder is not required. No packages need to be installed with pip.

The application icon is `PrevodnikNC.ico`. Select it in your shortcut's properties. The optional Windows script `vytvorit_ikonu.ps1` creates the icon and a local `PrevodnikNC.lnk` shortcut that you can copy to your desktop. The shortcut is not included in the repository because it contains an absolute path specific to the local computer.

### Your first conversion

1. Click **Otevřít NC…** (Open NC) to load an input. Use `examples/obrys.nc` to try it out.
2. Set the feed rate in mm/min and the **S** power value according to your controller configuration. S is not a percentage. The power field is intentionally blank by default.
3. Optionally select mirroring or rotation, then click **Konvert** (Convert).
4. The right-hand preview is generated from the actual output G-code.
5. Click **Uložit NC…** (Save NC) to save the contents of the right-hand editor under your chosen filename.

Before running a file on your machine, check its coordinates, dimensions, orientation and laser settings. The examples are synthetic geometry, not a calibrated process profile for a particular machine.

#### Conversion modes

- **Automaticky** (Automatic): inputs containing Z coordinates are interpreted using Z height; other inputs use laser commands.
- **Podle Z** (By Z height): G1/G2/G3 working moves are burned when Z is at or below the specified threshold. G0 moves are not burned. The output contains no Z commands.
- **Podle M3/M5 a S** (By M3/M5 and S): working moves are burned while M3/M4 is active and S > 0. Select this mode manually for laser files that only use Z to set the focus height.

The selected output feed rate and power replace the original values for all inputs. Path order is preserved. The laser is switched off before travel moves and after working paths.

### Merging files and marking drill positions

After opening the first file, click **Přidat soubor…** (Add file). Try adding `examples/vrtani.nc` to the example outline. The selector at the top switches the file shown in the left-hand editor; **Odebrat** (Remove) removes it from the assembly only. The left-hand graphical preview shows the complete assembly.

Each input is interpreted separately, including its units and modal commands. The output contains a single M2 program end, so the end of the first input does not prevent the next part from running.

**Značit vrtací vpichy Z** (Mark Z drilling plunges) detects a G1 plunge from above the Z threshold to or below it, followed by a return above the threshold with no intervening XY movement. A travel endpoint or entry into an outline cut is not treated as a hole. Repeated plunges at the same position within one file produce a single mark.

Marks are closed circles approximated by at least 32 G1 segments. Their diameter is adjustable. Marks are appended to the end of the corresponding file's paths; the log reports the number of detected positions. Drilling must be expressed as explicit NC/G-code moves: direct Excellon import and G81/G83 drilling cycles are not supported.

### Mirroring and rotation

Mirroring is performed around the centre of the combined working-path bounds. **Obrátit X** (Mirror X) swaps left and right; **Obrátit Y** (Mirror Y) swaps top and bottom.

Rotation is applied afterwards, counterclockwise. It preserves the minimum X/Y coordinates of the working-path bounds; 90° and 270° rotations swap the width and height. Travel moves receive the same transformation and may lie outside those bounds.

All inputs must use a common coordinate system and the same initial orientation. Do not combine already mirrored outlines with unmirrored drilling. The application does not automatically align files or move them inside the machine's working limits.

### Previews and editors

Use the mouse wheel to zoom and drag with the left mouse button to pan. Double-click or use **Celý výkres** (Fit entire drawing) to show the full extent. Rulers display millimetres, with Y increasing upwards. The displayed dimensions describe the working-path bounds, not necessarily the dimensions of the PCB blank.

The **Editory G-code** (G-code editors) tab lets you edit both input and output. Ctrl+A selects text, Ctrl+Z undoes changes, and Ctrl+G goes to a line. A parser error opens the relevant input and highlights the problematic line.

**Obnovit náhled** (Refresh preview) processes the editor's current text. **Konvert** reads the current text of all inputs. **Uložit jako…** (Save as) on the left saves only the selected input; the output save buttons save the exact contents of the right-hand editor, including manual changes. Previewing an unsupported command may fail, but its text can still be edited and saved.

Changing parameters or adding a file does not overwrite the right-hand editor; new output is only generated by another conversion. Unsaved changes are marked, and the application asks before discarding them. Long paths are abbreviated; hover over them to see the full path.

### Tool changes and pauses

A block from T through the next M6, inclusive, is removed before interpreting geometry. The log lists the skipped source-line range. An isolated T or M6 is removed on its own; the search for M6 stops at another T or the end of the program.

The application also recognises a `(MSG, Change to Tool…)` comment and an immediately following M0 after T or M6. This pause belongs to the tool change and is removed. Other M0 commands are preserved as pauses with the laser switched off.

### Test matrix

A separate tab generates hatched test cells within an area specified by X/Y, width and height. You can configure row/column counts, gaps, line spacing, and power/feed-rate ranges. Power increases from left to right, and feed rate increases from bottom to top. The legend is not burned; it is shown in the application and included in NC comments. The test is saved separately. You choose the available area manually.

### Supported commands and limitations

The parser supports modal G0/G1, G2/G3 arcs in the G17 plane with relative I/J centres, G20/G21, G90/G91, G91.1, G94, M3/M4/M5, standalone M0, and M2/M30 program endings. Arcs are converted to G1 segments with a maximum chord error of 0.005 mm before coordinate rounding.

The first XY position must be known and specified with G0. Simultaneous changes in XY and Z, R-format arcs, compensation commands, origin changes and drilling cycles are rejected with a line number. The application does not calculate isolation paths from Gerber files or modify the CAM Tool Diameter/Overlap settings.

### Tests

```console
python -m unittest -v test_nc_core
python test_gui_smoke.py
```

Tests cover geometry, units, mirroring, rotation, tool-change removal, pauses, drill marks, file merging, and GUI editing/saving. The GUI test requires an environment with Tk. Two additional regression tests use private manufacturing fixtures and are skipped when those files are absent. Those fixtures are not distributed.

### License

GNU General Public License v2.0 — see [LICENSE](LICENSE).

---

## Česky

Český desktopový převodník NC/G-code z frézování na laserové dráhy pro GRBL/LaserGRBL. Vznikl pro výrobu PCB: odstranění barvy kolem spojů a označení míst pro ruční vrtání. Umí také spojovat soubory, zrcadlit a otáčet dráhy a upravovat G-code ve dvou editorech.

**Verze 0.4 · Python + Tkinter · bez externích Python knihoven.** Program pouze vytváří soubory; nepřipojuje se ke stroji ani nespouští laser.

## Funkce

- Náhled vstupních a výstupních drah, pravítka v mm, zoom a posun.
- Převod podle výšky Z nebo podle M3/M4, M5 a výkonu S.
- Nastavení výstupního výkonu a rychlosti, volba M3/M4.
- Zrcadlení X/Y a otočení o 90°, 180° nebo 270°.
- Přidání více NC souborů a společný export v pořadí přidání.
- Kroužky pro označení vrtacích bodů, výchozí průměr 0,3 mm.
- Dva editory s číslováním řádků, Ctrl+G, Ctrl+Z a označením chybového řádku.
- Samostatný generátor testovací matice výkonu a rychlosti.
- Standardní dialogy otevření a uložení, ochrana neuložených změn.

## Spuštění

Primární prostředí je Windows. Nainstalujte Python 3.10 nebo novější s Tkinterem a spusťte:

```console
python PrevodnikNC.py
```

Na Windows lze použít dvojklik na `spustit_PrevodnikNC.cmd`. Spouštěč zkusí existující Python v sousedním projektu SVG_to_G-code, jinak použije `py -3`. Tato sousední složka není nutná. Není třeba instalovat žádné balíčky přes pip.

Ikona je v `PrevodnikNC.ico`. Nastavte ji ve vlastnostech svého zástupce. Volitelný skript `vytvorit_ikonu.ps1` na Windows vytvoří ikonu a místního zástupce `PrevodnikNC.lnk`, který můžete zkopírovat na plochu. Zástupce není součástí repozitáře, protože obsahuje absolutní cestu místního počítače.

## První převod

1. **Otevřít NC…** načte vstup. Pro vyzkoušení je zde `examples/obrys.nc`.
2. Nastavte rychlost v mm/min a výkon **S** podle konfigurace řadiče. S není procento. Pole výkonu je záměrně prázdné.
3. Případně nastavte zrcadlení nebo otočení a stiskněte **Konvert**.
4. Pravý náhled se načte ze skutečného vygenerovaného G-code.
5. **Uložit NC…** uloží obsah pravého editoru pod vybraným názvem.

Před použitím na stroji zkontrolujte souřadnice, rozměry, orientaci a nastavení laseru. Ukázky jsou syntetické geometrické podklady, nikoliv odladěný technologický profil konkrétního stroje.

### Režimy převodu

- **Automaticky:** vstup obsahující Z se vyhodnotí podle výšky Z; jinak podle příkazů laseru.
- **Podle Z:** pracovní pohyb G1/G2/G3 se pálí při Z menším nebo rovném zadané hranici. G0 se nepálí. Výstup neobsahuje Z.
- **Podle M3/M5 a S:** pracovní pohyb se pálí při aktivním M3/M4 a S > 0. Pro laserový soubor s nastavením Z jen pro ostření zvolte tento režim ručně.

Výstupní rychlost a výkon nahradí původní hodnoty pro všechny vstupy. Pořadí drah se zachovává. Před přejezdy a po pracovních drahách je laser vypnutý.

## Spojení souborů a značky děr

Po otevření prvního souboru použijte **Přidat soubor…**. Vyzkoušet lze přidání `examples/vrtani.nc` k ukázkovému obrysu. Seznam nahoře přepíná soubor v levém editoru; **Odebrat** jej odebere jen ze sestavy. Levý grafický náhled zobrazuje celou sestavu.

Při konverzi se každý vstup vyhodnotí samostatně, včetně jednotek a modálních příkazů. Výstup obsahuje jediný konec programu M2, takže ukončení prvního souboru nepřeruší další část.

Volba **Značit vrtací vpichy Z** rozpozná pracovní sjezd G1 z výšky nad hranicí Z na hranici nebo pod ni a následný návrat nad hranici bez pohybu XY. Pouhý konec přejezdu ani vstup do obrysového řezu se za díru nepovažují. Opakované vpichy stejného bodu v jednom souboru vytvoří jednu značku.

Značky jsou uzavřené kroužky z nejméně 32 úseček G1. Průměr je nastavitelný. Značky se přidají na konec drah příslušného souboru; počet rozpoznaných bodů se vypisuje do protokolu. Podporovány jsou vpichy rozepsané v NC/G-code, nikoliv přímý import Excellon ani vrtací cykly G81/G83.

## Zrcadlení a otočení

Zrcadlení se provede kolem středu společného rozsahu pracovních drah. **Obrátit X** převrátí levou a pravou stranu; **Obrátit Y** horní a dolní.

Otočení se provede poté, proti směru hodinových ručiček. Zachová minimum X/Y rozsahu pracovních drah; při 90° a 270° prohodí šířku a výšku. Stejnou transformací projdou přejezdy, které mohou ležet mimo tento rozsah.

Všechny vstupy musí používat společný souřadný systém a stejnou výchozí orientaci. Již zrcadlené obrysy nekombinujte s nezrcadleným vrtáním. Program soubory automaticky nezarovnává ani nepřesouvá do pracovních limitů stroje.

## Náhled a editory

Kolečkem přibližujete, levým tlačítkem táhnete obraz. Dvojklik nebo **Celý výkres** obnoví celý rozsah. Pravítka ukazují milimetry, osa Y roste nahoru. Zobrazený rozměr je rozsah pracovních drah, nikoliv automaticky rozměr laminátu.

V záložce **Editory G-code** můžete upravovat vstup i výstup. Ctrl+A vybere text, Ctrl+Z vrací změny a Ctrl+G přejde na řádek. Chyba parseru otevře příslušný vstup a zvýrazní problémové místo.

**Obnovit náhled** zpracuje aktuální text editoru. **Konvert** čte aktuální text všech vstupů. **Uložit jako…** vlevo ukládá pouze vybraný vstup; tlačítka pro uložení výstupu ukládají přesný text pravého editoru včetně ručních změn. Náhled nepodporovaného příkazu může selhat, ale jeho text lze stále editovat a uložit.

Změna parametrů ani přidání souboru nepřepíše pravý editor; nový výstup vznikne až dalším převodem. Neuložené změny jsou označené a program se před jejich zahozením zeptá. Dlouhé cesty se zkracují; najetí myší ukáže celou cestu.

## Výměny nástrojů a pauzy

Blok od T po následující M6 včetně se odstraní před vyhodnocením geometrie. Rozsah vynechaných řádků je v protokolu. Samotné T nebo M6 se vynechá jednotlivě; hledání M6 se zastaví u dalšího T nebo konce programu.

Rozpoznává se také komentář `(MSG, Change to Tool…)` a bezprostředně následující M0 za T nebo M6. Tato pauza patří k výměně nástroje a odstraní se. Ostatní M0 zůstávají jako pauzy s vypnutým laserem.

## Testovací matice

Samostatná záložka vytvoří šrafovaná políčka do plochy zadané X/Y, šířkou a výškou. Nastavit lze počet řádků/sloupců, mezery, rozteč čar, rozsah výkonů a rychlostí. Výkon roste zleva doprava, rychlost zdola nahoru. Legenda se nepálí; je dostupná v aplikaci a v komentářích NC. Test se ukládá samostatně. Volnou plochu určujete ručně.

## Podporované příkazy a omezení

Parser podporuje modální G0/G1, oblouky G2/G3 v rovině G17 s relativním středem I/J, G20/G21, G90/G91, G91.1, G94, M3/M4/M5, samostatné M0 a ukončení M2/M30. Oblouky převádí na G1 s chybou tětivy nejvýše 0,005 mm před zaokrouhlením souřadnic.

První XY poloha musí být známá a zadaná G0. Smíšený měnící se pohyb XY a Z, oblouky R, korekce, změny počátku a vrtací cykly se odmítají s číslem řádku. Program nepočítá izolační kontury z Gerberu ani nemění CAM parametry Tool Diameter/Overlap.

## Testy

```console
python -m unittest -v test_nc_core
python test_gui_smoke.py
```

Testy pokrývají geometrii, jednotky, zrcadlení, otáčení, odstranění výměn nástroje, pauzy, značení děr, spojování souborů a editaci/ukládání v GUI. GUI test vyžaduje prostředí s Tk. Dva doplňkové regresní testy používají soukromé výrobní podklady a bez nich se přeskočí. Tyto podklady nejsou distribuované.

## Licence

GNU General Public License v2.0 — viz [LICENSE](LICENSE).
