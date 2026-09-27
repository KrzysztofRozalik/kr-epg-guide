# Bezpłatne wdrożenie GitHub Pages

Repozytorium wydawnicze zawiera kod i workflow, a prywatne repozytorium służy jako kopia kodu.
Standardowy runner publicznego repozytorium generuje
EPG co godzinę i publikuje stronę przez GitHub Pages.

## Koszt i zabezpieczenia

- brak karty płatniczej;
- brak płatnego serwera i domeny;
- wyłącznie standardowy runner publicznego repozytorium;
- limit 20 minut na uruchomienie;
- brak zdarzeń `pull_request` i `push`, więc kod z forka nie otrzyma sekretu;
- workflow nie potrzebuje tokenu dostępu do prywatnego repo;
- nieudane generowanie nie zastępuje ostatniego poprawnego wdrożenia Pages.

## Dwa repozytoria

1. Prywatne `KR-Live-EPG` — kopia kodu.
2. Publiczne `kr-epg-guide` — kod generatora, workflow i adres EPG.

W publicznym repozytorium ustaw:

1. `Settings → Pages → Build and deployment → Source: GitHub Actions`.
2. Opcjonalnie dodaj `TMDB_API_TOKEN`. Dla prywatnego, niekomercyjnego pilotażu
   klucz TMDB jest bezpłatny, ale wymaga konta i atrybucji. Użycie komercyjne
   wymaga odrębnych praw/licencji.
3. Otwórz `Actions → Aktualizacja EPG → Run workflow`.

Po zielonym przebiegu adresy będą miały postać:

```text
https://LOGIN.github.io/kr-epg-guide/v1/dom/epg.xml.gz
https://LOGIN.github.io/kr-epg-guide/v1/lekki/epg.xml.gz
https://LOGIN.github.io/kr-epg-guide/v1/dom/epg.xml
https://LOGIN.github.io/kr-epg-guide/v1/lekki/epg.xml
```

Rzeczywisty zakres przyszłej ramówki zależy od źródeł. Generator nie może
stworzyć danych, których nadawca lub legalny agregator jeszcze nie opublikował.
Plik `v1/dom/coverage.json` pokazuje, które kanały mają prawdziwą ramówkę,
wyłącznie wpis zastępczy albo pozostają puste. Wbudowany Sentinel sprawdza także
oficjalny kalendarz KSW i dodaje potwierdzone gale do kanału `ksw.pl`.
