"""Customer Insights: separa as reviews, calcula sentimento (VADER) e classifica temas.

Limitacoes da fonte (documentar no dashboard):
- cada produto traz no maximo 8 reviews, uma amostra pequena perto de `rating_count`;
- as reviews nao tem nota individual, so a nota media do produto;
- `review_content` concatena reviews por virgula e o proprio texto tem virgulas,
  entao a separacao 1 linha = 1 review so e' confiavel para `review_title`.
"""

import re

import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# separador entre reviews: virgula SEM espaco depois (dentro do texto vem ', ')
SEP = re.compile(r",(?=\S)")
URL = re.compile(r"https?://\S+")

# temas por palavra-chave (as reviews estao em ingles); ordem = prioridade de exibicao
TEMAS = {
    "Qualidade e acabamento": r"\bquality\b|\bbuild\b|sturdy|premium|well made|solid",
    "Custo-benefício": r"value for money|\bworth\b|\bprice\b|\bcheap\b|affordable|budget|\bvfm\b",
    "Durabilidade e defeitos": r"stopped working|not working|\bbroke|damaged|defect|faulty|dead|durab",
    "Bateria e carregamento": r"battery|charg",
    "Som e áudio": r"\bsound\b|\bbass\b|audio|\bmic\b|volume",
    "Desempenho e velocidade": r"\bspeed\b|\bfast\b|\bslow\b|performance|\blag",
    "Instalação e uso": r"install|setup|set up|easy to use|user friendly|\bremote\b",
    "Entrega e embalagem": r"deliver|packag|packing|arrived|received",
    "Garantia e atendimento": r"warranty|replace|refund|customer (care|service)|\breturn",
    "Tamanho e encaixe": r"\bsize\b|\bfit\b|length|\bshort\b|\bsmall\b|\bbig\b",
}
TEMAS_RE = {t: re.compile(p, re.IGNORECASE) for t, p in TEMAS.items()}

# sinais de risco/contexto no texto (flags por trecho). Sao buscas por padrao, com
# falso positivo conhecido: servem para triagem e leitura manual, nao como taxa exata.
_SEM_MARCAS = re.compile(r"fire[- ]?boltt|fire ?tv|fire ?stick", re.IGNORECASE)
SINAIS = {
    "sinal_falsificacao": r"\b(?:fake|duplicate|counterfeit|not original|not genuine|refurbished|used product|first copy)",
    "sinal_seguranca": r"\b(?:overheat\w*|gets? (?:very |too |extremely )?(?:hot|heated)|smoke|sparks?|sparking|"
                       r"(?:electric )?shock|caught fire|melt(?:ed|ing)?|burn(?:t|ed|ing)? (?:smell|out|mark))\b",
    "sinal_presente": r"\b(?:gift|gifted|for my (?:mom|mother|father|dad|wife|husband|son|daughter|parents|kid))",
    "sinal_concorrente": r"\b(?:than (?:the )?(?:original|apple|samsung|boat|mi|oneplus|sony|jbl)|compared to)",
}
SINAIS_RE = {k: re.compile(p, re.IGNORECASE) for k, p in SINAIS.items()}

# "stopped working after 2 months" -> 60 dias
_TEMPO = re.compile(r"(?:after|within|in)\s+(?:just\s+|only\s+)?(\d+|a|one|two|three|few)\s+(day|week|month|year)s?",
                    re.IGNORECASE)
_FALHA = re.compile(r"stop|not work|broke|dead|damag|fail", re.IGNORECASE)
_NUM = {"a": 1, "one": 1, "two": 2, "three": 3, "few": 3}
_DIAS = {"day": 1, "week": 7, "month": 30, "year": 365}


def dias_ate_falha(texto: str, sentimento: str) -> float | None:
    """Dias citados ate a falha, so quando o trecho fala de defeito ou e' negativo."""
    m = _TEMPO.search(texto)
    if not m or not (sentimento == "Negativo" or _FALHA.search(texto)):
        return None
    n = m.group(1).lower()
    return int(_NUM.get(n, n)) * _DIAS[m.group(2).lower()]


_vader = SentimentIntensityAnalyzer()


def classe_sentimento(compound: float) -> str:
    # limiares padrao do VADER
    if compound >= 0.05:
        return "Positivo"
    if compound <= -0.05:
        return "Negativo"
    return "Neutro"


def separar_titulos(prod_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """1 linha por review a partir de review_id + review_title.

    So usa produtos em que o numero de titulos bate com o numero de review_id
    (o resto nao tem como alinhar com seguranca e fica de fora, contado no log).
    """
    linhas, descartados = [], 0
    for _, r in prod_raw.iterrows():
        ids = r["review_id"].split(",")
        titulos = SEP.split(r["review_title"])
        if len(ids) != len(titulos):
            descartados += 1
            continue
        for rid, tit in zip(ids, titulos):
            linhas.append({"review_id": rid.strip(), "product_id": r["product_id"], "titulo": tit.strip()})
    df = pd.DataFrame(linhas).drop_duplicates("review_id")
    return df, {"produtos_sem_alinhamento_titulo": descartados, "reviews_titulo": len(df)}


def pontuar(texto: str) -> float:
    return _vader.polarity_scores(texto)["compound"]


def temas_do_texto(texto: str) -> list[str]:
    return [t for t, rx in TEMAS_RE.items() if rx.search(texto)]


def fatiar_conteudo(conteudo: str) -> list[str]:
    """Quebra o review_content em trechos (aproximadamente 1 por review), sem URLs."""
    return [p.strip() for p in SEP.split(URL.sub("", conteudo)) if len(p.strip()) > 3]


def tabela_reviews(prod_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Devolve (fReview, fReviewTema, log).

    fReview: 1 linha por trecho de review (conteudo), com sentimento.
    fReviewTema: ponte trecho x tema (um trecho pode ter varios temas).
    """
    linhas = []
    for _, r in prod_raw.iterrows():
        for i, trecho in enumerate(fatiar_conteudo(r["review_content"])):
            linhas.append({"trecho_id": f"{r['product_id']}_{i}", "product_id": r["product_id"], "texto": trecho})
    rev = pd.DataFrame(linhas)
    rev["sentimento_score"] = rev["texto"].map(pontuar).round(4)
    rev["sentimento"] = rev["sentimento_score"].map(classe_sentimento)
    rev["qtd_palavras"] = rev["texto"].str.split().str.len()
    sem_marcas = rev["texto"].str.replace(_SEM_MARCAS, "", regex=True)
    for col, rx in SINAIS_RE.items():
        rev[col] = sem_marcas.map(lambda s, rx=rx: bool(rx.search(s)))
    rev["dias_ate_falha"] = [dias_ate_falha(t, s) for t, s in zip(rev["texto"], rev["sentimento"])]

    ponte = rev[["trecho_id", "texto"]].assign(tema=rev["texto"].map(temas_do_texto)).explode("tema")
    ponte = ponte.dropna(subset=["tema"])[["trecho_id", "tema"]]
    log = {"trechos_review": len(rev), "trechos_com_tema": ponte["trecho_id"].nunique()}
    return rev, ponte.reset_index(drop=True), log
