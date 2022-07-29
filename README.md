# Description
This is a collection of importers for the UK Lloyds bank for use by <a href="https://beancount.github.io/docs/index.html">Beancount</a>. Currently available are 
* credit_card_pdf.py - which parses PDFs of credit card statements
* current_account_csv.py - which parses CSVs of current account statements

# Setup
I recommend the following directory layout:

* `./main.bean` : Your top-level beancount file
* `./foo.bean` : (any included file)
* `importers/institutions/lloyds` : *This repo*
* `categorisers/` : Your categorisers
* `config.py` : Your importer configuration (see below)

# Sample importer configuration
```python
from institutions.lloyds import credit_card_pdf as lloyds_creditcard

CONFIG = [
    lloyds_creditcard.Importer('Liabilities:Lloyds:Mastercard', '9999', skip_balances=True),
]
```

# Usage

```bash
bean-extract config.py documents/statement-2000-01-15_9999.pdf >> lloyds-credit-card.bean
```

`9999` is the final 4 digits of your 16 digit number. This is supplied by
Lloyds when you download your statement and will be included if you use the
`bean-file` tool.  I like to test the import by writing to a temporary file
first (which I do include from my top-level file, but I subsequently truncate
this file prior to importing for real). Doing this allows me to modify
my categoriser and re-run `bean-extract` without having to manually edit my
already-imported credit card beanfile.

