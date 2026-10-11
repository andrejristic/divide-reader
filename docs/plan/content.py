title("Divide Reader — plan softvera")
p("11. oktobar 2026. · Andrej Ristić · radni naziv ranije: Brojač strana")

h("Šta softver radi")
p("Program obilazi web stranice, za svaku rečenicu nabroji sva čitanja koja vidi (u koliko strana govornik slaže figure iz rečenice) i piše raport s najvjerovatnijim čitanjima, ostalima na zahtjev, i s brojkama uporedivim među sajtovima.")
p("Ima dvije svrhe, koje ostaju odvojene u raportu:")
b("**Istraživačka:** pokazuje do pet najvjerovatnijih čitanja, a ostala na zahtjev, bez biranja pobjednika.")
b("**Mjerna:** računa brojke nad skupovima čitanja, tako da se dva sajta ili dva razdoblja mogu uporediti.")
p("Program ne objašnjava odakle dvojke dolaze i ne ocjenjuje da li je tekst tačan. Bilježi samo koliko strana rečenica nosi u trenutku kad je izgovorena.")
p("Govornik govori očekujući da će slušalac čuti određen broj strana. Slušalac taj broj može a ne mora čuti. Program zato ne traži jedan tačan broj, nego bilježi šta različiti slušaoci čuju.")

h("Pojmovi")
p("Broj koji se broji je S: koliko odvojenih strana ostane nakon što govornik razvrsta figure iz rečenice.")
table([
    ["Pojam", "Šta znači"],
    ["Figura", "Osoba, grupa ili stvar koja u rečenici nešto čini ili trpi. Izričita je ako stoji u tekstu, pretpostavljena ako je uvodi čitanje (na primjer sud o rezultatu). Osoba koju autor citira je figura, ne govornik."],
    ["F", "Broj izričitih figura u rečenici."],
    ["Strana", "Grupa u koju govornik svrsta jednu ili više figura."],
    ["S", "Broj strana nakon razvrstavanja."],
    ["Čitanje", "Jedan način razvrstavanja. Ima tri dijela: S, pretpostavku pod kojom važi i oslonac u tekstu."],
    ["Govornik", "Cijeli izvor. Sajt je jedan govornik, knjiga je jedan govornik, i grupa autora koja piše zajedno je jedan govornik."],
    ["Slušalac", "Onaj ko čita. Svaka jedinica se čita kroz pet zadatih slušalaca (vidi Čitač). Čitanje koje čuje više slušalaca je vjerovatnije."],
    ["Poštena dvojka", "F = 2 i S = 2. U rečenici su zaista samo dvije figure."],
    ["Sabijena dvojka", "F ≥ 3 i S = 2. Građe je bilo za više, a složena je u dva tabora."],
    ["Zaključana dvojka", "Sabijena dvojka kojoj je S = 2 jedino čitanje koje tekst dopušta."],
    ["Otvorena dvojka", "S = 2 je jedno od više čitanja iste rečenice."],
    ["Drugo brojanje", "Sve što se u rečenici da brojati, a nije brojanje strana (na primjer vremena). Stoji u posebnom dijelu raporta i ne ulazi u mjere."],
])
p("Primjer: u rečenici „Ja sam napravio website“ izričite figure su ja i website. Čitanje S = 1 spaja autora i djelo. Čitanje S = 3 uvodi pretpostavljenu figuru, sud o tome kako je ispalo, i drži sve tri odvojeno.")

h("Arhitektura")
p("Pet dijelova rade jedan za drugim, a svaki svoj rezultat upisuje u zajedničko skladište (jedna SQLite datoteka).")
table([
    ["Red", "Dio", "Dobija", "Daje"],
    ["1", "Hodač", "Početne adrese i granice obilaska", "Sačuvane stranice, s datumom i otiskom sadržaja"],
    ["2", "Čistač", "Sačuvanu stranicu", "Glavni tekst bez menija i reklama, podijeljen na pasuse i rečenice, s oznakom jezika"],
    ["3", "Čitač", "Rečenicu i pasuse oko nje", "Figure, sva čitanja, druga brojanja"],
    ["4", "Sabirač", "Čitanja svih rečenica", "Mjere po stranici i sajtu, pretpostavke o tekstu"],
    ["5", "Pisac", "Čitanja, mjere, pretpostavke", "Raport"],
])
p("Jezički model koriste samo čitač i sabirač (ovaj drugi samo za pretpostavke o tekstu). Ostalo je običan kod, u Pythonu.")
p("Pošto je svaki međurezultat sačuvan, svaki dio se može pokrenuti ponovo bez prethodnih. Ista sačuvana stranica može se pročitati drugim modelom ili drugim pravilom, bez novog obilaska.")
p("Čitač može koristiti bilo koji od ponuđenih modela (vidi Modeli i spajanje), a korisnik bira na početnom ekranu. Program bilježi uz svako čitanje koji ga je model dao.")

h("Čitač")
p("Čitač je srce programa. „Sve opcije“ u njemu ima tačno značenje: sva razvrstavanja figura u strane koja tekst podržava.")
p("Po jedinici radi tri koraka:")
n([
    "**Figure.** Izvuče izričite figure tri puta i zadrži one koje se pojave barem dva puta. Figure tada dobiju stalne oznake (f0, f1, f2…) i više se ne mijenjaju. Svi slušaoci čitaju istu listu figura, pa su njihova čitanja uporediva. Pretpostavljenu figuru čitanje dodaje samo uz pretpostavku koja je uvodi, i tako je označi.",
    "**Čitanja.** Pet slušalaca, svaki u svom prolazu, kaže koja razvrstavanja tekst podržava. Za svako se upiše S, pretpostavka, oslonac u tekstu i koji su ga slušaoci čuli.",
    "**Druga brojanja.** Zapiše sve drugo što se u rečenici da brojati, s opisom šta se broji.",
])
p("Uz rečenicu čitač dobija pasus prije, pasus poslije i naslov stranice, jer mjesto govornika često nije u samoj rečenici.")
p("Jedinica čitanja je po pravilu rečenica. Korisnik je može promijeniti na pasus, cijeli članak ili poglavlje knjige. Veće jedinice imaju više figura, pa za njih češće važi postupak za F ≥ 6, u kojem potpunost nije zajamčena. Jedinica bez figura bilježi se kao S = 0, a jedinica s jednom figurom kao S = 1. Za te dvije model ne čita particije.")

h2("Pet slušalaca")
p("Svaki prolaz čita drugi slušalac. Tako raspon čitanja dolazi od različitih mjesta s kojih se tekst sluša, a ne samo od šuma modela.")
n([
    "**Neutralan posmatrač.** Čita samo ono što stoji u tekstu, s najmanje pretpostavki.",
    "**Slušalac blizak govorniku.** Čuje ono što govornik najvjerovatnije želi da se čuje.",
    "**Slušalac nesklon govorniku.** Čita sumnjičavo i traži šta govornik spaja ili prećutkuje.",
    "**Slušalac s mjesta figure.** Čita s mjesta figure koja u rečenici trpi ili nema glas.",
    "**Slušalac bez konteksta.** Dobija samo rečenicu, bez pasusa i naslova.",
])
p("Opisi slušalaca su polazni i podešavaju se nakon ručne probe. Uz svaki prolaz u skladištu stoji koji ga je slušalac dao.")

h2("Kako se zna da nijedno čitanje nije izostalo")
p("Razvrstavanje F figura u strane je particija skupa, a broj particija je Bellov broj: 2 za F = 2, 5 za F = 3, 15 za F = 4, 52 za F = 5, 203 za F = 6.")
b("**F ≤ 5:** program sam ispiše sve particije (najviše 52) i u jednom pozivu pita slušaoca koje od njih tekst podržava i čime. Lista je potpuna po konstrukciji, jer model nema šta preskočiti. Redoslijed particija se za svakog slušaoca promiješa, da model ne bi davao prednost onima na vrhu.")
b("**F ≥ 6:** particija je previše, pa svaki slušalac sam predlaže čitanja. Nema petlje do zasićenja. Potpunost tu nije zajamčena i raport to kaže uz jedinicu.")
b("**Pretpostavljene figure** nemaju gornju granicu, pa za njih uvijek važi drugi postupak.")
b("**„Više“:** na zahtjev korisnika program pokreće još jedan krug slušalaca za tu jedinicu i dopisuje nova čitanja.")
p("Svaka particija ima kanonski ključ: niz u kojem svaka figura dobija broj svoje strane, s tim da nova strana uvijek dobija sljedeći slobodan broj (na primjer 0,0,0,1 znači {f0, f1, f2} | {f3}). Isto čitanje tako uvijek ima isti ključ, pa se čitanja slušalaca, dva kruga, dva modela i ručno brojanje porede direktno. Prijedlozi za F ≥ 6 prevode se u isti oblik, uz provjeru da je svaka figura u tačno jednoj strani.")
p("Odbačene particije ostaju u skladištu s razlogom odbijanja, da se odluka može provjeriti.")

h2("Vjerovatnoća i redoslijed")
p("Vjerovatnoća čitanja je izmjerena, ne izjavljena: broj slušalaca koji su ga čuli („4 od 5“). Kod izjednačenih prednost ima čitanje s manje pretpostavki izvan teksta.")
p("Raport po jedinici prikazuje najviše pet čitanja, ovim redom:")
n([
    "Najčujnije čitanje za svaki S koji se pojavio.",
    "Ostatak do pet, po broju slušalaca.",
])
p("Ostala čitanja otvaraju se na zahtjev, grupisana po S. Pet je granica prikaza, ne granica traženja: mjere se računaju nad svim nađenim čitanjima.")

h("Hodač")
p("Hodač ima dva načina rada: obilazak zadate liste sajtova i slobodno lutanje od jedne početne adrese.")
p("Ulaz je šta god korisnik pokaže: adresa sajta, adresa jedne stranice ili tekst za preuzimanje (PDF, EPUB, TXT). Nema unaprijed zadate liste. Preuzeti tekst preskače obilazak i ide pravo čistaču.")
b("**Lista:** uzima do zadatog broja stranica po sajtu i ostaje na istom domenu. Služi mjerenju.")
b("**Lutanje:** prati linkove prema van, s budžetom (najviše stranica, najviše skokova od početka). Služi istraživanju.")
p("Pravila ponašanja: poštuje robots.txt (datoteku u kojoj sajt kaže šta roboti smiju čitati), čeka nekoliko sekundi između zahtjeva istom sajtu i predstavlja se svojim imenom (Divide Reader).")
p("Za svaku stranicu čuva adresu, datum i vrijeme, sirovi HTML, otisak sadržaja i izvučeni tekst. Raport se zato uvijek može vratiti na tačan tekst koji je čitan, i kad se stranica kasnije promijeni.")
p("Čistač izvlači glavni tekst bibliotekom trafilatura (odvaja članak od menija, reklama i podnožja), preskače stranice s premalo teksta i duplikate po otisku.")
h2("Uzorak za mjerenje")
p("Brojke su uporedive samo ako je uzorak jednak: isti broj rečenica po sajtu i isti žanr (članci, ne komentari i ne navigacija). Polazna vrijednost je 200 rečenica po sajtu.")
h2("Stari snimci")
p("Internet Archive čuva ranije verzije istih adresa. Hodač može istu stranicu uzeti iz 2005. i iz danas, što je direktna provjera pomjera li se raspodjela kroz vrijeme. Doseže do sredine 1990-ih, ne dalje.")

h("Mjere")
p("Glavna mjera je udio zaključanih dvojki među rečenicama s tri ili više figura. Sve mjere se računaju nad skupovima čitanja, ne nad jednom presudom po rečenici. Nazivnik su sve jedinice jednog izvora (jednog govornika).")
table([
    ["Mjera", "Kako se računa", "Šta govori"],
    ["Udio zaključanih dvojki", "Rečenice s F ≥ 3 kojima je S = 2 jedino čitanje, kroz sve rečenice s F ≥ 3", "Koliko često tekst sabija bez izlaza"],
    ["Udio otvorenih dvojki", "Rečenice s F ≥ 3 kojima je S = 2 jedno od više čitanja, isti nazivnik", "Koliko često dvojka stoji uz druga čitanja"],
    ["Udio poštenih dvojki", "Rečenice s F = 2 i S = 2, kroz sve rečenice", "Koliko teksta zaista ima samo dvije figure"],
    ["Raspodjela S", "Broj čitanja sa S = 0, 1, 2, 3, 4, 5 i više", "Opšta slika dvojki, trojki i četvorki"],
    ["Raspon po rečenici", "Najveći S minus najmanji S, prosjek po tekstu", "Koliko mjesta tekst nudi čitaocu"],
    ["Broj čitanja po rečenici", "Prosjek i najveća vrijednost", "Koliko je tekst otvoren"],
    ["Najviši S", "Najveći S u tekstu koji čuju barem tri od pet slušalaca", "Dokle tekst ide"],
])
p("Jedinice bez figura (S = 0) ulaze u raspodjelu S i u nazivnik „sve rečenice“. Mjere su uporedive samo među tekstovima čitanim istom jedinicom: rečenice s rečenicama, pasusi s pasusima.")
p("Svaka mjera postoji u dvije verzije: prosta, u kojoj svako nađeno čitanje vrijedi jednako, i težena brojem slušalaca. Uz svaku brojku stoje veličina uzorka i stabilnost (vidi Provjeru pouzdanosti), i iz svake se može doći do rečenica iz kojih je izračunata.")
p("U prvoj verziji nema zbirnog indeksa. Mjere stoje jedna pored druge, dok se ne vidi koja od njih zaista razlikuje tekstove.")

h("Raport")
p("Raport po sajtu ima pet dijelova, ovim redom:")
n([
    "**Šta je obiđeno.** Adrese, datumi, broj stranica i rečenica, model koji je čitao, verzija pravila.",
    "**Mjere.** Tabela mjera u obje verzije, sa stabilnošću.",
    "**Pretpostavke o tekstu.** Sve koje sabirač vidi (na primjer: „kad je tema X, figure se slažu u dva tabora“). Uz svaku stoje rečenice koje je podupiru i rečenice koje joj protivrječe.",
    "**Čitanja po rečenicama.** Svaka rečenica s figurama i do pet čitanja, poredanih po S pa po broju slušalaca. Ostala se otvaraju na zahtjev.",
    "**Druga brojanja.** Grupisana po tome šta se broji. Ne ulaze u mjere.",
])
p("Zapis jedne rečenice u dijelu 4 izgleda ovako:")
code([
    "Rečenica 14: „Sindikat, vlada i poslodavci opet su se",
    "dogovorili preko leđa radnika.“",
    "Figure (4): sindikat, vlada, poslodavci, radnici",
    "",
    "Čitanja (2 nađena od 15 mogućih):",
    "",
    "  S = 2  {sindikat, vlada, poslodavci} | {radnici}",
    "         čulo: 5 od 5 slušalaca",
    "         pretpostavka: autor govori s mjesta radnika",
    "         oslonac: „preko leđa“",
    "",
    "  S = 4  {sindikat} | {vlada} | {poslodavci} | {radnici}",
    "         čulo: 2 od 5 (neutralan, bez konteksta)",
    "         pretpostavka: autor gleda dogovor izvana,",
    "         svaka strana ima svoj razlog",
    "         oslonac: tri strane su imenovane posebno",
    "",
    "Druga brojanja:",
    "  vrijeme: „opet“ spaja ranije slučajeve i ovaj u jedno (1)",
])
p("Izlaz su tri datoteke: raport u HTML-u za čitanje, mjere u CSV-u za poređenje i sva građa u SQLite-u. Uporedni raport stavlja dva sajta ili dva razdoblja istog sajta jedno pored drugog.")

h("Modeli i spajanje")
p("Na početnom ekranu programa korisnik bira model. Ponuđene su četiri grupe:")
table([
    ["Grupa", "Šta je u njoj", "Kako se spaja"],
    ["Ugrađeni lokalni", "llama.cpp, koji dolazi u paketu programa", "Bez interneta, nakon preuzimanja modela"],
    ["Ollama", "Modeli koje korisnik već ima u Ollami", "Lokalna adresa Ollame"],
    ["Besplatni online", "Gemini, Groq, Mistral, OpenRouter (besplatni modeli)", "Prijava preko preglednika"],
    ["Plaćeni online", "Claude, OpenAI, Grok, OpenRouter", "Prijava preko preglednika"],
])
p("Na početnom ekranu, odmah vidljivo, stoje dvije stvari:")
b("**Garancija ispravnog odgovora.** Ugrađeni llama.cpp gramatikom prisiljava odgovor u zadatu JSON šemu, pa lokalni model ne može vratiti neispravan odgovor. Online modeli to ne garantuju jednako, pa program kod njih provjerava odgovor i ponavlja upit kad nije ispravan.")
b("**Direktni linkovi za lokalne modele.** Za svaki preporučeni model stoji direktan link za preuzimanje i dugme „Preuzmi“. Program preporučuje model prema količini RAM-a na mašini.")
h2("Prijava na online modele")
p("Kad korisnik na početku izabere online model, program uvijek otvori zadani web preglednik:")
b("**OpenRouter:** preglednik otvori stranicu za prijavu, korisnik odobri pristup, i pristup se sam vrati programu. Ovo je najbrži način, a preko OpenRoutera su dostupni i Claude, OpenAI i Grok.")
b("**Claude, OpenAI, Gemini, Groq, Mistral, Grok:** ovi dobavljači za programe daju samo API ključ. Preglednik otvori stranicu dobavljača na kojoj se pravi ključ, a korisnik ga zalijepi u program.")
p("Prijava važi dok je program otvoren i nigdje se ne upisuje. Pri sljedećem pokretanju radi se ponovo.")
p("Claude je ponuđen kao posebna opcija, preko svog API-ja, a ne samo preko OpenRoutera.")
h2("Brzina i trošak")
b("**Ograničenje brzine.** Besplatni nivoi imaju ograničenje broja poziva po minutu i po danu. Program čeka kad treba, nastavlja posao sutra i pokazuje koliko je ostalo.")
b("**Gornja granica troška.** Za plaćene modele korisnik prije pokretanja postavi granicu troška po poslu. Program prikaže procjenu i stane kad dostigne granicu. Urađeno ostaje sačuvano i posao se može nastaviti.")
b("**Test na tri rečenice.** Prije pravog posla dugme pokreće probu: provjerava da model vraća ispravan odgovor i da razumije jezik teksta.")

h("Program i pakovanje")
b("**Ime:** Divide Reader. Ime paketa: divide-reader.")
b("**Licenca:** GPL-3.0. Svako smije koristiti, mijenjati i dijeliti program, ali izmijenjena verzija koja se dijeli mora ostati otvorena pod istom licencom.")
b("**Jezik programa:** engleski po pravilu, srpski (latinica) kao opcija u postavkama.")
b("**Izgled:** desktop program s grafičkim sučeljem (PySide6, Qt).")
b("**Paket:** .deb za amd64, Ubuntu 22.04 i noviji, Debian 12 i noviji. Python i sve biblioteke su u paketu (u /opt/divide-reader), pa program ne zavisi od onoga što je na sistemu. arm64 možda kasnije. Windows (.exe) kasnije.")
b("**Rad na svakoj mašini:** u paketu je llama.cpp u verziji za procesor, s varijantama za starije procesore (i one bez AVX2), i u verziji za Vulkan, koja koristi grafičku karticu ako je ima (NVIDIA, AMD ili Intel). Program pri pokretanju sam izabere koju koristi.")
b("**Model nije u paketu**, jer bi paket imao više gigabajta. Preuzima se iz programa ili preko direktnog linka i čuva u ~/.local/share/divide-reader/models.")
b("**Kod:** ~/Desktop/Brojac Strana/kod, s git repozitorijem, i kopija u privatnom repozitoriju na GitHubu.")

h("Provjera pouzdanosti")
p("Programu se ne vjeruje dok se njegova čitanja ne poklope s ručnim brojanjem na uzorku i dok ponovljeno čitanje ne da isti skup.")
n([
    "**Poređenje s ručnim brojanjem.** Ti ručno prebrojiš 50 do 100 rečenica i za svaku upišeš sve S koje vidiš. Računaju se pokrivenost (u koliko rečenica je tvoj S u skupu programa) i višak (koliko čitanja programa ti odbacuješ).",
    "**Ponovljeno čitanje.** Pošto pet slušalaca namjerno čuju različito, stabilnost se ne mjeri među njima, nego između dva cijela kruga od pet slušalaca nad istom jedinicom. Skupovi se porede Jaccardovim indeksom (presjek kroz uniju: 1 znači isti skupovi, 0 ništa zajedničko). Drugi krug se radi na uzorku za provjeru i na 10% jedinica u redovnom radu. Prosjek je „stabilnost“ koja stoji uz svaku mjeru.",
    "**Dva modela.** Isti uzorak čitaju dva različita modela. Rečenice u kojima se razilaze idu na ručni pregled.",
])
p("Pola ručno prebrojanih rečenica postaje primjer u uputstvu čitaču, a druga polovina služi samo za provjeru. Na primjerima iz uputstva se ne provjerava.")
p("Razlika između dva sajta računa se kao nalaz samo ako je veća od razlike između dva čitanja istog sajta.")
p("Za ručno brojanje program ima mali alat: prikaže rečenicu i figure, a korisnik klikom složi strane. Isti alat služi za ručni pregled rečenica u kojima se modeli razilaze.")

h("Granice i rizici")
p("Najveća granica je što S stanuje u mjestu govornika, a program vidi samo tekst.")
b("**Mjesto govornika se procjenjuje.** Ton, lice i prilika ne postoje u pisanom tekstu. Zato svako čitanje nosi pretpostavku i zato program daje skup, ne presudu.")
b("**Jedan izvor, jedan govornik.** Sajt s mnogo autora čita se kao jedan glas. To je namjerno, ali razlike među autorima istog sajta se ne vide.")
b("**„Sve što vidi“ je ograničeno modelom.** Potpunost je zajamčena samo za izričite figure do F = 5.")
b("**Model ima vlastite sklonosti u čitanju**, koje se ne znaju unaprijed. Otud dva modela i ručno poređenje.")
b("**Izdvajanje figura je prvi izvor greške.** Pogrešan F pomjera sve mjere, pa se figure izvlače tri puta i provjeravaju na istom ručnom uzorku.")
b("**Jezik.** Slabiji modeli lošije čitaju srpski i hrvatski nego engleski. Stabilnost se mjeri po jeziku posebno.")
b("**Brzina.** Jedna rečenica traži tri poziva za figure i pet za slušaoce. Lokalni model na starijem procesoru bez grafičke kartice čita desetine rečenica na sat, ne hiljade (gruba procjena). Za 200 rečenica po sajtu realan je online model, a lokalni za probe.")
b("**Uzorak iz lutanja je pristrasan**, jer ide kud linkovi vode. Brojke iz lutanja nisu uporedive među sajtovima.")
b("**Sajtovi koji brane robote ili traže prijavu se preskaču**, i to stoji u raportu.")

h("Faze izgradnje")
p("Svaka faza ima uslov prolaza. Rad ide iz faze u fazu bez čekanja na odobrenje. Hodač dolazi tek kad čitač radi, jer je čitač dio koji može ne uspjeti.")
n([
    "**Jezgro.** Skladište, particije i kanonski ključevi, sloj za modele (svi dobavljači), čitač s pet slušalaca nad tekstom iz datoteke, mjere i HTML raport za jedan tekst. Prolaz: testovi prolaze, a raport se pravi iz datoteke.",
    "**Alat za ručno brojanje i ručna proba.** Ti prebrojiš 50 do 100 rečenica u alatu, a program ih čita. Prolaz: pokrivenost od 80% ili više i stabilnost 0,7 ili više.",
    "**Grafičko sučelje.** Početni ekran s modelima, prijavom, linkovima i granicom troška, pa ekran za posao. Prolaz: cijeli posao nad datotekom urađen iz sučelja.",
    "**Pakovanje.** .deb s ugrađenim llama.cpp-om. Prolaz: instalira se i radi na čistoj mašini.",
    "**Hodač i čistač.** Lista sajtova, čuvanje stranica, čistač. Prolaz: deset sajtova obiđeno bez ručnog popravljanja, tekst čist.",
    "**Uporedni raport.** CSV, dva sajta jedno pored drugog. Prolaz: barem na jednom paru razlika među sajtovima veća je od razlike među čitanjima istog sajta.",
    "**Pretpostavke o tekstu i druga brojanja** u raportu.",
    "**Lutanje i stari snimci.** Slobodan obilazak s budžetom i čitanje ranijih verzija iz Internet Archivea.",
])
p("Pragovi 80% i 0,7 su polazne vrijednosti. Podešavaju se nakon ručne probe, kad se vidi koliko se dva ručna brojanja iste osobe slažu među sobom.")

h("Odluke")
p("Potvrđeno 11. oktobra 2026.:")
b("**Jezici:** svi koje spojeni model podnosi. Srpski i engleski su obavezni, i na njima se provjerava pouzdanost.")
b("**Jedinica čitanja:** rečenica po pravilu. Korisnik je može promijeniti na pasus, cijeli članak ili poglavlje knjige.")
b("**Pretpostavljene figure:** ne broje se u F. Mjere koriste samo izričite.")
b("**Jedinice bez figura:** bilježe se kao S = 0.")
b("**Ulaz:** šta god korisnik pokaže na internetu, sajt ili tekst za preuzimanje. Nema unaprijed zadate liste.")
b("**Prikaz čitanja:** pet najvjerovatnijih po jedinici, poredanih po S pa po broju slušalaca. Ostala na zahtjev korisnika.")
b("**Govornik:** cijeli izvor je jedan govornik. Sajt, knjiga i grupa autora su po jedan govornik. Citirane osobe su figure.")
b("**Prolazi:** pet različitih slušalaca, ne pet istih prolaza.")
b("**Modeli:** ugrađeni llama.cpp, Ollama, besplatni online (Gemini, Groq, Mistral, OpenRouter) i plaćeni online (Claude, OpenAI, Grok, OpenRouter). Claude je posebna opcija.")
b("**Početni ekran:** izričito navodi JSON garanciju lokalnog modela i daje direktne linkove za preuzimanje lokalnih modela, uz dugme „Preuzmi“ i preporuku prema RAM-u.")
b("**Prijava:** online model se uvijek spaja preko zadanog preglednika. Prijava važi dok je program otvoren i ne čuva se.")
b("**Trošak:** granica troška po poslu, program staje kad je dostigne.")
b("**Upozorenje o slanju teksta online:** nema ga.")
b("**Ime i licenca:** Divide Reader, GPL-3.0.")
b("**Jezik programa:** engleski po pravilu, srpski latinica kao opcija.")
b("**Pakovanje:** .deb za amd64 prvo. arm64 možda, Windows .exe kasnije.")
b("**Kod:** lokalni git i privatni GitHub repozitorij.")
