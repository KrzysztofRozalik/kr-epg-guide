# KR Live EPG — wydanie publiczne

To repozytorium zawiera generator i bezpłatny mechanizm publikacji GitHub Pages.
Gotowe pliki XMLTV
są publikowane jako artefakt Pages, więc historia Git nie puchnie od cogodzinnych
kopii dużego pliku `epg.xml.gz`.

Wymagane ustawienia repozytorium:

- opcjonalny sekret `TMDB_API_TOKEN`: bezpłatne wzbogacanie filmów i seriali;
- Pages: źródło `GitHub Actions`.

Workflow uruchamia się o 17 minut po każdej pełnej godzinie oraz ręcznie z karty
Actions. Nie używa płatnego runnera ani płatnego hostingu.
