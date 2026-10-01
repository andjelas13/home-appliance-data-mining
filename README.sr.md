# Analiza tržišta bele tehnike: istraživanje podataka na dve srpske internet prodavnice

**Projekat iz predmeta** — Univerzitet u Beogradu, Elektrotehnički fakultet, predmet *Pronalaženje skrivenog znanja* (engl. Knowledge Discovery / Data Mining), školska godina 2025/26.

Autor: Anđela Spasić

*Engleska verzija: [README.md](README.md)*

Podaci o proizvodima bele tehnike (veliki i mali kućni aparati, klima-uređaji i televizori) prikupljeni su sa dve srpske internet prodavnice, gigatron.rs i winwin.rs, prečišćeni i upisani u drugu bazu, analizirani SQL upitima i grafikonima, i iskorišćeni za izradu tri modela napisana bez biblioteka za mašinsko učenje: višestruke linearne regresije obučene gradijentnim spustom (predviđanje cene), algoritma K-means sa k-means++ inicijalizacijom i težinama obeležja koje bira korisnik, i sistema preporuka zasnovanog na sadržaju (TF-IDF, one-hot kodiran brend i standardizovana numerička obeležja, poređeni kosinusnom sličnošću). Sva tri modela dostupna su kroz desktop prozor napisan u tkinter-u. scikit-learn se pojavljuje u samo jednom fajlu, radi provere ručno napisanih implementacija.

Identifikatori u kodu, komentari, natpisi na grafikonima i izveštaj su na srpskom jeziku.

## Šta projekat radi

1. **Preuzimanje** — čita URL adrese proizvoda iz mapa sajta (sitemap) prodavnica i svaku stranicu proizvoda čuva na disku (gzip), uz poštovanje fajla robots.txt i pauze između zahteva.
2. **Parsiranje** — dva parsera, po jedan za platformu svake prodavnice, pretvaraju sačuvane stranice u redove primarne PostgreSQL baze; karakteristike se čuvaju kao parovi naziv–vrednost, tačno onako kako su napisane na sajtu.
3. **Prečišćavanje** — preslikava kategorije i brendove u kontrolisane rečnike, izdvaja brojeve i jedinice iz teksta, razdvaja dve skale energetskih oznaka, spaja isti uređaj iz obe prodavnice u jedan red i rezultat upisuje u drugu, prečišćenu bazu.
4. **Upiti** — sedam SQL naredbi nad prečišćenom bazom, koje odgovaraju na pet pitanja, sa izvozom u Excel.
5. **Vizuelizacija** — stubičasti grafikoni kategorija, brendova, cenovnih opsega i energetskih klasa, pri čemu su na svakom stubiću ispisani broj i procenat.
6. **Modeli** — regresija cene, klasterovanje i preporuke, svaki implementiran ručno.
7. **Upotreba** — desktop aplikacija sa tri kartice: predviđanje cene, klasterovanje, preporuke.

U kodu, zaglavljima fajlova i izveštaju ove faze se nazivaju po brojevima zadataka iz teksta projekta: *Zadatak 1* (prikupljanje podataka), *Zadatak 2* (čišćenje i SQL analiza), *Zadatak 3* (vizuelizacija), *Zadatak 4* (regresija), *Zadatak 5* (klasterovanje) i *Zadatak 6* (preporuke).

## Rezultati

| Faza | Rezultat |
|---|---|
| Preuzete stranice | 53.482 od 53.551 zahteva (69 neuspešnih, svi HTTP 404) |
| Proizvodi u primarnoj bazi | 15.949 (winwin.rs 9.634, gigatron.rs 6.315), sa 300.688 zapisa o karakteristikama |
| Proizvodi posle prečišćavanja i spajanja | 11.984 (75,1 %) |
| Kategorije uređaja | 38 |
| Proizvođači | 197 (svedeno sa 260 načina pisanja brenda među zadržanim proizvodima) |
| Uređaji pronađeni u obe prodavnice | 1.244 (donja granica) |
| Regresija cene, test skup (2.397 proizvoda) | R² 0,850 u logaritamskom prostoru, 0,646 u RSD; RMSE 58.226 RSD; MAE 21.782 RSD; medijalna greška 21,4 %; MAPE 32,6 % |
| Primer za K-means | 1.112 frižidera, K = 4, težine cena 50 % / zapremina 30 % / energetska klasa 20 %: Silhouette 0,407, inercija 339,7, konvergencija u 14 iteracija |
| Primeri preporuka | Midea klima-uređaj: sličnosti od 0,6130 do 0,5417; Gorenje frižider: od 0,7596 do 0,7587 |

Odgovori na pet pitanja, iz prečišćenih podataka (potpuni rezultati su u `izvestaj/rezultati_upita.xlsx`):

| Pitanje | Odgovor |
|---|---|
| Broj proizvoda po kategoriji | 38 kategorija; najveće su televizori (1.895), frižideri (1.464), mašine za pranje veša (856), usisivači (821) |
| Deset najzastupljenijih brendova | Gorenje (1.384), Bosch (1.215), Beko (1.148), VOX (989), LG (844), Samsung (622), Philips (468), Candy (416), Miele (287), Hisense (273); ukupno 7.646 proizvoda (63,8 %) |
| Energetska klasa C (ili A+ na staroj skali) ili bolja | 2.518 od 7.343 proizvoda sa poznatom klasom i skalom (34,3 %) |
| Cena do 50.000 RSD | 7.061 proizvod (58,9 %) |
| 30 najskupljih televizora | najskuplji je Samsung QE98QN100BTXXH, po ceni od 3.779.999 RSD |

Cenovni opsezi: 35,6 % proizvoda košta do 30.000 RSD, 49,2 % između 30.001 i 100.000, 12,9 % više od 100.000 a manje od 300.000, dok 2,3 % košta 300.000 ili više. Televizori i frižideri zajedno čine 28,0 % prečišćene baze. Za 4.641 proizvod (38,7 %) energetska klasa nije navedena.

## Tri modela

Sva tri modela čitaju prečišćenu bazu. numpy i pandas koriste se za nizove i tabele, a matplotlib za grafikone; za obučavanje se ne koristi nijedna biblioteka.

### Višestruka linearna regresija (predviđanje cene)

Ručno su napisani: funkcija gubitka, njen gradijent, petlja gradijentnog spusta, predviđanje, one-hot kodiranje, standardizacija, podela na skup za obučavanje i test skup i sve mere kvaliteta.

```
ŷ = θ₀ + θ₁x₁ + θ₂x₂ + … + θₙxₙ
J(θ) = (1/2m) · Σ(ŷ − y)²  +  (λ/2m) · Σθⱼ²        (j ≥ 1)
∂J/∂θ = (1/m) · Xᵀ(Xθ − y)  +  (λ/m) · θ'          (θ'₀ = 0)
θ := θ − α · ∂J/∂θ
```

```
R² = 1 − Σ(y − ŷ)² / Σ(y − ȳ)²
RMSE = √( prosek((y − ŷ)²) )
MAE = prosek(|y − ŷ|)
MAPE = prosek(|y − ŷ| / y) · 100
medijalna APE = medijana(|y − ŷ| / y) · 100
```

Obeležja: kategorija, brend i skala energetske oznake kao one-hot kolone (brendovi sa manje od 15 proizvoda grupisani su kao „ostalo“), energetski rang i numeričke tehničke karakteristike. Sa indikatorima nedostajućih vrednosti i interakcijama opisanim u nastavku, konačna matrica obeležja ima 785 kolona: 17 numeričkih kolona, 17 indikatora, 105 one-hot kolona i 646 interakcija.

Odluke u projektovanju:

- **Logaritam cene kao ciljna promenljiva.** Cene se kreću od 699 do 3.779.999 RSD, pa bi na sirovim cenama najskuplji uređaji dominirali kvadratnom greškom. Model uči log(cena), a predviđanje se vraća kao exp(Xθ). Pri istim podešavanjima MAPE pada sa 74,8 % na 35,7 %, a predviđanja su uvek pozitivna; bez logaritma je 159 od 2.397 test uređaja dobilo cenu nula ili manju.
- **Interakcije.** Svaka numerička karakteristika množi se indikatorom kategorije, pa model uči poseban nagib za svaku kategoriju: litar zapremine ne vredi isto kod frižidera i kod kuvala za vodu. Kolona se prvo standardizuje, pa tek onda množi; standardizacija već pomnožene kolone, koja se gotovo cela sastoji od nula, dala bi ogromne vrednosti i gradijentni spust bi divergirao. Bez interakcija R² (log) iznosi 0,797, a medijalna greška 25,9 %; sa njima 0,826 i 23,5 %.
- **Popunjavanje medijanom.** Prazno polje dobija medijanu svoje kategorije (ili svih proizvoda ako kategorija nema nijednu vrednost te karakteristike), uz indikatorsku kolonu koja beleži da je vrednost nedostajala. Medijanu ne pomera nekoliko skupih uređaja.
- **Standardizacija.** z = (x − srednja vrednost) / standardna devijacija, jer se zapremina meri stotinama litara, a energetski rang ide od 1 do 8. Svi parametri određuju se samo na skupu za obučavanje.

Podela 80:20 sa semenom 2026: 9.587 proizvoda u skupu za obučavanje i 2.397 u test skupu. Eksperimenti (mere na test skupu):

| α | Iteracije | λ | log(cena) | Interakcije | R² (log) | Medijalna greška | MAPE | RMSE (RSD) |
|---|---|---|---|---|---|---|---|---|
| 0,001 | 3.000 | 0 | da | da | 0,5193 | 42,7 % | 70,9 % | 101.225 |
| 0,01 | 3.000 | 0 | da | da | 0,7266 | 31,2 % | 47,5 % | 69.946 |
| 0,1 | 3.000 | 0 | da | da | 0,8264 | 23,5 % | 35,7 % | 58.142 |
| 0,3 | 3.000 | 0 | da | da | divergirao posle 449 iteracija | – | – | – |
| 0,1 | 10.000 | 0 | da | da | 0,8437 | 22,0 % | 33,4 % | 59.551 |
| 0,1 | 3.000 | 1 | da | da | 0,8260 | 23,5 % | 35,8 % | 58.039 |
| 0,1 | 3.000 | 10 | da | da | 0,8228 | 23,9 % | 36,1 % | 57.373 |
| 0,1 | 3.000 | 0 | ne | da | nije definisan | 38,2 % | 74,8 % | 60.100 |
| 0,1 | 3.000 | 0 | da | ne | 0,7966 | 25,9 % | 39,2 % | 63.676 |

L2 regularizacija ne pomaže: gradijentni spust koji polazi od nule i izvršava ograničen broj iteracija već deluje kao blaga regularizacija. Pošto R² (log) nastavlja da raste sa brojem iteracija, konačni model koristi α = 0,1, λ = 0 i 25.000 iteracija:

| Mera | Skup za obučavanje | Test skup |
|---|---|---|
| R² (logaritamski prostor) | 0,8615 | 0,8502 |
| R² (RSD) | 0,6290 | 0,6462 |
| RMSE | 63.063 RSD | 58.226 RSD |
| MAE | – | 21.782 RSD |
| MAPE | – | 32,6 % |
| Medijalna procentualna greška | – | 21,4 % |

Mere na skupu za obučavanje i na test skupu su bliske, pa model nije preobučen. R² u RSD je niži zato što model minimizuje relativnu grešku, a ista relativna greška na skupom televizoru predstavlja veoma veliku kvadratnu grešku u dinarima. Iz istog razloga je RMSE 2,7 puta veći od MAE: deset najvećih promašaja čini 47 % zbira kvadrata.

![Predviđena i stvarna cena na test skupu, logaritamske ose](izvestaj/grafikoni/08_predvidjeno_stvarno.png)

*Predviđena i stvarna cena na test skupu. Ose su logaritamske, pa jednako rastojanje od dijagonale znači jednaku relativnu grešku.*

### K-means klasterovanje

Ručno su napisani: k-means++ inicijalizacija, dodela tačaka i ažuriranje centara, inercija, Silhouette koeficijent i kratak generisani opis svakog klastera.

Korisnik bira obeležja, težinu za svako od njih i K. Proizvodi kojima nedostaje bilo koja od izabranih vrednosti se izostavljaju. Kolone se standardizuju, težine se normalizuju tako da im je zbir 1 (50 i 30 znače isto što i 62,5 i 37,5), a svaka kolona se množi kvadratnim korenom svoje težine, tako da u kvadratu euklidskog rastojanja težina deluje tačno kao izabrani udeo:

```
d² = Σ wⱼ · (xⱼ − cⱼ)²  =  Σ (√wⱼ·xⱼ − √wⱼ·cⱼ)²
inercija = Σ ‖xᵢ − c(i)‖²
s = (b − a) / max(a, b)
```

U formuli za Silhouette *a* je srednje rastojanje tačke do tačaka sopstvenog klastera, a *b* najmanje srednje rastojanje do nekog drugog klastera. Koeficijent se računa na uzorku od 2.000 tačaka samo kada tačaka ima više od toga.

- **k-means++.** Prvi centar je slučajan; svaki sledeći se bira sa verovatnoćom srazmernom kvadratu rastojanja do najbližeg već izabranog centra.
- **Deset pokretanja.** Algoritam se izvršava deset puta, sa semenima od 2026 do 2035, i zadržava se rešenje sa najmanjom inercijom, jer k-means++ i dalje može da završi u lošijem lokalnom minimumu: za K = 4 prvo pokretanje daje inerciju 364,85, a najbolje 339,72.
- **Zaustavljanje.** Pokretanje se zaustavlja kada se dodela tačaka klasterima više ne menja (ili posle 300 iteracija).

Primer: frižideri, sa težinama cena 50 %, zapremina 30 %, energetska klasa 20 % (najbolje od deset pokretanja za svako K):

| K | Inercija | Silhouette |
|---|---|---|
| 2 | 635,28 | 0,495 |
| 3 | 467,25 | 0,325 |
| 4 | 339,72 | 0,407 |
| 5 | 271,33 | 0,371 |
| 6 | 231,82 | 0,367 |
| 7 | 201,27 | 0,372 |
| 8 | 179,09 | 0,341 |
| 9 | 162,97 | 0,345 |
| 10 | 148,11 | 0,328 |

![Inercija i Silhouette koeficijent za frižidere, K od 2 do 10](izvestaj/grafikoni/10_kmeans_lakat.png)

Inercija uvek opada, pa se K ne može izabrati samo na osnovu nje. K = 2 ima najveći Silhouette (0,495), ali samo razdvaja velike, skupe frižidere od svih ostalih. Od K = 3 naviše najbolja vrednost je K = 4 (0,407), i ona je uzeta za primer. Kriva nema izražen lakat, ali pad sa 3 na 4 klastera iznosi 127,5, a sa 4 na 5 samo 68,4.

| Klaster | Proizvoda | Udeo | Prosečna cena | Na staroj skali oznaka | Opis |
|---|---|---|---|---|---|
| 0 | 546 | 49,1 % | 50.370 RSD | 4 | jeftiniji uređaji, najčešće klasa E na novoj skali |
| 1 | 306 | 27,5 % | 61.924 RSD | 231 | uređaji srednje cene, mešovite skale, najčešće A+ na staroj skali |
| 3 | 209 | 18,8 % | 126.471 RSD | 20 | skuplji, veće zapremine, najčešće E na novoj skali |
| 2 | 51 | 4,6 % | 306.069 RSD | 4 | znatno skuplji, znatno veće zapremine, najčešće F na novoj skali |

Silhouette od 0,407 ukazuje na slabu strukturu: grupe se razlikuju, ali se na granicama preklapaju, jer cena i zapremina frižidera rastu postepeno. Klasterovanje pokazuje i da klastere 0 i 1, koji su bliski po ceni, razdvaja uglavnom skala energetske oznake: 231 od 306 frižidera u klasteru 1 nosi staru skalu, naspram 4 od 546 u klasteru 0. Rang se računa unutar skale, pa su staro A+ (rang 3) i novo E (rang 5) međusobno daleko. Zbog toga opis klastera uvek navodi klasu zajedno sa njenom skalom, a ispisuje „mešovito“ kada nijedna skala ne pokriva 80 % klastera.

### Sistem preporuka zasnovan na sadržaju

Za izabrani proizvod sistem vraća pet najsličnijih proizvoda iz iste kategorije. Ručno su napisani: TF-IDF, one-hot kodiranje brenda i kosinusna sličnost, uključujući skalarni proizvod i norme vektora. Skalarni proizvod je obična petlja, bez `numpy.dot` i bez operatora `@`.

```
tf(t,d) = broj pojavljivanja reči t u nazivu d / broj reči u d
idf(t)  = ln( N / (1 + df(t)) ) + 1

a · b    = a₁·b₁ + a₂·b₂ + … + aₙ·bₙ
‖a‖      = √(a · a)
cos(a,b) = (a · b) / (‖a‖ · ‖b‖)
```

Profil proizvoda ima tri bloka, koji se grade zasebno za svaku kategoriju sa najmanje šest proizvoda (37 od 38 kategorija):

- **Numerički** — cena i tehničke karakteristike koje postoje kod najmanje polovine proizvoda u kategoriji (10 kolona za frižidere, 5 za klima-uređaje); prazna polja dobijaju medijanu kategorije, a zatim se kolone standardizuju unutar kategorije.
- **Brend** — one-hot.
- **Tekst** — TF-IDF nad nazivom proizvoda. Ime brenda se prethodno uklanja iz naziva, da se brend ne bi računao dva puta.

Svaki blok se skalira na jediničnu dužinu i množi kvadratnim korenom svoje težine, pa je kosinusna sličnost celog profila tačno težinski prosek sličnosti po blokovima:

```
cos(A,B) = 0,60·cos_numerički + 0,15·cos_brend + 0,25·cos_tekst
```

Težine su 60 % za karakteristike i cenu, 25 % za naziv i 15 % za brend: cilj je zamena za uređaj, a ne isti proizvođač, a naziv nosi informacije kojih nema u tabeli karakteristika („inverter“, „no frost“, „side by side“). Pošto je numerički blok standardizovan, sličnost se kreće od −0,60 do 1.

**Izmereni uticaj brenda.** Cena utiče na preporuku manje nego brend. Cena je jedna od 10 numeričkih kolona kod frižidera i jedna od 5 kod klima-uređaja, pa na nju otpada oko 6 % odnosno 12 % sličnosti, dok isti brend uvek doprinosi punih 15 %. Mereno na svim kategorijama, 82,4 % preporuka ima isti brend kao izabrani proizvod, iako taj brend u proseku drži 11,3 % kategorije. Kada se težina brenda postavi na nulu (numerički blok 60 %, naziv 40 %), udeo pada na 50,7 %, a samo sa numeričkim obeležjima na 40,1 %, jer proizvođači prave serije sličnih uređaja.

Isti uređaj se ne ponavlja u listi: prepoznaje se po brendu i sortiranim grupama slova i cifara u nazivu („TM1057“ i „TM 1057“ su isto), pri čemu se reč „outlet“ zanemaruje.

Primeri:

| Izabrani proizvod | Preporuke (sličnost) |
|---|---|
| Midea Inverter klima GAIA-12HRFN8-IG (89.999 RSD) | Midea Breezeless MSFAAU-12HRFN8.Wi-Fi (0,6130), Midea GAIA-12HRFN8 (0,5861), Midea Breezeless MSFAAU-12HRFN8 (0,5645), LG AP12RT.NSJ (0,5467), Samsung AR70H09CAAWNEU (0,5417) |
| Gorenje Kombinovani frižider NRK11PWJ (33.999 RSD) | pet Gorenje kombinovanih frižidera: NRK611PS4 (0,7596), NRK6191GHW4 (0,7596), NRK611PW4 (0,7592), NRK6191MW (0,7590), NRK611SYW4 (0,7587) |

Sličnost od 0,61 ne znači „61 % tačno“; ona znači da je to najbliži proizvod pri ovim težinama.

## Prikupljanje i prečišćavanje podataka

### Indekser

- **Zasnovan na mapama sajta.** URL adrese proizvoda čitaju se iz sitemap fajlova koje prodavnice objavljuju za pretraživače (tri fajla sa proizvodima za winwin.rs, sitemap indeks za gigatron.rs), pa se ceo katalog dobija bez obilaska stranica kategorija i sa manje zahteva nego praćenjem linkova.
- **Filtriranje pre preuzimanja gde je to moguće.** winwin.rs čuva kategoriju u URL adresi, pa je preuzeta samo bela tehnika (9.677 stranica). gigatron.rs to ne radi, pa su zatražene sve 43.874 URL adrese proizvoda (43.805 uspešno), a 6.315 proizvoda bele tehnike izdvojeno je tokom parsiranja.
- **robots.txt.** Učitava se za svaku prodavnicu i svaka URL adresa se proverava metodom `can_fetch`.
- **Pauze i ograničenja.** 0,6 s ± 0,4 s između zahteva istog radnika, najviše 5 paralelnih radnika. Zahtev ima najviše 3 pokušaja, sa pauzom od 5 s puta redni broj pokušaja posle neuspelog; HTTP 404 se ne ponavlja. Zahtevi nose uobičajena zaglavlja pregledača.
- **Nastavak posle prekida.** Svaka stranica se čuva kao gzip pod SHA-1 hešom svoje URL adrese, a postojeći fajl se preskače. Spisak URL adresa se meša sa fiksnim semenom, pa i prekinuto preuzimanje pokriva sve kategorije.
- **Dnevnik.** Svaki zahtev se upisuje u tabelu dnevnika indeksiranja: URL, status, uspeh, greška, trajanje u ms.

Preuzimanje je odvojeno od parsiranja: parser radi samo nad sačuvanim stranicama, pa se može menjati i ponovo pokretati bez ijednog novog zahteva. Preuzimanje je obavljeno za jednu noć: proizvodi u primarnoj bazi nose vremena preuzimanja od 31. avgusta 2026. u 23:30 do 1. septembra 2026. u 03:48 (lokalno vreme).

### Dva parsera

| Prodavnica | Platforma | Tehnika | Šta se čita |
|---|---|---|---|
| winwin.rs | Magento | DOM parser (tabela th/td, lista detalja, blok o zalihama) | specifikacije, dostupnost na stanju |
| winwin.rs | Magento | meta tagovi stranice | cena i valuta |
| winwin.rs | Magento | regularni izrazi nad JavaScript objektom `dataLayer` | šifra artikla, naziv, brend, kategorija |
| gigatron.rs | Next.js | semantičke anotacije (JSON-LD, schema.org) | naziv, brend, cena, ocene kupaca, kategorija |
| gigatron.rs | Next.js | DOM parser (tabela td/td) | specifikacije, stariji raspored |
| gigatron.rs | Next.js | regularni izrazi nad ugrađenim JSON zapisom | specifikacije, noviji raspored |
| gigatron.rs | Next.js | atribut `alt` slike | energetska klasa i skala |

Oba parsera vraćaju rečnik sa istim ključevima. Primarna baza ima tabele `prodavnice`, `proizvodi`, `karakteristike` (karakteristike kao parovi naziv–vrednost) i `dnevnik_indeksiranja` (dnevnik preuzimanja). Vrednost koje nema na sajtu tamo nema zapis, a u prečišćenoj bazi je NULL.

### Prečišćavanje

| Korak | Zapisa | Udeo |
|---|---|---|
| Učitano iz primarne baze | 15.949 | 100,0 % |
| Odbačeno: kategorija nije bela tehnika | 212 | 1,3 % |
| Odbačeno: cena van opsega | 8 | 0,1 % |
| Odbačeno: dodatna oprema prepoznata po nazivu | 108 | 0,7 % |
| Odbačeno: premalo popunjenih karakteristika | 2.198 | 13,8 % |
| Spojeno kao duplikati | 1.439 | 9,0 % |
| Upisano u prečišćenu bazu | 11.984 | 75,1 % |

- **Kategorije.** Lista pravila preslikava kategorije prodavnica u kontrolisani rečnik (u prečišćenoj bazi je prisutno 38 kategorija); važi prvo pravilo koje se poklopi, pa uža pravila stoje ispred širih (mikrotalasne rerne ispred rerni). Za zbirne kategorije vrsta uređaja se čita iz naziva proizvoda.
- **Dodatna oprema.** Filteri i nastavci izlistani među uređajima prepoznaju se po nazivu i odbacuju (108 zapisa, od toga 70 filtera).
- **Brendovi.** Među zadržanim proizvodima 260 načina pisanja brenda svedeno je na 197 proizvođača.
- **Tipizacija.** Iz teksta se izdvajaju broj i jedinica, a jedinica se proverava („12000 BTU“, „7 kg“, „300 l“). Vrednost van verodostojnog opsega ostavlja se prazna; cena van opsega odbacuje zapis.
- **Šablonske vrednosti.** Druga tabela specifikacija na winwin.rs služi filterima prodavnice i nosi šablonske vrednosti („visina 187 cm“ kod 945 proizvoda, od kojih 934 navodi i stvarnu, drugačiju visinu). Takvi parovi se preskaču.
- **Energetska klasa.** Postoje dve skale oznaka: stara sa plusevima (od A+++ naniže) i nova (od A do G), uvedena 2021. godine. Između njih ne postoji zvanično preslikavanje, pa se klasa i skala čuvaju odvojeno, a numerički rang se računa unutar sopstvene skale. Skalu određuje eksplicitna oznaka; kod samog slova skala se određuje prema vrsti uređaja.
- **Duplikati.** Ključ je brend i oznaka modela. Outlet ponude dobijaju sopstveni ključ. Dve ponude iste prodavnice pod istim ključem, ali sa različitim nazivima, razdvajaju se, a Gigatron ponuda čiji ključ nije našao par (njeno polje modela može da sadrži internu šifru) uparuje se sa winwin.rs ponudom iste kategorije po delovima naziva ili po oznaci modela sadržanoj u njemu, samo kada je par jedinstven (423 para). Spojeni uređaj čuva najnižu, najvišu i prosečnu cenu; modeli koriste najnižu (`cena_min`).
- **Prag.** Uređaj ulazi u prečišćenu bazu samo ako posle spajanja ima najmanje 3 popunjena tehnička polja.

Prečišćena baza ima jedan red po uređaju sa tipiziranim kolonama, tabelu `poreklo` koja svaki red povezuje sa izvornim zapisima i tabelu `dnevnik_ciscenja` sa gornjim brojevima.

## Aplikacija

Prozor u tkinter-u sa tri kartice. Model cene se učitava iz `izvestaj/modeli/regresija_model.json`; klasterovanje se izvršava pri svakom zahtevu; profili za preporuke grade se jednom, pri pokretanju. Aplikacija bazu samo čita.

**Predviđanje cene.** Korisnik bira kategoriju, brend i energetsku klasu sa njenom skalom i unosi karakteristike koje zna; prazna polja se popunjavaju na isti način kao pri obučavanju. Broj mora biti između polovine najmanje i 1,5 puta najveće vrednosti te karakteristike u kategoriji, a procena van opsega cena u bazi zamenjuje se porukom o grešci. Primer ispod je Gorenje frižider (klasa E na novoj skali, ukupno 300 l, od čega 210 l frižider i 90 l zamrzivač, 185 × 60 × 64 cm, 38 dB), procenjen na 56.264 RSD; promenom samo brenda dobija se 93.268 RSD za LG, 105.638 RSD za Bosch i 61.018 RSD za Beko.

![Kartica Predviđanje cene](docs/screenshots/price-prediction.png)

**Klasterovanje.** Korisnik zadaje K (od 2 do 12), po želji ograničava podatke na jednu kategoriju, štiklira najmanje dve promenljive i unosi njihove težine. Forma sabira težine tokom unosa; zbir veći od 100 % se odbija, a manji se srazmerno uvećava.

![Kartica Klasterovanje: promenljive, težine i K](docs/screenshots/clustering-setup.png)

Rezultat prikazuje broj proizvoda, Silhouette, inerciju i broj iteracija, dijagram rasejanja i veličine klastera, a za svaki klaster broj proizvoda, udeo, prosečnu cenu i medijanu cene i generisani opis.

![Kartica Klasterovanje: rezultat](docs/screenshots/clustering-result.png)

**Preporuke.** Korisnik pretražuje proizvode po rečima u nazivu, bira jedan i dobija pet najsličnijih proizvoda sa njihovom sličnošću.

![Preporuke za klima-uređaj](docs/screenshots/recommendations-ac.png)

![Preporuke za frižider](docs/screenshots/recommendations-fridge.png)

## Struktura repozitorijuma

```
kod/                              izvorni kod
  indekser/                       indekser: indekser.py (sitemap → spisak URL adresa → sačuvane stranice), podesavanja.py (podešavanja)
  parser/                         parser_magento.py (winwin.rs), parser_gigatron.py (gigatron.rs), upis_u_bazu.py (upis u primarnu bazu)
  preprocessing/                  ciscenje.py (prečišćavanje i spajanje), pravila.py (pravila: kategorije, sinonimi, opsezi, energetske skale)
  analiza/                        upiti.sql (SQL upiti), izvoz_rezultata.py (izvoz u Excel)
  vizuelizacija/                  grafikoni.py (grafikoni)
  models/                         podaci.py (učitavanje, matrica obeležja, podela), regresija.py, kmeans.py, preporuke.py
  evaluation/                     verifikacija.py (poređenje sa bibliotekom scikit-learn)
  app/                            app.py (tkinter aplikacija)
  zajednicko/                     zajednički moduli: veza sa bazom, SQLite/MySQL kopija, nazivi za prikaz, putanje, SQL za punjenje primarne baze
  pokreni_aplikaciju.py, .bat     pokretač aplikacije bez servera baze podataka
  pokreni.bat                     pokretanje celog toka obrade korak po korak
  requirements.txt
baza/
  01_sema_primarna.sql            šema primarne (sirove) baze
  02_sema_preciscena.sql          šema prečišćene baze
  sqlite/psz_preciscena.sqlite    SQLite kopija prečišćene baze (11.984 proizvoda)
izvestaj/
  Izvestaj.pdf                    izveštaj (na srpskom)
  rezultati_upita.xlsx            rezultati upita, po jedan list za svaku SQL naredbu (7 listova)
  grafikoni/                      grafikoni (PNG)
  modeli/                         sačuvani model regresije, tabele eksperimenata i K-means rezultata, primeri preporuka, izlaz verifikacije
docs/screenshots/                 snimci ekrana aplikacije korišćeni u ovom dokumentu
```

Nisu u repozitorijumu: preuzete HTML stranice (preko 2,5 GB), potpuni SQL dump fajlovi obe baze i SQLite kopija primarne baze. Veliki su i sastoje se od sadržaja preuzetog sa sajtova prodavnica. SQLite kopija prečišćene baze je priložena da bi aplikacija i skripte modela radile bez servera baze podataka.

## Pokretanje

Zahtevi za aplikaciju: Python 3.10 ili noviji sa bibliotekama numpy, pandas i matplotlib. tkinter se isporučuje uz Python.

```bash
pip install numpy pandas matplotlib
python kod/pokreni_aplikaciju.py
```

Pokretač proverava biblioteke, a zatim pita za MySQL korisnika. Pritiskom na Enter koristi se priložena SQLite kopija (`python kod/pokreni_aplikaciju.py --baza fajl` preskače pitanje). Kada konzola ispiše `Spremno: 11.984 proizvoda, 37 kategorija sa preporukama`, otvara se prozor. Na Windows-u isto radi dvoklik na `kod\pokreni_aplikaciju.bat`.

Ostali izvori podataka su opcioni. Glavna baza projekta je PostgreSQL. Skripte pokrenute direktno, uključujući `python kod/app/app.py`, povezuju se preko `kod/zajednicko/baza.py`, koji koristi PostgreSQL kada server odgovara, a u suprotnom prelazi na SQLite fajl; promenljiva okruženja `PSZ_BAZA` (`postgres`, `mysql` ili `sqlite`) nameće izvor, a parametri veze čitaju se iz promenljivih `PSZ_DB_*` i `PSZ_MYSQL_*`. Pokretač `kod/pokreni_aplikaciju.py` sam postavlja izvor i bira samo između MySQL-a i SQLite fajla. Put preko MySQL-a ide kroz `kod/zajednicko/kopija_baze.py`, koji puni MySQL iz SQLite kopija obe baze; pošto primarna kopija nije u repozitorijumu, na svežem klonu pokretač prelazi na priloženi fajl.

Ceo tok obrade pokreće se sa `kod\pokreni.bat <korak>` (koraci: `baza`, `spisak`, `preuzmi`, `parsiraj`, `ciscenje`, `upiti`, `grafikoni`, `regresija`, `klasteri`, `preporuke`, `provera`, `aplikacija`, `sve`; `sve` izvršava korake od `ciscenje` do `provera`). Potrebni su PostgreSQL server sa klijentom `psql`, virtuelno okruženje u `.venv` sa instaliranim `kod/requirements.txt` i novo preuzimanje, jer sirove stranice i dump fajlovi baza nisu deo repozitorijuma; iz istog razloga ne može se koristiti ni korak `obnovi`, koji obnavlja baze iz dump fajlova. Korak preuzimanja traje nekoliko sati. Koracima koji samo čitaju prečišćenu bazu (`upiti`, `grafikoni`, `regresija`, `klasteri`, `preporuke`, `provera`, `aplikacija`) dovoljno je virtuelno okruženje: kada nijedan PostgreSQL server ne odgovara, oni čitaju priloženi SQLite fajl, a skripte među njima ponovo upisuju svoje izlazne fajlove u `izvestaj/`.

## Verifikacija

scikit-learn se koristi samo u `kod/evaluation/verifikacija.py`, za poređenje ručno napisanih implementacija sa bibliotečkim na istim podacima. Izlaz je u `izvestaj/modeli/verifikacija.txt`.

| Implementacija | Poređeno sa | Rezultat |
|---|---|---|
| Kosinusna sličnost | `cosine_similarity` | najveća apsolutna razlika 6,7e-16 na 40.000 parova |
| TF-IDF | `TfidfVectorizer` | ista veličina rečnika (511); identičnih Top-5 za 399 od 400 naziva televizora. Formule za idf se razlikuju, pa se porede rangiranja, a ne vrednosti |
| K-means, frižideri | `KMeans` | K = 4: inercija 339,72 u oba slučaja, 99,9 % parova tačaka raspoređeno na isti način |
| Silhouette | `silhouette_score` | 0,4075 u oba slučaja, razlika 2,2e-13 |
| Gradijent | numerički izvod | razlika manja od 1e-8 |
| Gradijentni spust na matrici punog ranga | `np.linalg.lstsq` | najveća razlika koeficijenata 1,4e-14 |
| Regresija na punoj matrici obeležja, šest podela 80/20 | `LinearRegression` | sopstveni gradijentni spust (α = 0,1, najviše 8.000 iteracija): R² (log) od 0,83 do 0,84 na svakoj podeli; najmanji kvadrati: od −2,81 do 0,86 |

Poslednji red zahteva komentar. Matrica obeležja je izrazito kolinearna (785 kolona, rang 401), pa je metod običnih najmanjih kvadrata na njoj nestabilan i njegovi koeficijenti rastu do 222, dok se gradijentni spust pokrenut od nule ponaša kao rano zaustavljanje i zadržava najveći koeficijent na 2,19. Ručno napisani kod nije bolji od biblioteke; on je stabilan na ovoj matrici, a dva reda iznad pokazuju da je sama implementacija ispravna.

## Ograničenja

- Cene i dostupnost na stanju su presek u trenutku preuzimanja, a dve prodavnice ne predstavljaju celo srpsko tržište.
- Kategorija se preuzima od prodavnice, pa su 24 poslovna displeja (interaktivni, signage i video-wall modeli) svrstana među televizore.
- Parametri gradijentnog spusta birani su na istom test skupu na kojem je prikazan i konačni rezultat, jer ne postoji zaseban validacioni skup; konačna procena je zato blago optimistična.
- Model je linearan i van opsega podataka samo produžava pravu liniju. Najveća apsolutna greška je kod televizora, najskupljih uređaja; najveća relativna greška je kod ventilatora i usisivača, čija cena malo zavisi od karakteristika koje se mogu pročitati sa sajta.
- Matrica obeležja je kolinearna, pa mnogo različitih vektora koeficijenata daje isto predviđanje i pojedinačni koeficijenti se ne mogu tumačiti kao uticaj obeležja.
- Stara i nova energetska skala nisu svedene na zajedničku meru, jer zvanično preslikavanje ne postoji. Energetski rang zato delimično razdvaja uređaje po skali oznake, a ne po efikasnosti, i u klasterovanju i u preporukama.
- K-means nalazi lokalni minimum i osetljiv je na odstupajuće vrednosti: kada se televizori klasteruju po ceni i dijagonali, nekoliko najskupljih obrazuje sopstveni klaster.
- Isti uređaj iz dve prodavnice ne prepoznaje se uvek kada se oznake modela razlikuju, pa je stvarni broj uređaja prisutnih u obe prodavnice veći od 1.244.
- Kod klima-uređaja čita se opšta klasa ili klasa hlađenja, a ne klasa grejanja, pa 21 klima-uređaj koji navodi samo klasu grejanja ostaje bez klase (30 od 412 klima-uređaja nema klasu).
- Prag od tri tehnička polja ne pogađa sve vrste uređaja podjednako, jer za neke prodavnice navode uglavnom opisna polja.
- winwin.rs za mali broj proizvoda navodi pogrešan brend.

## Izveštaj

Potpuni izveštaj je u [izvestaj/Izvestaj.pdf](izvestaj/Izvestaj.pdf) (na srpskom jeziku). Obuhvata prikupljanje podataka, pretprocesiranje i SQL upite, vizuelizaciju i po jedno poglavlje za svaki od tri modela, a završava se zaključcima i ograničenjima.
