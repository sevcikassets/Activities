# Activities

Evidence odpracovane doby a aktivit s importem historickych dat z Excelu.

## Cil

Nahradit soucasny Excel `Aktivity MaSe.xlsm` webovou aplikaci provozovanou v Dockeru vedle existujici aplikace `vocab-app`.

Zakladni funkcionalita:

- evidence casovych zaznamu v tabulkovem rezimu,
- import historickych aktivit z Excelu,
- evidence rezijnich tiketu vcetne platnosti,
- statistiky podle mesicu, roku, kategorii a projektu,
- export do CSV,
- priprava na hlasove zadavani.

## Rychly start pro vyvoj

```powershell
docker compose up --build
```

Aplikace:

- frontend: http://localhost:3000
- API: http://localhost:8000
- PostgreSQL: localhost:5432

## Dokumentace

- `docs/ARCHITECTURE.md` - architektura a datovy model
- `docs/AWS_DEPLOYMENT.md` - postup nasazeni na AWS pri jedne verejne IP
- `docs/EXCEL_MIGRATION.md` - mapovani Excelu a migracni postup

## Produkcni nasazeni

Postup je stejny jako u `vocab-app`: pripravit `.env` a spustit:

```bash
./deploy-production.sh
```

Aktualizace bez rucniho prepisovani compose prikazu:

```bash
./update-activities-app.sh
```
