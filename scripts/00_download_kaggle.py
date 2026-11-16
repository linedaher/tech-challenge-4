"""Baixa o Amazon Sales Dataset do Kaggle para data/raw/amazon.csv.

Usa `kagglehub` (le ~/.kaggle/kaggle.json no formato novo, so com `key`).
Idempotente: se o CSV ja existe em data/raw/, nao baixa de novo.

Uso:  python scripts/00_download_kaggle.py
"""

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _preparar_credencial() -> None:
    """Exporta KAGGLE_API_TOKEN a partir de ~/.kaggle/kaggle.json (token novo, prefixo KGAT)."""
    if os.environ.get("KAGGLE_API_TOKEN"):
        return
    arquivo = Path.home() / ".kaggle" / "kaggle.json"
    if not arquivo.exists():
        return
    cred = json.loads(arquivo.read_text())
    if "username" not in cred and str(cred.get("key", "")).startswith("KGAT"):
        os.environ["KAGGLE_API_TOKEN"] = cred["key"]


_preparar_credencial()

import kagglehub  # noqa: E402

from src.config import CSV_RAW, DATASET_KAGGLE, DIR_RAW  # noqa: E402


def main() -> None:
    if CSV_RAW.exists():
        print(f"ja existe em {CSV_RAW} ({CSV_RAW.stat().st_size / 1e6:.1f} MB)")
        return
    print(f"baixando {DATASET_KAGGLE} ...")
    pasta = Path(kagglehub.dataset_download(DATASET_KAGGLE))
    csvs = sorted(pasta.rglob("*.csv"))
    if not csvs:
        raise RuntimeError(f"nenhum CSV encontrado em {pasta}")
    origem = max(csvs, key=lambda p: p.stat().st_size)
    DIR_RAW.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem, CSV_RAW)
    print(f"{origem.name} -> {CSV_RAW} ({CSV_RAW.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
