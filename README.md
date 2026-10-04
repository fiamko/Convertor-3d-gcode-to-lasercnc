# PrevodnikNC

![Ikona PrevodnikNC](PrevodnikNC.png)

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
