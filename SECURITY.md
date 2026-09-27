# Security policy

## Dane wrażliwe

Lista wynikowa M3U może zawierać login i hasło Xtream albo prywatne tokeny
strumieni. Traktuj ją jak hasło. Nie publikuj `config.yaml`, `.env`, `state/`,
plików M3U ani logów portalu.

Sekrety należy przekazywać przez zmienne środowiskowe lub menedżer sekretów.
Publiczny magazyn R2/S3 nie jest wspieranym ustawieniem; bucket powinien być
prywatny, a pliki wydaje Worker z długim losowym tokenem.

## Model zaufania

- Administrator świadomie wybiera źródła XMLTV, RSS, ICS i HTML.
- Parser XML nie rozwiązuje encji ani zasobów sieciowych.
- Pobrania oraz rozmiar po rozpakowaniu gzip mają twarde limity.
- Adapter HTML nie uruchamia JavaScriptu i używa tylko zadanych XPath.
- Nazwy profili i źródeł nie mogą zawierać ścieżek ani `..`.
- Kod nie próbuje omijać blokad, DRM ani kontroli dostępu dostawcy.

## Zgłaszanie

W prywatnym wdrożeniu zgłoszenie powinno trafić bezpośrednio do właściciela
instancji. Przed usługą komercyjną należy utworzyć dedykowany kanał zgłoszeń,
procedurę rotacji sekretów i plan reakcji na incydent.
