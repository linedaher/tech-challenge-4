"""Regras de tratamento da base de produtos (espelhadas no Power Query do .pbix).

Cada funcao aqui tem um passo equivalente em powerbi/power_query.m; os dois
caminhos precisam produzir os mesmos numeros (ver notebooks/01_perfil_tratamento.ipynb).
"""

import re

import numpy as np
import pandas as pd

from src.config import COTACAO_INR_BRL

CATEGORIAS_PRINCIPAIS = {"Electronics", "Computers&Accessories", "Home&Kitchen", "OfficeProducts"}

TRADUCAO_CATEGORIA = {
    "Electronics": "Eletrônicos",
    "Computers&Accessories": "Informática e Acessórios",
    "Home&Kitchen": "Casa e Cozinha",
    "OfficeProducts": "Escritório",
    "Outros": "Outros",
}


def _moeda_para_numero(s: pd.Series) -> pd.Series:
    """'₹1,099' -> 1099.0"""
    return pd.to_numeric(s.str.replace("₹", "", regex=False).str.replace(",", "", regex=False))


def _separar_camel(nome: str) -> str:
    """'USBCables' -> 'USB Cables'; 'Cables&Accessories' -> 'Cables & Accessories'."""
    nome = nome.replace("&", " & ")
    nome = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", nome)
    return re.sub(r"\s+", " ", nome).strip()


def tratar_produtos(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Devolve (tabela de produtos tratada, log de tratamento com contagens)."""
    log = {"linhas_raw": len(raw), "produtos_unicos_raw": raw["product_id"].nunique()}
    df = raw.copy()

    # 1. tipos numericos
    df["preco_original_inr"] = _moeda_para_numero(df["actual_price"])
    df["preco_desconto_inr"] = _moeda_para_numero(df["discounted_price"])
    df["desconto_pct"] = pd.to_numeric(df["discount_percentage"].str.rstrip("%")) / 100
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")  # '|' vira NaN
    df["qtd_avaliacoes"] = pd.to_numeric(df["rating_count"].str.replace(",", "", regex=False))
    log["rating_invalido"] = int(df["rating"].isna().sum())
    log["qtd_avaliacoes_nula"] = int(df["qtd_avaliacoes"].isna().sum())

    # 2. duplicados: mesmo produto coletado 2x -> fica o snapshot com mais avaliacoes
    df = (df.sort_values("qtd_avaliacoes", ascending=False, na_position="last")
            .drop_duplicates("product_id", keep="first"))
    log["duplicados_removidos"] = log["linhas_raw"] - len(df)

    # 3. nulos: sem nota ou sem contagem nao entram nas analises de satisfacao/engajamento
    df["flag_sem_avaliacao"] = df["rating"].isna() | df["qtd_avaliacoes"].isna()
    log["produtos_sem_avaliacao"] = int(df["flag_sem_avaliacao"].sum())

    # 4. conversao para R$
    df["preco_original_brl"] = (df["preco_original_inr"] * COTACAO_INR_BRL).round(2)
    df["preco_desconto_brl"] = (df["preco_desconto_inr"] * COTACAO_INR_BRL).round(2)
    df["economia_brl"] = df["preco_original_brl"] - df["preco_desconto_brl"]

    # 5. hierarquia de categoria
    niveis = df["category"].str.split("|")
    cat1 = niveis.str[0].where(niveis.str[0].isin(CATEGORIAS_PRINCIPAIS), "Outros")
    df["categoria"] = cat1.map(TRADUCAO_CATEGORIA)
    df["subcategoria"] = niveis.str[1].map(_separar_camel)
    df["categoria_folha"] = niveis.str[-1].map(_separar_camel)

    # 6. variantes: na Amazon, cores/modelos do mesmo anuncio compartilham nota e contagem.
    # Mesma marca + mesma nota + mesma qtd_avaliacoes = mesmo grupo; somas de engajamento
    # contam cada grupo 1 vez (medida DAX usa grupo_avaliacao).
    marca = df["product_name"].str.split().str[0].str.lower()
    chave = marca + "|" + df["rating"].astype(str) + "|" + df["qtd_avaliacoes"].astype(str)
    df["grupo_avaliacao"] = chave.where(~df["flag_sem_avaliacao"], df["product_id"])
    codigos = pd.Series(pd.factorize(df["grupo_avaliacao"])[0], index=df.index)
    df["grupo_avaliacao"] = "G" + codigos.astype(str).str.zfill(4)
    log["produtos_em_grupo_de_variantes"] = int(df["grupo_avaliacao"].duplicated(keep=False).sum())
    log["grupos_de_avaliacao"] = int(df["grupo_avaliacao"].nunique())

    # 7. checagens (falham alto se a regra quebrar)
    assert df["product_id"].is_unique
    assert (df["preco_desconto_inr"] <= df["preco_original_inr"]).all(), "preco com desconto > original"
    calc = 1 - df["preco_desconto_inr"] / df["preco_original_inr"]
    log["desconto_divergente_>1pp"] = int(((calc - df["desconto_pct"]).abs() > 0.01).sum())

    log["produtos_final"] = len(df)
    cols = ["product_id", "product_name", "categoria", "subcategoria", "categoria_folha",
            "preco_original_inr", "preco_desconto_inr", "preco_original_brl", "preco_desconto_brl",
            "economia_brl", "desconto_pct", "rating", "qtd_avaliacoes", "flag_sem_avaliacao",
            "grupo_avaliacao",
            "about_product", "img_link", "product_link"]
    return df[cols].reset_index(drop=True), log


def rating_ponderado(rating: pd.Series, n: pd.Series, m: float, c: float) -> pd.Series:
    """Media bayesiana (formula IMDb): puxa notas com poucas avaliacoes para a media geral c."""
    return (n / (n + m)) * rating + (m / (n + m)) * c


def quadrante(qtd: pd.Series, nota: pd.Series, corte_qtd: float, corte_nota: float) -> pd.Series:
    alto_eng = qtd >= corte_qtd
    alta_nota = nota >= corte_nota
    return pd.Series(np.select(
        [alto_eng & alta_nota, alto_eng & ~alta_nota, ~alto_eng & alta_nota],
        ["Estrela", "Risco", "Oportunidade"], default="Revisar"), index=qtd.index)
