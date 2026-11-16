"""Gera as tabelas tratadas em data/processed/ a partir de data/raw/amazon.csv.

- dProduto.csv     : 1 linha por produto (referencia para validar o Power Query)
- fReview.csv      : 1 linha por trecho de review, com sentimento (VADER)
- fReviewTema.csv  : ponte trecho x tema
- log_tratamento.json

O Power BI refaz o tratamento de produtos no Power Query (passos visiveis no .pbix)
e importa so fReview.csv e fReviewTema.csv, que dependem de Python.

Uso:  python scripts/01_tratamento.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from src.config import CSV_RAW, DIR_PROCESSADOS  # noqa: E402
from src.limpeza import tratar_produtos  # noqa: E402
from src.reviews import tabela_reviews  # noqa: E402


def main() -> None:
    raw = pd.read_csv(CSV_RAW)
    prod, log = tratar_produtos(raw)

    # reviews so dos registros mantidos na deduplicacao (mesma regra de tratar_produtos)
    qtd = pd.to_numeric(raw["rating_count"].str.replace(",", "", regex=False))
    raw_dedup = (raw.assign(_q=qtd).sort_values("_q", ascending=False, na_position="last")
                    .drop_duplicates("product_id", keep="first"))
    rev, ponte, log_rev = tabela_reviews(raw_dedup)
    log.update(log_rev)

    DIR_PROCESSADOS.mkdir(parents=True, exist_ok=True)
    prod.to_csv(DIR_PROCESSADOS / "dProduto.csv", index=False)
    rev.to_csv(DIR_PROCESSADOS / "fReview.csv", index=False)
    ponte.to_csv(DIR_PROCESSADOS / "fReviewTema.csv", index=False)
    (DIR_PROCESSADOS / "log_tratamento.json").write_text(json.dumps(log, indent=2, ensure_ascii=False))
    print(json.dumps(log, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
