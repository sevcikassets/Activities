# Architecture

## Komponenty

- `web`: Next.js frontend pro tabulkove zadavani, statistiky a hlasovy navrh.
- `api`: FastAPI backend.
- `db`: PostgreSQL.
- `traefik`: reverse proxy pro provoz vice aplikaci na jedne IP adrese.

## Datovy model

### `time_entries`

Hlavni evidence aktivit importovana z listu `Aktivity`.

Mapovani Excelu:

- `Kat.` -> `category_code`
- `Popis` -> `description`
- `Datum` -> `spent_on`
- `Zacatek` -> `started_at`
- `Konec` -> `ended_at`
- `Prekryv` -> `overlap_hours`
- `Hodin` -> `duration_hours`
- `Tiket` -> `ticket_id`
- `Projekt` -> `project_id`
- `Text` -> `raw_text`
- `redmine cas` -> `redmine_time`
- `Zapsano` -> `reported_status`

### `tickets`

Obsahuje bezne i rezijni tikety. Rezijni tikety pochazi z listu `Rezijni tikety`.

Pro rezijni tikety se uklada:

- cislo tiketu,
- projekt,
- predmet,
- puvodni obdobi z Excelu,
- `valid_from`,
- `valid_to`.

Excelove obdobi `YYYY-MM` se prevadi na cely mesic. Obdobi `YYYY` se prevadi na cely rok. Nove zadavani ma uz pouzivat explicitni datum a cas od-do.

### `projects`

Projektovy ciselnik vznikne z listu `Aktivity` a `Rezijni tikety`.

### `transports`

Ciselnik dopravy z listu `Doprava`.

## Statistiky

Prvni sada statistik kopiruje rozsah listu `Statistika` a `KT`:

- mesicni soucty hodin,
- rocni soucty hodin,
- soucty podle kategorii,
- soucty podle projektu,
- soucty pro VIP / dulezite zakazniky / ostatni,
- rozdily mezi roky,
- kontrola zapsanych a nezapsanych casu,
- kontrola prekryvu.

## Hlasove zadavani

Aktualni MVP umi z textu pripravit navrh. Dalsi krok je doplnit realny speech-to-text vstup:

- browser Web Speech API pro rychly prototyp,
- nebo serverove STT pro spolehlivejsi prepis.

Ukladat se ma az potvrzeny navrh.

