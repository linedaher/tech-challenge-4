# Amazon Product Performance & Customer Insights

**Tech Challenge Fase 4 — Pós Tech FIAP (DTAT).** Solução analítica em Power BI para
apoiar decisões de portfólio e experiência do cliente de um e-commerce, investigando a
cadeia **Preço → Desconto → Engajamento → Satisfação**.

> Pergunta central: quais produtos, categorias e estratégias comerciais merecem maior
> atenção, e quais oportunidades os dados revelam?

## Dataset

[Amazon Sales Dataset](https://www.kaggle.com/datasets/karkavelrajaj/amazon-sales-dataset)
(Kaggle, `karkavelrajaj/amazon-sales-dataset`): 1.465 linhas, preços em rúpias (₹),
nota, quantidade de avaliações e até 8 reviews por produto. **Não tem vendas nem datas**:
engajamento = quantidade de avaliações (`rating_count`).

## Tratamento (o que a base exigiu)

| Problema encontrado | Tratamento |
|---|---|
| 114 linhas duplicadas (mesmo produto coletado 2×) | Fica o registro com mais avaliações → **1.351 produtos** |
| Preço `₹1,099`, desconto `"64%"`, contagem `"24,269"` | Convertidos para número; preços em R$ (cotação 0,05997, PTAX USD × BCE INR, 13/11/2026) |
| 1 nota inválida (`|`), 2 contagens nulas | 3 produtos marcados e fora das análises de nota/engajamento |
| **Variantes compartilham avaliações** (241 produtos em 93 grupos) | Somas de engajamento contam cada grupo 1× — sem isso o total infla 27% |
| Categoria hierárquica `A|B|…|Folha` | Categoria (traduzida), subcategoria e categoria folha |
| Reviews concatenadas por vírgula, com vírgulas no texto | Separadas por `,` sem espaço; URLs removidas → 10.295 trechos |

Customer Insights: sentimento com **VADER** (reviews em inglês), 10 **temas** por
palavra-chave e **sinais de risco** no texto (falsificação, segurança, tempo até o defeito).

## Estrutura

```
src/                 regras de negócio (limpeza, reviews, análises) — única fonte de verdade
scripts/00_download_kaggle.py   baixa a base (usa ~/.kaggle/kaggle.json)
scripts/01_tratamento.py        gera data/processed/ (produtos, reviews, temas, log)
scripts/03_gerar_pbip.py        gera o projeto Power BI (TMDL + PBIR) em powerbi/
notebooks/02_analises.ipynb     perguntas do desafio + lentes por área (executado)
results/tabelas/                21 tabelas exportadas pelo notebook
powerbi/                        projeto PBIP + dados/ → abrir no Power BI Desktop
docs/guia_powerbi.md            passo a passo no Windows + números esperados para validação
```

## Como reproduzir

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/00_download_kaggle.py
.venv/bin/python scripts/01_tratamento.py
(cd notebooks && ../.venv/bin/jupyter nbconvert --to notebook --execute --inplace 02_analises.ipynb)
.venv/bin/python scripts/03_gerar_pbip.py
```

Depois, no Windows, siga [`docs/guia_powerbi.md`](docs/guia_powerbi.md).

## Limitações

- Engajamento é proxy (avaliações), não venda. Sem datas: não há análise temporal.
- Até 8 reviews por produto e sem nota individual: o sentimento concorda moderadamente
  com a nota (correlação de Spearman 0,33). Temas e sinais de risco são busca por padrão,
  com falso positivo — servem para triagem e leitura manual.
- Correlações não implicam causa (ex.: preço terminado em 9 tem mais avaliações, mas
  grandes marcas usam mais esse padrão).
