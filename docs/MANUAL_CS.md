# PrevodnikNC 0.6 — uživatelský návod

Úprava NC pro PCB, laser a CNC frézku. Program pracuje se soubory; nepřipojuje
se ke stroji a nespouští laser ani vřeteno. Rozhraní je české. Tento návod je
součástí EXE: tlačítko Návod / F1, případně klávesa F1. Escape návod zavře.

## 1. Spuštění a přenos na jiný počítač

Z vydání na GitHubu stáhněte PrevodnikNC.exe pro 64bitové Windows. Uložte jej
na disk nebo USB a spusťte přímo dvojklikem. Nepotřebuje instalaci Pythonu,
instalátor, složku _internal ani konfigurační soubor vedle EXE. Konzolové okno
se neotevírá. Návody a ikona jsou zabalené uvnitř. Zdrojový spouštěč .cmd je
určený pro vývoj, nikoli pro běžné spouštění přenosného programu.

Při spuštění se potřebné knihovny dočasně rozbalí do systémové složky TEMP;
po řádném ukončení se odstraní. První spuštění může chvíli trvat. Běžné
oprávnění k zápisu do TEMP a uživatelského profilu je potřebné. Windows může
při stahování nepodepsaného EXE zobrazit své obvyklé upozornění.

Nastavení, recepty a rozpracovaná práce se ukládají na používaném počítači do:
%APPDATA%\UpravaNC_Laser_CNC

- nastaveni.json: hodnoty polí, poslední složka a vybrané záložky;
- recepty.json: pojmenované technologické recepty;
- obnova: obnovovací kopie rozpracované práce.

Tyto soubory si aplikace vytvoří sama. Nejsou podmínkou přenosu EXE a nejsou
vázané na jeho umístění. Samotné přenesení EXE nepřenese nastavení ani NC data.
Chcete-li přenést i profil, při zavřeném programu zkopírujte uvedenou složku
do profilu druhého počítače; existující profil nejdřív zálohujte. Staré cesty
k projektům mohou vyžadovat nové otevření dat. Samotná výrobní data ukládejte
do libovolné složky, do které smíte zapisovat, například C:\My documents.
EXE neobchází ochranu složek systému Windows.

## 2. První převod

1. Otevřít NC… načte první soubor. Pro vyzkoušení slouží examples/obrys.nc.
2. Vyberte způsob vyhodnocení vstupu a výstupní technologii.
3. Nastavte posuv a výkon laseru, nebo parametry CNC uvedené níže.
4. Podle potřeby zrcadlete X/Y, otočte nebo vyřaďte kontury.
5. Konvert vytvoří pravý náhled a výstupní G-code.
6. Uložit NC… uloží skutečný obsah pravého editoru včetně ručních změn.

Levý náhled ukazuje původní geometrii modře, včetně drah vyřazených z výstupu.
Pravý náhled se čte z výsledného NC. Panely jsou vedle sebe přibližně napůl;
dělicí příčku lze ručně posunout, při změně velikosti okna se vycentruje.
Změna parametrů sama nepřepisuje již vytvořený výstup. Použijte znovu Konvert.

Výchozí názvy nového výstupu jsou projekt-grb_drl.nc pro laser a
projekt-grb_cnc.nc pro frézku. Například verze7.drl_cnc.nc se pro laser uloží
jako verze7-grb_drl.nc. Známé koncové přípony CAM se odstraní. U více vstupů
se použije projektové jméno prvního. Přípona grb_drl je dohodnutý název
laserového výstupu, nikoli záruka přítomnosti vrtání. Ručně zadaný název má
přednost a při dalším ukládání téhož výstupu zůstává zachovaný.

## 3. Jak se čte vstup

- Automaticky: pokud NC obsahuje Z, použije se vyhodnocení podle Z; jinak
  podle M3/M4, M5 a S.
- Podle Z: pracovní pohyb G1/G2/G3 je aktivní při Z menším nebo rovném
  zadané hranici. Přejezd G0 není pracovní dráha.
- Podle M3/M5 a S: dráha je pracovní při zapnutém vřetenu/laseru a S > 0.
  Použijte například pro laserový vstup, jehož Z slouží jen k ostření.

Každý přidaný soubor má vlastní jednotky a modální stav. Oblouky I/J se pro
zobrazení a výstup převádějí na úsečky. Podporováno je G0/G1, G2/G3 v G17
s relativním středem I/J, G20/G21, G90/G91, G91.1, G94, M3/M4/M5, M0 a M2/M30.
Výměny nástroje T…M6 a jejich rozpoznané hlášení Change to Tool se vynechají;
ostatní pauzy M0 zůstávají. Nepodporované příkazy a nejednoznačné pohyby se
hlásí s číslem řádku. Vrtací cykly G81/G83, oblouky R, korekce nástroje a
smíšený současný pohyb XY/Z nejsou podporované. Excellon .drl není vstupní
NC: vrtání musí být rozepsané do běžných pohybů G-code.

## 4. Laser, spojování a značení děr

Nechte CNC frézka vypnuté. Nastavte posuv XY v mm/min, výkon S podle rozsahu
řadiče a M3 nebo M4. S není procento. Výkon a posuv výstupu nahrazují původní
hodnoty. Laser se vypíná před přejezdy a po pracovních drahách; výstup nemá Z.

Přidat soubor… připojí další NC, například vrtací značky. Aktivní soubor
určuje obsah levého editoru a vstup pro Ubrat kontury. Levý grafický náhled
zobrazuje sestavu. Odebrat odstraní soubor ze sestavy, nikoli z disku. Soubory
se převedou v pořadí přidání do jednoho výstupu. Automaticky se nezarovnávají:
musí mít společný počátek a orientaci. Ke značení ručního vrtání lze vytvořit
kroužky se zadaným průměrem, výchozí 0,3 mm.

Zrcadlení probíhá kolem společného rozsahu, otočení o 90/180/270° následuje
po zrcadlení a zachovává minimum X/Y. Vyřazení kontur neposouvá původní
referenční rámec transformace.

## 5. CNC frézování

Zaškrtněte CNC frézka a nastavte:

- posuv XY: rychlost pracovní dráhy v mm/min;
- ponor: kladná hodnota pod povrch Z0, například 0,04 znamená Z-0.04;
- přejezd Z: kladná výška nad povrchem;
- posuv Z: rychlost zanoření v mm/min;
- otáčky: hodnota S pro vřeteno;
- rozběh: čekání po zapnutí vřetena v sekundách;
- vpich navíc: přídavek hloubky ke značkovacím vpichům.

Výstup zvedne Z, přejede v XY, zanoří nastaveným posuvem a projede dráhu.
Před dalším přejezdem znovu zvedne Z. Vřeteno běží po celou práci, kromě pauzy
M0 a konce. Po pauze se znovu rozběhne s nastavenou prodlevou. Při značkování
děr vytvoří svislý vpich místo laserového kroužku; skutečné provrtání desky
tím není automaticky zajištěno.

Používejte původní NC bez aplikované výškové mapy. Program výškovou mapu
nepočítá ani neaplikuje: převod nastavuje vlastní pracovní hloubku. Případný
autoleveling patří do následného zpracování nebo řídicího programu.

## 6. Ubrat kontury a pokračovat v úpravách

Vyberte aktivní NC se spoji a stiskněte Ubrat kontury…. Program najde
odpovídající Gerber mědi podle názvu; pokud není jednoznačný, nabídne výběr.
Gerber slouží k rozpoznání odstupů existujících drah od mědi, ne k tvorbě
nových CAM drah. Při přesunu projektu přeneste NC i odpovídající Gerber.

Při prvním otevření se navrhne odebrání 1 až 4 vrstev nejblíž k mědi.
Nejednoznačné dráhy se automaticky ponechávají. Návrh vždy můžete změnit:

- dvojklik přímo na čáře přepíná ponechat / odebrat;
- modrá znamená ponechat, červená přerušovaná odebrat;
- klik vybere dráhu oranžově, Delete ji vyřadí;
- dvojklik v pravé tabulce přepíná totéž; sloupec Odebrat ukazuje ANO nebo —;
- pravé tlačítko a tažení posouvá náhled, kolečko přibližuje;
- dvojklik na prázdném místě nic nemění; Celý výkres obnoví celkový pohled.

Použít a převést uloží výběr a rovnou vytvoří výstup, pokud jsou platné
parametry technologie. Pokud chybí, výběr se uloží a je třeba doplnit hodnoty
a použít Konvert. Zrušit zahodí pouze změny právě otevřeného dialogu.

Po opětovném kliknutí na Ubrat kontury se obnoví dosavadní výběr aktivního
vstupu. Můžete odstranit zapomenuté fragmenty i vrátit dříve vyřazené dráhy.
Nezačínáte od začátku. Změna počtu vrstev výslovně vytvoří nový automatický
výběr. V dialogu lze vrátit všechny dráhy; nelze potvrdit odebrání úplně všech
pracovních drah. Vrátit kontury na hlavní obrazovce zruší masku vyřazení
aktivního vstupu; nový výstup vytvořte tlačítkem Konvert.

Levý hlavní náhled zůstává modrým originálem. Je v něm zachovaný rychlý výběr
klikem/Ctrl+klikem, Delete a Ctrl+Z pro poslední ruční vyřazení. Tyto změny se
do výstupu promítnou až přes Konvert. Klik může zvýraznit odpovídající řádky
G-code. Klávesy v textovém editoru mají obvyklý textový význam.
Změna vstupního textu, režimu čtení nebo hranice Z zneplatní předchozí výběr
kontur, aby se nepoužily nesprávné indexy drah.

## 7. Porovnávací testy 1:1

Test laseru a Test frézování jsou samostatné záložky. Každá zadaná šířka W má
v každém poli vlastní sloupeček. Po výšce se střídají stejně široké plochy W
a mezery W. Šířky jsou zleva v pořadí zadání, například 0,3; 0,5; 0,8; 1.
Smyslem je porovnat zbylou měď s odebranou plochou bez přesného měření.

Nastavte počátek X/Y, celkovou šířku/výšku, počty polí, mezery polí, šířky
spojů, mezeru sloupečků a nominální stopu D. Krajní osy výplně jsou D/2 od
hran, další krok je 0,8 D. Počet obrysů celého pole je 0/1/2, jejich stopa je
samostatně nastavitelná. Rozměry plochy se automaticky nezvětšují. Pokud se
vzorek nevejde, program oznámí chybu. Neúplný horní vzorek se vynechá; zbytek
u horní hrany není porovnávací mezera.

Laser: sloupce polí mění výkon S, řádky zdola posuv. Negativní rezist je
samostatná technologická volba: zapnuto znamená osvit budoucí mědi;
vypnuto znamená odkrývání budoucích mezer v barvě / pozitivním rezistu.
Oba pásy vzoru 1:1 mají stejnou šířku, proto XY geometrie zůstává stejná a
mění se význam osvětlené plochy. Volba nepřevrací libovolný importovaný NC.

CNC: sloupce polí mění ponor, řádky zdola posuv. Otáčky jsou stejné pro celý
test, přejezdy probíhají v nastavené výšce. Rozběh testu je pevně 2 sekundy.
Není zde volba rezistu. U V-hrotu závisí skutečná šířka řezu na hloubce;
zadané šířky a stopa jsou nominální. Stejná geometrie polí je záměrná, aby
šlo porovnat různé ponory a posuvy.

Vytvořit test vytvoří náhled a editor. Každý test se ukládá samostatným
tlačítkem. Rozpis výkonu/ponoru, posuvu, šířek a počtů drah je v komentářích
NC; nezabírá místo pod náhledem a negravíruje se na desku.

## 8. Editory, recepty, obnova a ukládání

Editory mají čísla řádků, Ctrl+G pro skok, Ctrl+A a Ctrl+Z. Po ruční změně
obnovte příslušný náhled. Uložení použije přesný text editoru, i když se jej
nepodařilo zobrazit. Konvert čte vstupy z editorů a přepíše výstup po potvrzení
případných neuložených změn. Kopírovat vše pomůže uložit text jinou cestou.

Recept ukládá pojmenovanou sadu technologických parametrů s poznámkou.
Běžné nastavení polí se pamatuje při dalším spuštění. Obnovit práci načítá
časově označené kopie vstupů, výstupu, testů a výběrů. Obnova není automatické
otevření posledního projektu; zvolte příslušný soubor podle času.

Zápis NC používá dočasný soubor ve stejné cílové složce a jeho následné
nahrazení. Je proto nutné mít právo vytvářet i nahrazovat soubory v této
složce. Při neúspěchu text zůstává v editoru; použijte jinou složku nebo
Kopírovat vše. Výstup se nesmí uložit přes některý načtený vstupní NC.

Statistika času je odhad bez akcelerace a neznámého prvního příjezdu. CNC
odhad započítává i Z a prodlevu rozběhu. Nejde o čas změřený na stroji.

## 9. Meze a kontrola před výrobou

Program nenahrazuje CAM, neodesílá kód do stroje a neměří skutečnou stopu.
Zkontrolujte orientaci, počátek, rozsah plochy, jednotky, výkon/otáčky,
ponor a přejezdovou výšku. Zkušební data nejsou odladěné nastavení stroje.
Podporované Gerbery jsou omezené na geometrie, které umí místní parser;
nepodporovaný obsah se hlásí, nikoli tiše odhaduje.

Zdrojový kód a vydání: https://github.com/fiamko/Convertor-3d-gcode-to-lasercnc
Licence projektu je v přiloženém textu LICENSE a v záložce Licence návodu.
