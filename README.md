# Amazon Product Performance & Customer Insights

**Tech Challenge Fase 4 · Pós Tech FIAP (DTAT).** Dashboard em Power BI que ajuda um e-commerce
a decidir **quais produtos, categorias e estratégias comerciais merecem atenção**.

## Índice

1. [O problema](#o-problema)
2. [Dados](#dados)
3. [Solução](#solução)
4. [Principais achados](#principais-achados)
5. [Como usar](#como-usar)
6. [Como reproduzir os dados](#como-reproduzir-os-dados)
7. [Estrutura do repositório](#estrutura-do-repositório)
8. [Limitações](#limitações)

## O problema

O catálogo tem muitos produtos com descontos agressivos, e não fica claro se o desconto traz
engajamento ou só reduz margem e satisfação. O projeto investiga a cadeia
**Preço → Desconto → Engajamento → Satisfação** e lê as reviews para entender o que o cliente
elogia e critica.

> Pergunta central: quais produtos, categorias e estratégias comerciais merecem maior atenção, e
> quais oportunidades os dados revelam?

## Dados

[Amazon Sales Dataset](https://www.kaggle.com/datasets/karkavelrajaj/amazon-sales-dataset) (Kaggle).
São 1.465 linhas, com preços em rúpias, nota, quantidade de avaliações e até 8 reviews por
produto. A base **não tem vendas nem datas**, então o engajamento é medido pela quantidade de
avaliações.

| Problema na base | Tratamento |
|---|---|
| 114 linhas duplicadas | Fica o registro com mais avaliações → **1.351 produtos** |
| Textos como `₹1,099`, `"64%"`, `"24,269"` | Convertidos para número; preços em R$ (cotação 0,05997) |
| 1 nota inválida e 2 contagens nulas | 3 produtos fora das análises de nota e engajamento |
| Variantes compartilham avaliações (93 grupos) | Cada grupo conta 1×; sem isso o total infla 27% |
| Categoria hierárquica `A\|B\|…\|Folha` | Categoria (traduzida), subcategoria e folha |
| Reviews concatenadas | Separadas em 10.295 trechos |

Nas reviews são aplicados sentimento **VADER**, 10 **temas** por palavra-chave e **sinais de risco**
(falsificação, segurança e tempo até o defeito).

## Solução

O relatório tem 5 páginas, com menu lateral de navegação e filtros:

| Página | Responde |
|---|---|
| 1. Visão Executiva | Como está o portfólio e onde estão os riscos? |
| 2. Produtos e Categorias | Quais produtos, subcategorias e marcas merecem atenção? |
| 3. Preços e Estratégia Comercial | O desconto funciona? |
| 4. Insights de Clientes | O que o cliente valoriza e critica? |
| 5. Recomendações | O que fazer, filtrável por área (Pricing, Marketing, Compras, Risco, CX)? |

Os produtos são classificados em quadrantes de **engajamento × nota**: Estrela, Oportunidade,
Revisar e Risco.

## Principais achados

- **Concentração:** 10% dos produtos têm 62% das avaliações, e os produtos Estrela somam 74,7%.
- **Desconto alto não compra satisfação:** a parcela de produtos com nota abaixo de 4 sobe de 16,6%
  (desconto de 0 a 20%) para 42% (acima de 80%).
- **Desconto alto também não traz mais engajamento:** a mediana de avaliações cai de cerca de 7 mil
  (até 40% de desconto) para 3 a 4 mil (acima de 40%).
- **Qualidade precoce:** 48,8% das falhas relatadas acontecem no primeiro mês de uso.
- **Riscos para triagem:** 36 produtos com suspeita de falsificação e 49 com alerta de segurança
  nas reviews.

## Como usar

**Requisito:** Power BI Desktop atualizado (Windows).

1. Baixe ou clone o repositório.
2. Abra `powerbi/AmazonInsights.pbip` no Power BI Desktop.
3. Se aparecer erro de fonte de dados, vá em **Página Inicial → Transformar dados → Editar
   parâmetros** e informe em `PastaDados` o caminho da pasta `powerbi\dados\`, **terminando com `\`**.
4. Clique em **Atualizar**.
5. Para navegar pelo menu lateral no Desktop, use **Ctrl + clique** nos botões. No serviço do Power BI
   ou no `.pbix` publicado, basta um clique.

Para gerar o `.pbix`, use **Arquivo → Salvar como → Arquivo do Power BI (.pbix)**.

Os números esperados para validação estão em [`docs/guia_powerbi.md`](docs/guia_powerbi.md).

## Como reproduzir os dados

Opcional, pois os dados tratados já estão no repositório. Requer Python 3.

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python scripts/00_download_kaggle.py
.venv\Scripts\python scripts/01_tratamento.py
.venv\Scripts\jupyter nbconvert --to notebook --execute --inplace notebooks/02_analises.ipynb
```

> `scripts/03_gerar_pbip.py` recria o projeto Power BI do zero, com o layout original. Não rode
> esse script se quiser manter o visual atual do relatório.

## Estrutura do repositório

```
src/                       regras de negócio (limpeza, reviews, análises)
scripts/                   download da base, tratamento e gerador do PBIP
notebooks/02_analises.ipynb  perguntas do desafio e lentes por área
data/processed/            produtos, reviews e temas tratados
results/tabelas/           tabelas exportadas pelo notebook
powerbi/                   projeto Power BI (.pbip) e pasta dados/
docs/guia_powerbi.md       passo a passo e números de validação
```

## Limitações

- O engajamento é medido por avaliações, não por vendas. Sem datas, não há análise temporal.
- Há no máximo 8 reviews por produto, sem nota individual. Temas e sinais de risco são busca por
  padrão e têm falsos positivos, então servem para triagem.
- Correlação não implica causa.
