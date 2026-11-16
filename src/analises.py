"""Analises por pergunta de negocio e por area da empresa.

Cada funcao recebe as tabelas tratadas e devolve um DataFrame pronto para exibir
no notebook e exportar para results/tabelas/. Somas de engajamento usam 1 linha
por grupo_avaliacao (variantes compartilham avaliacoes na Amazon).
"""

import pandas as pd

from src.config import BASE_N_MINIMA, DIR_PROCESSADOS
from src.limpeza import quadrante

FAIXAS_DESCONTO = ([-0.01, 0.2, 0.4, 0.6, 0.8, 1.0], ["0-20%", "20-40%", "40-60%", "60-80%", "80%+"])


def carregar() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(produtos com avaliacao valida + colunas derivadas, reviews, ponte de temas)."""
    p = pd.read_csv(DIR_PROCESSADOS / "dProduto.csv")
    r = pd.read_csv(DIR_PROCESSADOS / "fReview.csv")
    t = pd.read_csv(DIR_PROCESSADOS / "fReviewTema.csv")
    v = p[~p["flag_sem_avaliacao"]].copy()
    v["marca"] = v["product_name"].str.split().str[0].str.replace(r"[^A-Za-z0-9]", "", regex=True).str.lower()
    v["faixa_desconto"] = pd.cut(v["desconto_pct"], *FAIXAS_DESCONTO)
    v["faixa_preco"] = pd.qcut(v["preco_desconto_brl"], 4, labels=["Q1 barato", "Q2", "Q3", "Q4 caro"])
    v["quadrante"] = quadrante(v["qtd_avaliacoes"], v["rating"],
                               v["qtd_avaliacoes"].median(), v["rating"].median())
    return v, r, t


def grupos(v: pd.DataFrame) -> pd.DataFrame:
    """1 linha por grupo de avaliacao (para somar engajamento sem duplicar variantes)."""
    return v.drop_duplicates("grupo_avaliacao")


def _resumo(df: pd.DataFrame, por) -> pd.DataFrame:
    return df.groupby(por, observed=True).agg(
        produtos=("product_id", "size"),
        nota_media=("rating", "mean"),
        pct_abaixo_4=("rating", lambda x: (x < 4).mean()),
        avaliacoes_mediana=("qtd_avaliacoes", "median"),
        desconto_medio=("desconto_pct", "mean"),
    ).round(3)


# ------------------------------------------------------------- perguntas do PDF
def kpis(v: pd.DataFrame) -> pd.Series:
    g = grupos(v)
    top10 = g.nlargest(int(len(g) * 0.1), "qtd_avaliacoes")["qtd_avaliacoes"].sum()
    return pd.Series({
        "produtos": len(v),
        "avaliacoes_total_sem_variantes": int(g["qtd_avaliacoes"].sum()),
        "nota_media": round(v["rating"].mean(), 3),
        "pct_produtos_abaixo_4": round((v["rating"] < 4).mean(), 3),
        "desconto_medio": round(v["desconto_pct"].mean(), 3),
        "preco_mediano_brl": v["preco_desconto_brl"].median(),
        "pct_avaliacoes_top10pct_produtos": round(top10 / g["qtd_avaliacoes"].sum(), 3),
    })


def por_categoria(v: pd.DataFrame, nivel: str = "categoria") -> pd.DataFrame:
    res = _resumo(v, nivel)
    res["avaliacoes_total"] = grupos(v).groupby(nivel)["qtd_avaliacoes"].sum()
    res["pct_avaliacoes"] = (res["avaliacoes_total"] / res["avaliacoes_total"].sum()).round(3)
    return res[res["produtos"] >= (15 if nivel != "categoria" else 1)].sort_values("nota_media")


def desconto_vs_nota(v: pd.DataFrame) -> pd.DataFrame:
    return _resumo(v, "faixa_desconto")


def quadrantes(v: pd.DataFrame) -> pd.DataFrame:
    res = _resumo(v, "quadrante")
    av = grupos(v).groupby("quadrante")["qtd_avaliacoes"].sum()
    res["pct_avaliacoes"] = (av / av.sum()).round(3)
    return res


def lista_quadrante(v: pd.DataFrame, nome: str, n: int = 10) -> pd.DataFrame:
    df = v[v["quadrante"] == nome]
    if nome == "Oportunidade":  # boa nota com base minima confiavel, menos vistos primeiro
        df = df[df["qtd_avaliacoes"] >= BASE_N_MINIMA].sort_values(["rating", "qtd_avaliacoes"], ascending=[False, True])
    else:
        df = df.sort_values("qtd_avaliacoes", ascending=False)
    return df.drop_duplicates("grupo_avaliacao").head(n)[
        ["product_name", "categoria", "subcategoria", "rating", "qtd_avaliacoes", "desconto_pct"]]


def temas(r: pd.DataFrame, t: pd.DataFrame) -> pd.DataFrame:
    tt = t.merge(r[["trecho_id", "sentimento"]], on="trecho_id")
    tab = pd.crosstab(tt["tema"], tt["sentimento"])
    tab["mencoes"] = tab.sum(axis=1)
    tab["pct_trechos"] = (tab["mencoes"] / len(r)).round(3)
    tab["pct_negativo"] = (tab["Negativo"] / tab["mencoes"]).round(3)
    return tab.sort_values("mencoes", ascending=False)


# ------------------------------------------------------------- lentes por area
def pricing_correlacoes(v: pd.DataFrame) -> pd.DataFrame:
    cols = ["desconto_pct", "economia_brl", "preco_desconto_brl"]
    return grupos(v)[cols + ["qtd_avaliacoes", "rating"]].corr("spearman").loc[cols, ["qtd_avaliacoes", "rating"]].round(3)


def pricing_desconto_por_folha(v: pd.DataFrame, n_min: int = 15) -> pd.DataFrame:
    """Dentro da mesma categoria folha: desconto x nota e preco x engajamento."""
    linhas = []
    for folha, d in grupos(v).groupby("categoria_folha"):
        if len(d) >= n_min:
            linhas.append({
                "categoria_folha": folha, "produtos": len(d),
                "rho_desconto_nota": round(d[["desconto_pct", "rating"]].corr("spearman").iloc[0, 1], 2),
                "rho_preco_avaliacoes": round(d[["preco_desconto_brl", "qtd_avaliacoes"]].corr("spearman").iloc[0, 1], 2),
            })
    return pd.DataFrame(linhas).sort_values("rho_desconto_nota").set_index("categoria_folha")


def pricing_preco_final_9(v: pd.DataFrame) -> pd.DataFrame:
    termina9 = v["preco_desconto_inr"].astype(int).astype(str).str[-1].eq("9").rename("preco_termina_em_9")
    return _resumo(v, termina9)


def pricing_ancora_inflada(v: pd.DataFrame) -> pd.DataFrame:
    """Hipotese: preco original inflado para simular desconto (testada, nao confirmada)."""
    w = v[v.groupby("categoria_folha")["product_id"].transform("size") >= 10].copy()
    orig = w["preco_original_brl"] / w.groupby("categoria_folha")["preco_original_brl"].transform("median")
    final = w["preco_desconto_brl"] / w.groupby("categoria_folha")["preco_desconto_brl"].transform("median")
    w["suspeita_ancora"] = (w["desconto_pct"] >= 0.6) & (orig >= 1.5) & (final <= 1.1)
    return _resumo(w, "suspeita_ancora")


def marketing_texto_anuncio(v: pd.DataFrame) -> dict[str, pd.DataFrame]:
    rot = ["Q1 curto", "Q2", "Q3", "Q4 longo"]
    return {
        "tamanho_titulo": _resumo(v, pd.qcut(v["product_name"].str.len(), 4, labels=rot).rename("tamanho_titulo")),
        "tamanho_descricao": _resumo(v, pd.qcut(v["about_product"].str.len(), 4, labels=rot).rename("tamanho_descricao")),
    }


def compras_marcas(v: pd.DataFrame, n_min: int = 10) -> pd.DataFrame:
    res = _resumo(v, "marca")
    av = grupos(v).groupby("marca")["qtd_avaliacoes"].sum()
    res["pct_avaliacoes"] = (av / av.sum()).round(3)
    return res[res["produtos"] >= n_min].sort_values("nota_media")


def compras_espacos_vazios(v: pd.DataFrame) -> pd.DataFrame:
    """Categorias folha com nota alta e poucos produtos: candidatas a ampliar sortimento."""
    f = v.groupby(["categoria", "categoria_folha"]).agg(
        produtos=("product_id", "size"), nota_media=("rating", "mean"),
        avaliacoes_mediana=("qtd_avaliacoes", "median")).round(2)
    return f[f["produtos"].between(3, 10) & (f["nota_media"] >= 4.3)].sort_values("nota_media", ascending=False)


def _reviews_com_produto(v, r):
    return r.merge(v[["product_id", "categoria", "categoria_folha", "rating", "desconto_pct",
                      "preco_desconto_brl", "faixa_preco", "qtd_avaliacoes", "product_name"]], on="product_id")


def risco_sinais_texto(v, r) -> pd.DataFrame:
    rr = _reviews_com_produto(v, r)
    base_neg = (rr["sentimento"] == "Negativo").mean()
    linhas = []
    for col in [c for c in rr.columns if c.startswith("sinal_")]:
        d = rr[rr[col]]
        linhas.append({"sinal": col.replace("sinal_", ""), "trechos": len(d), "produtos": d["product_id"].nunique(),
                       "pct_negativo": round((d["sentimento"] == "Negativo").mean(), 3),
                       "pct_negativo_base": round(base_neg, 3),
                       "principais_categorias": ", ".join(d["categoria_folha"].value_counts().head(3).index)})
    return pd.DataFrame(linhas).set_index("sinal")


def risco_nota_vs_texto(v, r, nota_min=4.2, pct_neg_min=0.375) -> pd.DataFrame:
    """Nota alta mas texto negativo: risco escondido atras da media."""
    ps = r.groupby("product_id").agg(pct_trechos_negativos=("sentimento", lambda x: (x == "Negativo").mean()))
    m = v.merge(ps, on="product_id")
    m = m[(m["rating"] >= nota_min) & (m["pct_trechos_negativos"] >= pct_neg_min)]
    return m.drop_duplicates("grupo_avaliacao").sort_values("qtd_avaliacoes", ascending=False)[
        ["product_name", "categoria_folha", "rating", "pct_trechos_negativos", "qtd_avaliacoes"]].round(3)


def cx_tempo_ate_falha(v, r) -> pd.DataFrame:
    rr = _reviews_com_produto(v, r).dropna(subset=["dias_ate_falha"])
    faixa = pd.cut(rr["dias_ate_falha"], [0, 7, 30, 90, 180, 365, 10_000],
                   labels=["até 1 semana", "até 1 mês", "1-3 meses", "3-6 meses", "6-12 meses", "mais de 1 ano"])
    res = faixa.value_counts(sort=False).rename("mencoes").to_frame()
    res["pct"] = (res["mencoes"] / res["mencoes"].sum()).round(3)
    return res


def cx_temas_por(v, r, t, coluna: str) -> pd.DataFrame:
    """% de trechos que citam cada tema, por faixa (ex.: faixa_preco)."""
    rr = _reviews_com_produto(v, r)
    tt = t.merge(rr[["trecho_id", coluna]], on="trecho_id")
    return (pd.crosstab(tt["tema"], tt[coluna]) / rr.groupby(coluna, observed=True).size()).round(3)


def cx_negatividade_tema_por_desconto(v, r, t) -> pd.DataFrame:
    rr = _reviews_com_produto(v, r)
    rr["faixa"] = pd.cut(rr["desconto_pct"], [-0.01, 0.4, 0.6, 1], labels=["até 40%", "40-60%", "acima de 60%"])
    tt = t.merge(rr[["trecho_id", "faixa", "sentimento"]], on="trecho_id")
    return tt.groupby(["tema", "faixa"], observed=True)["sentimento"].apply(
        lambda x: (x == "Negativo").mean()).unstack().round(3)


def cx_validacao_sentimento(v, r) -> float:
    ps = r.groupby("product_id")["sentimento_score"].mean()
    m = v.set_index("product_id").join(ps, how="inner")
    return round(m[["sentimento_score", "rating"]].corr("spearman").iloc[0, 1], 3)
