# Guia — abrir o projeto no Power BI Desktop e gerar o `.pbix`

O dashboard já vem pronto como **projeto PBIP** (formato de projeto do Power BI em texto),
gerado por `scripts/03_gerar_pbip.py`. Ele traz o modelo (Power Query, medidas DAX,
relacionamentos) e as 5 páginas com os visuais. No Windows, você só abre, aponta a pasta
dos dados, confere os números e salva como `.pbix`.

## 1. Preparar (uma vez)

1. Instale o **Power BI Desktop** (Microsoft Store ou site da Microsoft) e mantenha atualizado.
2. Em *Arquivo > Opções e configurações > Opções > Recursos de visualização*, confirme que
   **"Formato de projeto do Power BI (.pbip)"** e **"Armazenar relatórios usando o formato PBIR"**
   estão marcados (nas versões recentes já vêm ligados). Reinicie o Desktop se mudar algo.
3. Copie a pasta `powerbi/` inteira deste repositório para o Windows. Exemplo:
   `C:\TechChallenge4\powerbi\`. Ela contém:
   - `AmazonInsights.pbip` — o arquivo que você abre
   - `AmazonInsights.SemanticModel/` e `AmazonInsights.Report/` — modelo e relatório
   - `dados/` — `amazon.csv` (bruto, Kaggle), `fReview.csv` e `fReviewTema.csv` (gerados em Python)

## 2. Abrir e apontar os dados

1. *Arquivo > Abrir* → `AmazonInsights.pbip`.
2. Vai aparecer erro de fonte de dados (normal: o caminho padrão não existe). Vá em
   **Página Inicial > Transformar dados > Editar parâmetros** e preencha:
   - `PastaDados` = caminho da pasta `dados`, **terminando com `\`**
     (ex.: `C:\TechChallenge4\powerbi\dados\`)
   - `CotacaoINRBRL` = `0.05997` (já preenchido; fonte no próprio parâmetro)
3. Clique em **Aplicar alterações** / **Atualizar**.

> Se aparecer aviso de privacidade de dados, escolha *Ignorar níveis de privacidade* para
> este arquivo (são só arquivos locais).

## 3. Conferir os números (validação Python × Power BI)

Crie um visual de **Cartão** temporário com cada medida (ou use os cartões das páginas)
e confira, **sem nenhum filtro aplicado**:

| Medida | Valor esperado |
|---|---|
| Produtos | 1.351 |
| Produtos Avaliados | 1.348 |
| Avaliações | 18.697.002 |
| Avaliações por Produto (mediana) | 4.740 |
| Nota Média | 4,09 |
| % Produtos Abaixo de 4 | 25,1% |
| Nota Ponderada | 4,11 |
| Desconto Médio | 46,7% |
| Preço Mediano (R$) | R$ 53,91 |
| Preço Médio Original (R$) | R$ 341,26 |
| Preço Médio com Desconto (R$) | R$ 198,18 |
| Economia Média (R$) | R$ 143,08 |
| Trechos de Review | 10.295 |
| % Trechos Positivos / Negativos | 76,9% / 10,5% |
| Sentimento Médio | 0,41 |
| Menções | 10.398 |
| Produtos com Suspeita de Falsificação | 36 |
| Produtos com Alerta de Segurança | 49 |
| Falhas Relatadas | 125 |
| % Falhas no 1º Mês | 48,8% |

Contagens por coluna (arraste a coluna + `Produtos` numa tabela):

- `quadrante`: Estrela 478 · Oportunidade 372 · Revisar 301 · Risco 197 · Sem avaliação 3
- `categoria`: Eletrônicos 490 · Casa e Cozinha 448 · Informática e Acessórios 375 · Escritório 31 · Outros 7

Se algum número divergir, o tratamento do Power Query (`dProduto`) não está espelhando
`src/limpeza.py` — me mande o valor que apareceu.

## 4. Ajustes visuais no Desktop (o que o arquivo de texto não garante)

O projeto define **quais** visuais existem, **onde** ficam e **o que** mostram. O acabamento
fica com você:

1. **Cores dos quadrantes** (páginas 1 e 2): em *Formatar > Cores*, use
   Estrela = verde `#2E8B57`, Risco = vermelho `#C0392B`, Oportunidade = azul `#146EB4`,
   Revisar = cinza `#8E8E8E`. Mantenha as mesmas cores em todas as páginas.
2. **Navegação**: *Inserir > Botões > Navegador > Navegador de páginas* no topo de cada página
   (um clique cria os botões das 5 páginas). Depois, oculte as abas se quiser.
3. **Rótulos de dados** nos gráficos de colunas/barras (*Formatar > Rótulos de dados*: Ativado).
4. **Tooltips**: na dispersão da página 2, adicione `categoria` e `Desconto Médio` em *Dicas de ferramenta*.
5. **Sincronizar segmentações** de `categoria` entre páginas: *Exibir > Sincronizar segmentações*.
6. Revise sobreposições: se algum visual ficou cortado, ajuste o tamanho à mão.

## 5. Salvar a entrega

*Arquivo > Salvar como* → tipo **Arquivo do Power BI (.pbix)** → `TechChallenge4_AmazonInsights.pbix`.

Continue editando pelo `.pbip` se quiser versionar no git (cada mudança vira diff legível);
o `.pbix` é só o arquivo final de entrega.

## O que tem em cada página

| Página | Pergunta que responde | Visuais |
|---|---|---|
| 1. Visão Executiva | Como está o portfólio? Onde estão os riscos? | 6 KPIs, avaliações por categoria, quadrantes, % nota < 4 por faixa de desconto, mensagens-chave |
| 2. Produtos e Categorias | Quais produtos/categorias/marcas merecem atenção? | Dispersão avaliações × nota (cada ponto = produto), subcategorias, produtos por quadrante, marcas |
| 3. Preços e Estratégia | Desconto funciona? | Faixa de desconto × nota e × engajamento, desconto × nota por categoria folha, faixas de preço |
| 4. Customer Insights | O que o cliente valoriza e critica? | Temas × sentimento, % negativo por tema, tempo até o defeito, trechos reais filtráveis |
| 5. Recomendações | O que fazer? | Tabela achado → evidência → ação, com **lente por área**, e as 3 mensagens para a liderança |

## Modelo de dados

```
dProduto (1) ──< fReview (N) >──< fReviewTema (N)      dRecomendacao (isolada)
  product_id      product_id, trecho_id   trecho_id      _Medidas (só medidas)
```

- `fReviewTema → fReview` com filtro em **ambas as direções**, para a segmentação de *tema*
  filtrar os trechos.
- Todas as medidas ficam em `_Medidas`, organizadas em pastas (Portfólio, Engajamento,
  Satisfação, Preço e Desconto, Customer Insights, Riscos), cada uma com descrição.
