# Excel migration

Zdrojovy soubor:

```text
C:\TEMP\Aktivity MaSe.xlsm
```

Analyzovane listy:

- `Aktivity`
- `Rezijni tikety`
- `KT`
- `Statistika`
- `Doprava`

## Postup migrace

1. Spustit aplikaci a databazi.
2. Nahrat Excel pres endpoint `POST /imports/excel`.
3. Importovat ciselnik dopravy.
4. Importovat rezijni tikety.
5. Importovat casove zaznamy z listu `Aktivity`.
6. Porovnat soucty s listy `Statistika` a `KT`.

## Kontrolni soucty

Po importu overit minimalne:

- pocet importovanych zaznamu s datem,
- celkove hodiny za mesic,
- celkove hodiny za rok,
- top projekty podle hodin,
- pocet zaznamu s tiketem,
- pocet zaznamu s prekryvem,
- soucty podle kategorii.

## Rezijni tikety

Puvodni list obsahuje:

- `#`
- `Projekt`
- `Predmet`
- `Obdobi`

Pravidlo prevodu:

- `YYYY-MM` -> platnost od prvniho dne mesice 00:00 do posledniho dne mesice 23:59:59,
- `YYYY` -> platnost od 1.1. 00:00 do 31.12. 23:59:59,
- nove zaznamy v aplikaci budou mit explicitni `valid_from` a `valid_to`.

