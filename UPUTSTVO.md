# Divide Reader — uputstvo

Divide Reader čita sajtove, knjige i datoteke, rečenicu po rečenicu. Za svaku rečenicu broji **S**, odnosno u koliko strana govornik slaže figure iz te rečenice. Ne bira jedno tačno čitanje, nego nabraja sva koja tekst dopušta. Za svako čitanje bilježi koliko ga je od pet slušalaca čulo. Na kraju piše raport s brojkama koje se mogu porediti između sajtova ili razdoblja.

English version: [GUIDE.md](GUIDE.md)

---

## 1. Šta ti treba

- Ubuntu 22.04 ili noviji, ili Debian 12 ili noviji, na 64-bitnom računaru (amd64).
- Oko 0,5 GB prostora za program. Lokalni model traži još 3–7 GB.
- Za lokalni model barem 8 GB RAM-a. Ako ga nemaš, koristi online model.

## 2. Instalacija

1. Preuzmi `divide-reader_0.1.0_amd64.deb`:
   - sa GitHuba: stranica repozitorija → **Releases** → **v0.1.0**;
   - ili na ovom računaru, gdje već stoji u folderu `~/Desktop/Brojac Strana/`.
2. Otvori terminal u folderu gdje je datoteka i pokreni:

   ```
   sudo apt install ./divide-reader_0.1.0_amd64.deb
   ```

   `apt` sam instalira biblioteke koje programu trebaju.
3. Program se nalazi u meniju kao **Divide Reader**. Iz terminala se pokreće komandom `divide-reader`.

Program je jezički podešen na engleski. Srpski (latinica) se bira gore desno, u polju **Language**.

## 3. Prvi korak: izbor modela (kartica „1. Model“)

Model je program koji čita tekst. Ponuđene su četiri grupe.

### Ugrađeni lokalni model (llama.cpp)
- Radi bez interneta i ništa ne košta.
- **Uvijek vraća ispravan odgovor.** llama.cpp gramatikom prisiljava svaki odgovor u zadati oblik (JSON šemu). Ako odgovoru ponestane prostora prije kraja, program ga traži ponovo s više prostora.
- Na vrhu ekrana su **direktni linkovi** za preuzimanje modela i dugme **Preuzmi** pored svakog. Program sam preporuči model prema tvom RAM-u:

| Model | Veličina | RAM |
|---|---|---|
| Gemma 4 E2B | 3,1 GB | ~4 GB |
| Gemma 4 E4B | 5,0 GB | ~8 GB |
| Gemma 4 12B | 7,1 GB | ~16 GB |
| Qwen3.5 4B | 2,7 GB | ~4 GB |
| Qwen3.5 9B | 5,7 GB | ~10 GB |

- Preuzeti model se čuva u `~/.local/share/divide-reader/models/`. Program pri preuzimanju provjerava da je datoteka ispravna (SHA256).
- Ako računar ima grafičku karticu sa Vulkan drajverom (NVIDIA, AMD ili Intel), program je sam koristi. Inače radi na procesoru.
- **Brzina:** na starijem procesoru bez grafičke kartice jedan poziv modelu traje i do nekoliko minuta. Jedna rečenica traži 8 poziva. Lokalni model je zato dobar za probe, a za veće poslove je bolji online model.

### Ollama
Ako već koristiš Ollamu, ovdje se pojave tvoji modeli. Dugme **Osvježi** ponovo učitava spisak.

### Besplatni online (Gemini, Groq, Mistral, OpenRouter)
### Plaćeni online (Claude, OpenAI, Grok, OpenRouter)

**Prijava uvijek ide preko web preglednika:**
- **OpenRouter:** klikneš **Prijava**, preglednik otvori OpenRouter, odobriš pristup, i program je odmah prijavljen. Ovo je najlakši način. Preko OpenRoutera su dostupni i Claude, OpenAI i Grok.
- **Claude, OpenAI, Gemini, Groq, Mistral, Grok:** preglednik otvori stranicu dobavljača gdje se pravi API ključ. Napraviš ključ, kopiraš ga i zalijepiš u prozorčić u programu.

**Prijava važi dok ne zatvoriš program i nigdje se ne čuva.** Pri sljedećem pokretanju prijavljuješ se ponovo.

Za plaćene modele program pokazuje cijenu za milion tokena (ulaz / izlaz). Cijenu možeš ispraviti ako ju je dobavljač promijenio.

### Dugmad na dnu
- **Test na 3 rečenice:** pročita tri probne rečenice, da provjeriš da model radi i daje ispravne odgovore. Preporučujem ga pri prvom korištenju svakog modela.
- **Koristi ovaj model →:** spoji model i prebaci te na karticu za čitanje.

## 4. Čitanje (kartica „2. Čitanje“)

1. U polje **Sajt, stranica ili datoteka** upiši adresu, na primjer `https://primjer.rs`, ili klikni **Izaberi…** i izaberi PDF, EPUB, TXT ili HTML datoteku.
2. **Kako čitati:**
   - **Automatski:** program sam zaključi da li je u pitanju datoteka ili sajt.
   - **Jedna stranica:** samo ta jedna adresa.
   - **Sajt, isti domen (mjerenje):** obiđe do zadatog broja stranica na istom sajtu. Ovaj način koristi kad hoćeš da porediš sajtove.
   - **Lutanje odavde (istraživanje):** prati linkove i izvan sajta. Brojke iz lutanja nisu uporedive među sajtovima.
   - **Stari snimak (Internet Archive):** ista adresa iz izabrane godine, na primjer 2005.
3. **Jedinica:** rečenica (po pravilu), pasus, cijeli članak ili poglavlje knjige.
4. **Jedinica po izvoru:** koliko jedinica se čita. Za poređenje sajtova uzmi isti broj za svaki, na primjer 200. Nula znači sve.
5. **Granica troška:** za plaćeni model je obavezna. Program stane kad je dostigne, a sve urađeno ostaje sačuvano.
6. Ispod polja program pokazuje **procjenu** broja poziva, tokena i cijene.
7. Klikni **Pokreni**. Posao se može zaustaviti dugmetom **Zaustavi** i kasnije nastaviti dugmetom **Nastavi zadnji posao**.
8. Na kraju klikni **Otvori raport**.

Hodač poštuje pravila sajta (`robots.txt`), čeka nekoliko sekundi između zahtjeva i preskače stranice koje traže prijavu. Sve preskočene stranice su navedene u raportu.

## 5. Kako čitati raport

Raport ima pet dijelova:

1. **Šta je obiđeno:** adrese, datumi, broj stranica i jedinica, koji je model čitao.
2. **Mjere:** svaka mjera postoji u dvije verzije. U **prostoj** svako nađeno čitanje vrijedi jednako. U **teženoj** čitanje vrijedi onoliko koliko ga je slušalaca čulo.
   - **Zaključane dvojke:** rečenice s tri ili više figura kojima je S = 2 jedino čitanje. Ovo je glavna mjera.
   - **Otvorene dvojke:** S = 2 je jedno od više čitanja.
   - **Poštene dvojke:** rečenica zaista ima samo dvije figure.
   - **Raspodjela S, raspon, broj čitanja, najviši S.**
   - **Stabilnost:** koliko se poklapaju dva kruga čitanja iste rečenice. Vrijednost 1 znači isto, a 0 ništa zajedničko.
3. **Pretpostavke o tekstu:** obrasci koje model vidi u cijelom tekstu, s rečenicama koje ih podupiru i rečenicama koje im protivrječe.
4. **Čitanja po jedinicama:** svaka rečenica s figurama i do pet najčujnijih čitanja, a ostala na klik. Uz svako čitanje stoji koliko ga je slušalaca čulo („čulo 4 od 5“), pod kojom pretpostavkom važi i na koji dio teksta se oslanja.
5. **Druga brojanja:** ostalo što se u tekstu broji, na primjer vremena. Ova brojanja ne ulaze u mjere.

Uz raport (`report.html`) program pravi i `measures.csv` za tabele.

## 6. Ručno brojanje (kartica „Ručno brojanje“)

Ovo je najvažniji korak prije nego što se programu vjeruje.

1. Upiši svoje ime i izaberi izvor, ili dodaj datoteku dugmetom **Dodaj datoteku za brojanje…**.
2. Klikni **Učitaj jedinice**.
3. Za svaku rečenicu:
   - provjeri figure (jedna po redu) i ispravi ih ako treba. Dugme **Pitaj model za figure** ih može predložiti.
   - Svakoj figuri izaberi stranu, pa klikni **Dodaj ovo čitanje**.
   - Ponovi to za svako čitanje koje čuješ.
   - Klikni **Sačuvaj**.
4. Prebroji 50–100 rečenica. Program pola njih koristi kao primjere u uputstvu modelu, a drugu polovinu samo za provjeru.
5. Klikni **Provjera prema programu**. Pokrivenost (koliko tvojih S je program našao) treba biti 80% ili više.

## 7. Poređenje (kartica „Poređenje“)

Označi dva ili više izvora i klikni **Uporedi izabrane**. Raport stavlja mjere jednu pored druge. Razlika se računa kao **nalaz** samo ako je veća od razlike između dva čitanja istog izvora (šuma).

## 8. Gdje su datoteke

| Šta | Gdje |
|---|---|
| Raporti i baza (sva građa) | `~/.local/share/divide-reader/projects/default/` |
| Lokalni modeli | `~/.local/share/divide-reader/models/` |
| Podešavanja (bez ključeva) | `~/.config/divide-reader/settings.json` |
| Dnevnik lokalnog modela | `~/.local/share/divide-reader/llama-server.log` |

## 9. Komandna linija

```
divide-reader models                     # modeli i direktni linkovi
divide-reader download gemma-4-e4b       # preuzmi lokalni model
divide-reader read knjiga.epub --provider local --model gemma-4-E4B-it-Q4_K_M.gguf
divide-reader read https://primjer.rs --provider openrouter --model openrouter/free --lang sr
divide-reader read https://primjer.rs --provider claude --model claude-sonnet-5-5 --cap 5
divide-reader sources                    # spisak izvora
divide-reader report 3 4                 # uporedi izvore 3 i 4
divide-reader check                      # pokrivenost prema ručnom brojanju
```

## 10. Problemi

- **Lokalni model je vrlo spor:** to je normalno na procesoru bez grafičke kartice. Uzmi manji model (E2B) ili online model.
- **„No answer within 60 min“:** model je prespor za tu jedinicu. Program je preskače i ide dalje.
- **Prijava ne prolazi:** provjeri da je ključ kopiran cijeli. Kod OpenRoutera dovrši odobravanje u pregledniku.
- **„Rate limited“ kod besplatnih modela:** dobavljač ograničava broj poziva. Sačekaj, pa klikni **Nastavi zadnji posao**.
- **Raport je kraći nego što si očekivao:** pogledaj „Preskočene stranice“ u prvom dijelu raporta.

## 11. Uklanjanje

```
sudo apt remove divide-reader
rm -rf ~/.local/share/divide-reader ~/.config/divide-reader   # i tvoji podaci, ako hoćeš
```

---

Licenca: GPL-3.0. Ugrađeni llama.cpp: MIT.
