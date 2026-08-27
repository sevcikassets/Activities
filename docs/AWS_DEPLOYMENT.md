# AWS deployment pri jedne verejne IP

## Princip

Na serveru bude verejne vystaveny pouze reverse proxy kontejner Traefik na portech 80 a 443. Jednotlive aplikace pobezi v interni Docker siti a Traefik je bude smerovat podle domeny.

Priklad:

- `vocabulary.sevcikassets.cz` -> `vocab-app`
- `activities.sevcikassets.cz` -> `activities-web`
- `activities.sevcikassets.cz/api` -> `activities-api`

## Co pripravit v DNS

Az bude znamy nazev subdomeny, zalozte DNS A zaznam:

```text
activities.sevcikassets.cz  A  <verejna-IP-AWS-serveru>
```

TTL muze byt napr. 300 sekund.

Stejny princip pouzijte pro `vocab-app`, pokud jeste nejede pres subdomenu:

```text
vocabulary.sevcikassets.cz  A  <verejna-IP-AWS-serveru>
```

## AWS Security Group

Povolit z internetu:

- TCP 80
- TCP 443

SSH port 22 doporucene povolit pouze z vasi verejne IP adresy.

Databaze PostgreSQL nesmi byt vystavena do internetu. Ma byt dostupna jen v Docker siti, pripadne v privatni siti AWS, pokud se pouzije RDS.

## Instalace Traefiku

Na serveru:

```bash
mkdir -p /opt/proxy
cd /opt/proxy
```

Zkopirovat obsah `deploy/traefik/docker-compose.yml` a `.env`.

```bash
cp .env.example .env
nano .env
docker compose up -d
```

V `.env` nastavit email pro Let's Encrypt:

```text
LETSENCRYPT_EMAIL=vas.email@example.cz
```

## Nasazeni Activities

Na serveru:

```bash
mkdir -p /opt/activities
cd /opt/activities
git clone <repo-url> .
cp .env.example .env
nano .env
./deploy-production.sh
```

Produkci nastavte napriklad:

```text
POSTGRES_DB=activities
POSTGRES_USER=activities
POSTGRES_PASSWORD=<silne-heslo>
DATABASE_URL=postgresql+psycopg://activities:<silne-heslo>@db:5432/activities
DOMAIN=activities.sevcikassets.cz
API_CORS_ORIGINS=https://activities.sevcikassets.cz
NEXT_PUBLIC_API_URL=https://activities.sevcikassets.cz/api
APP_USERNAME=admin
APP_PASSWORD=<prvni-admin-heslo>
APP_TOKEN_SECRET=<nahodny-token-secret>
# Volitelne pro rozpoznavani fotek PHM pres AWS Textract:
AWS_REGION=eu-central-1
```

`APP_USERNAME` a `APP_PASSWORD` se pouziji jen pri prvnim startu pro vytvoreni prvniho admina. Dalsi uzivatele a hesla se spravuji primo v aplikaci v sekci `Uzivatele`.

Pro rozpoznavani uctenek a palubni desky v agende PHM pridejte EC2 instance role opravneni `textract:DetectDocumentText`. Bez tohoto opravneni bude rucni zadavani a editace PHM fungovat dal, pouze tlacitko pro rozpoznani fotek vrati chybu konfigurace OCR.

Aktualizace aplikace po zmenach v Gitu:

```bash
./update-activities-app.sh
```

## Napojeni stavajici vocab-app

`vocab-app` musi byt pripojena do Docker site `proxy` a musi mit Traefik labels.

Priklad:

```yaml
services:
  vocab-app:
    networks:
      - proxy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.vocab.rule=Host(`vocabulary.sevcikassets.cz`)"
      - "traefik.http.routers.vocab.entrypoints=websecure"
      - "traefik.http.routers.vocab.tls.certresolver=letsencrypt"
      - "traefik.http.services.vocab.loadbalancer.server.port=3000"

networks:
  proxy:
    external: true
    name: proxy
```

Port `3000` v poslednim radku nahradte internim portem, na kterem `vocab-app` skutecne posloucha.

## Kontrola

```bash
docker network ls
docker ps
docker logs traefik --tail=100
curl -I https://activities.sevcikassets.cz
curl https://activities.sevcikassets.cz/api/health
```

## Zalohy

Minimalni varianta:

```bash
docker exec activities-db-1 pg_dump -U activities activities > activities-$(date +%F).sql
```

Doporuceni pro produkci:

- denni dump PostgreSQL,
- ulozeni do S3,
- lifecycle policy v S3,
- pravidelny test obnovy.
