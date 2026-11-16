"""Constantes do projeto: dataset, caminhos locais e premissas de analise."""

from pathlib import Path

# ---------------------------------------------------------------- caminhos locais
RAIZ = Path(__file__).resolve().parents[1]
DIR_DADOS = RAIZ / "data"
DIR_RAW = DIR_DADOS / "raw"
DIR_PROCESSADOS = DIR_DADOS / "processed"
DIR_RESULTADOS = RAIZ / "results"
DIR_TABELAS = DIR_RESULTADOS / "tabelas"

# ---------------------------------------------------------------- dataset
DATASET_KAGGLE = "karkavelrajaj/amazon-sales-dataset"
CSV_RAW = DIR_RAW / "amazon.csv"

# ---------------------------------------------------------------- premissas
# Cotacao INR -> BRL fixa. O BCB nao cota INR na PTAX, entao cruzamos a PTAX do dolar
# com a taxa INR/USD do BCE. Toda a analise e' relativa: a cotacao muda a escala, nao as conclusoes.
COTACAO_INR_BRL = 0.05997  # cruzamento PTAX USD/BRL BCB 13/11/2026 (5,6518) x INR/USD BCE 13/11/2026 (0,010611)

# Produtos/categorias com menos avaliacoes que isso nao entram em rankings de nota.
BASE_N_MINIMA = 30
