# rol1


Male cviceni v pouziti jekylla. 

jak to "spustit" ? 

1. nainstalujeme Jekyll podle https://jekyllrb.com/

2. 
```
git clone https://github.com/Kraksna83/rol1.git
cd rol1
jekyll build
```

v adresari _site se objevi kompletni stranky v HTML formátu ktere je mozne uploadnout na vas oblibeny webhosting. 

## Nasazení pomocí webhooku

Webhook pro nasazování načítá konfiguraci ze souboru `.env` vedle souboru
`wh.py`. Nainstalujte jeho závislost pro Python a vytvořte konfigurační soubor
podle připraveného vzoru:

```sh
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Na serveru nastavte v souboru `.env` hodnoty `REPO_DIR`, `WEB_DIR`,
`JEKYLL_CMD`, `SECRET` a `EMAIL_FROM`. Pro `SECRET` použijte jedinečnou,
bezpečně vygenerovanou hodnotu; soubor `.env` neukládejte do Gitu.

Lokální testovací sestavení můžete spustit z konzole:

```sh
python3 wh.py --dry-run
```

Tento režim vygeneruje `dokumenty.md` a sestaví web do `_site`, ale neprovede
`git pull`, neodešle e-mail ani nezkopíruje soubory do webového adresáře.
