# Google Cloud Run + Scheduler

Ten wariant uruchamia generator tylko na czas żądania i publikuje pliki do R2. Nie
polegaj na lokalnym katalogu `output` w Cloud Run, bo system plików instancji jest
ulotny.

1. Zbuduj obraz przez `cloudbuild.yaml` i skonfiguruj usługę z `--max-instances=1`.
2. Przekaż sekrety przez Secret Manager: `KR_EPG_ADMIN_TOKEN`, dane źródeł, TMDb
   i R2. Nie wpisuj ich do obrazu ani repozytorium.
3. W docelowym `config.yaml` ustaw `storage.type: s3` i endpoint R2.
4. Nadaj kontu Scheduler rolę `roles/run.invoker` dla usługi.
5. Utwórz zadanie HTTP co 10 minut na adres:
   `POST https://SERVICE_URL/admin/run?mode=live`.
6. Scheduler powinien wysyłać token OIDC w `Authorization` oraz osobny nagłówek
   `X-Admin-Token` z wartością `KR_EPG_ADMIN_TOKEN`.

Endpoint czeka na zakończenie kompilacji. To celowe: Cloud Run może ograniczać CPU
po wysłaniu odpowiedzi, dlatego generator nie pracuje jako zadanie w tle.

Limity bezpłatnych usług i zasady Scheduler/R2 mogą się zmieniać. Przed
uruchomieniem ustaw budżet i alert kosztowy równy 0 lub najniższy możliwy próg.
