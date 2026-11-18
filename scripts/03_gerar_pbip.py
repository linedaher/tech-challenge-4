"""Gera o projeto Power BI (PBIP) em powerbi/: modelo em TMDL + relatorio em PBIR.

Abrir no Windows: Power BI Desktop > Arquivo > Abrir > powerbi/AmazonInsights.pbip,
ajustar o parametro PastaDados (Transformar dados > Gerenciar parametros) e
Salvar como .pbix.

- Tratamento de produtos: refeito em Power Query (M) a partir do amazon.csv bruto,
  espelhando src/limpeza.py (os numeros esperados estao em docs/validacao_powerbi.md).
- fReview / fReviewTema: importados dos CSVs gerados por scripts/01_tratamento.py.

Uso:  python scripts/03_gerar_pbip.py
"""

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import COTACAO_INR_BRL, RAIZ  # noqa: E402

PBI = RAIZ / "powerbi"
NOME = "AmazonInsights"
MODELO = PBI / f"{NOME}.SemanticModel"
RELAT = PBI / f"{NOME}.Report"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"


def escrever(caminho: Path, conteudo) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(conteudo, str):
        conteudo = json.dumps(conteudo, indent=2, ensure_ascii=False)
    caminho.write_text(conteudo, encoding="utf-8")


def uid(semente: str) -> str:
    """UUID deterministico (regerar o projeto nao muda ids a toa no git)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"tc4/{semente}"))


def indentar(texto: str, n: int) -> str:
    return "\n".join(("\t" * n + linha) if linha.strip() else "" for linha in texto.strip("\n").splitlines())


# =========================================================== MODELO (TMDL)
M_PRODUTO = r'''
let
    // 1. Leitura do CSV bruto do Kaggle (UTF-8; textos com virgula vem entre aspas)
    Fonte = Csv.Document(File.Contents(PastaDados & "amazon.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalhos = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    Colunas = Table.SelectColumns(Cabecalhos, {"product_id", "product_name", "category", "discounted_price", "actual_price", "discount_percentage", "rating", "rating_count", "about_product", "img_link", "product_link"}),

    // 2. Texto -> numero: remove "₹", "," e "%" e le no padrao en-US (ponto decimal).
    //    Valores invalidos (ex.: rating "|", rating_count vazio) viram null.
    ParaNumero = (t as nullable text) as nullable number => try Number.FromText(Text.Remove(t, {"₹", ",", "%"}), "en-US") otherwise null,
    Numeros = Table.TransformColumns(Colunas, {
        {"actual_price", ParaNumero, type nullable number},
        {"discounted_price", ParaNumero, type nullable number},
        {"discount_percentage", each ParaNumero(_) / 100, type nullable number},
        {"rating", ParaNumero, type nullable number},
        {"rating_count", ParaNumero, type nullable number}}),
    Renomeado = Table.RenameColumns(Numeros, {
        {"actual_price", "preco_original_inr"}, {"discounted_price", "preco_desconto_inr"},
        {"discount_percentage", "desconto_pct"}, {"rating_count", "qtd_avaliacoes"}}),

    // 3. Duplicados: o mesmo produto foi coletado 2x (114 linhas). Fica o registro com mais avaliacoes.
    Ordenado = Table.Buffer(Table.Sort(Renomeado, {{"qtd_avaliacoes", Order.Descending}})),
    SemDuplicados = Table.Distinct(Ordenado, {"product_id"}),

    // 4. Sem nota ou sem contagem: fica marcado e sai das analises de satisfacao/engajamento
    FlagSemAvaliacao = Table.AddColumn(SemDuplicados, "flag_sem_avaliacao", each [rating] = null or [qtd_avaliacoes] = null, type logical),

    // 5. Conversao para R$ (parametro CotacaoINRBRL)
    PrecoOriginalBRL = Table.AddColumn(FlagSemAvaliacao, "preco_original_brl", each Number.Round([preco_original_inr] * CotacaoINRBRL, 2), type number),
    PrecoDescontoBRL = Table.AddColumn(PrecoOriginalBRL, "preco_desconto_brl", each Number.Round([preco_desconto_inr] * CotacaoINRBRL, 2), type number),
    EconomiaBRL = Table.AddColumn(PrecoDescontoBRL, "economia_brl", each [preco_original_brl] - [preco_desconto_brl], type number),

    // 6. Hierarquia de categoria: "A|B|...|Folha" -> categoria (traduzida), subcategoria e folha
    Traducao = [Electronics = "Eletrônicos", #"Computers&Accessories" = "Informática e Acessórios", #"Home&Kitchen" = "Casa e Cozinha", OfficeProducts = "Escritório"],
    SepararCamel = (t as nullable text) as nullable text =>
        if t = null then null else
        let
            comE = Text.Replace(t, "&", " & "),
            partes = Splitter.SplitTextByCharacterTransition({"a".."z"}, {"A".."Z"})(comE),
            junto = Text.Combine(partes, " ")
        in
            Text.Combine(List.Select(Text.Split(junto, " "), each _ <> ""), " "),
    Niveis = Table.AddColumn(EconomiaBRL, "niveis", each Text.Split([category], "|")),
    Categoria = Table.AddColumn(Niveis, "categoria", each Record.FieldOrDefault(Traducao, [niveis]{0}, "Outros"), type text),
    Subcategoria = Table.AddColumn(Categoria, "subcategoria", each SepararCamel([niveis]{1}?), type text),
    Folha = Table.AddColumn(Subcategoria, "categoria_folha", each SepararCamel(List.Last([niveis])), type text),

    // 7. Marca = 1a palavra do nome. Variantes (cor/modelo) compartilham nota e contagem na Amazon:
    //    mesma marca + mesma nota + mesma contagem = mesmo grupo, somado 1x na medida [Avaliações].
    Marca = Table.AddColumn(Folha, "marca", each Text.Select(Text.Lower(Text.BeforeDelimiter(Text.Trim([product_name]), " ")), {"a".."z", "0".."9"}), type text),
    GrupoAvaliacao = Table.AddColumn(Marca, "grupo_avaliacao", each
        if [flag_sem_avaliacao] then [product_id]
        else Text.Lower(Text.BeforeDelimiter(Text.Trim([product_name]), " ")) & "|" & Number.ToText([rating], "G", "en-US") & "|" & Number.ToText([qtd_avaliacoes], "G", "en-US"), type text),

    // 8. Faixas de desconto (com coluna de ordem para os graficos)
    FaixaDesconto = Table.AddColumn(GrupoAvaliacao, "faixa_desconto", each
        if [desconto_pct] <= 0.2 then "0-20%" else if [desconto_pct] <= 0.4 then "20-40%"
        else if [desconto_pct] <= 0.6 then "40-60%" else if [desconto_pct] <= 0.8 then "60-80%" else "80%+", type text),
    FaixaDescontoOrdem = Table.AddColumn(FaixaDesconto, "faixa_desconto_ordem", each
        List.PositionOf({"0-20%", "20-40%", "40-60%", "60-80%", "80%+"}, [faixa_desconto]) + 1, Int64.Type),

    // 9. Quartis de preco e quadrantes, calculados so sobre produtos com avaliacao valida
    Validos = Table.SelectRows(FaixaDescontoOrdem, each not [flag_sem_avaliacao]),
    Quartis = List.Percentile(Validos[preco_desconto_brl], {0.25, 0.5, 0.75}, [PercentileMode = PercentileMode.ExcelInc]),
    FaixaPreco = Table.AddColumn(FaixaDescontoOrdem, "faixa_preco", each
        if [preco_desconto_brl] <= Quartis{0} then "Q1 (mais baratos)" else if [preco_desconto_brl] <= Quartis{1} then "Q2"
        else if [preco_desconto_brl] <= Quartis{2} then "Q3" else "Q4 (mais caros)", type text),
    FaixaPrecoOrdem = Table.AddColumn(FaixaPreco, "faixa_preco_ordem", each Number.From(Text.Middle([faixa_preco], 1, 1)), Int64.Type),
    MedianaAvaliacoes = List.Median(Validos[qtd_avaliacoes]),
    MedianaNota = List.Median(Validos[rating]),
    Quadrante = Table.AddColumn(FaixaPrecoOrdem, "quadrante", each
        if [flag_sem_avaliacao] then "Sem avaliação"
        else if [qtd_avaliacoes] >= MedianaAvaliacoes and [rating] >= MedianaNota then "Estrela"
        else if [qtd_avaliacoes] >= MedianaAvaliacoes then "Risco"
        else if [rating] >= MedianaNota then "Oportunidade"
        else "Revisar", type text),

    // 10. Tamanho do titulo (lente de Marketing)
    TamanhoTitulo = Table.AddColumn(Quadrante, "tamanho_titulo", each Text.Length([product_name]), Int64.Type),

    Final = Table.RemoveColumns(TamanhoTitulo, {"niveis", "category"})
in
    Final
'''

M_REVIEW = r'''
let
    // Trechos de review com sentimento (VADER) e sinais de texto, gerados por scripts/01_tratamento.py
    Fonte = Csv.Document(File.Contents(PastaDados & "fReview.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalhos = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    Logicos = Table.TransformColumns(Cabecalhos, {
        {"sinal_falsificacao", each _ = "True", type logical},
        {"sinal_seguranca", each _ = "True", type logical},
        {"sinal_presente", each _ = "True", type logical},
        {"sinal_concorrente", each _ = "True", type logical}}),
    VazioParaNull = Table.ReplaceValue(Logicos, "", null, Replacer.ReplaceValue, {"dias_ate_falha"}),
    Tipos = Table.TransformColumnTypes(VazioParaNull, {
        {"trecho_id", type text}, {"product_id", type text}, {"texto", type text},
        {"sentimento_score", type number}, {"sentimento", type text}, {"qtd_palavras", Int64.Type},
        {"dias_ate_falha", type number}}, "en-US"),
    FaixaFalha = Table.AddColumn(Tipos, "faixa_tempo_falha", each
        if [dias_ate_falha] = null then null
        else if [dias_ate_falha] <= 7 then "1. Até 1 semana" else if [dias_ate_falha] <= 30 then "2. Até 1 mês"
        else if [dias_ate_falha] <= 90 then "3. 1 a 3 meses" else if [dias_ate_falha] <= 180 then "4. 3 a 6 meses"
        else if [dias_ate_falha] <= 365 then "5. 6 a 12 meses" else "6. Mais de 1 ano", type text)
in
    FaixaFalha
'''

M_TEMA = r'''
let
    Fonte = Csv.Document(File.Contents(PastaDados & "fReviewTema.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalhos = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    Tipos = Table.TransformColumnTypes(Cabecalhos, {{"trecho_id", type text}, {"tema", type text}})
in
    Tipos
'''

# (nome, tipo TMDL, formatString, oculta, sortBy)
COLS_PRODUTO = [
    ("product_id", "string", None, False, None), ("product_name", "string", None, False, None),
    ("categoria", "string", None, False, None), ("subcategoria", "string", None, False, None),
    ("categoria_folha", "string", None, False, None), ("marca", "string", None, False, None),
    ("preco_original_inr", "double", "#,##0", True, None), ("preco_desconto_inr", "double", "#,##0", True, None),
    ("preco_original_brl", "double", '"R$" #,##0.00', False, None),
    ("preco_desconto_brl", "double", '"R$" #,##0.00', False, None),
    ("economia_brl", "double", '"R$" #,##0.00', False, None),
    ("desconto_pct", "double", "0%", False, None), ("rating", "double", "0.0", False, None),
    ("qtd_avaliacoes", "double", "#,##0", False, None), ("flag_sem_avaliacao", "boolean", None, False, None),
    ("grupo_avaliacao", "string", None, True, None),
    ("faixa_desconto", "string", None, False, "faixa_desconto_ordem"),
    ("faixa_desconto_ordem", "int64", "0", True, None),
    ("faixa_preco", "string", None, False, "faixa_preco_ordem"), ("faixa_preco_ordem", "int64", "0", True, None),
    ("quadrante", "string", None, False, None), ("tamanho_titulo", "int64", "0", False, None),
    ("about_product", "string", None, True, None), ("img_link", "string", None, True, None),
    ("product_link", "string", None, False, None),
]
COLS_REVIEW = [
    ("trecho_id", "string", None, True, None), ("product_id", "string", None, True, None),
    ("texto", "string", None, False, None), ("sentimento_score", "double", "0.00", False, None),
    ("sentimento", "string", None, False, None), ("qtd_palavras", "int64", "0", False, None),
    ("sinal_falsificacao", "boolean", None, False, None), ("sinal_seguranca", "boolean", None, False, None),
    ("sinal_presente", "boolean", None, False, None), ("sinal_concorrente", "boolean", None, False, None),
    ("dias_ate_falha", "double", "0", False, None), ("faixa_tempo_falha", "string", None, False, None),
]
COLS_TEMA = [("trecho_id", "string", None, True, None), ("tema", "string", None, False, None)]

# (pasta, nome, DAX, formato, descricao)
MEDIDAS = [
    ("Portfólio", "Produtos", "COUNTROWS ( dProduto )", "#,##0", "Produtos únicos após remover duplicados."),
    ("Portfólio", "Produtos Avaliados",
     "CALCULATE ( COUNTROWS ( dProduto ), dProduto[flag_sem_avaliacao] = FALSE () )", "#,##0",
     "Produtos com nota e quantidade de avaliações válidas."),
    ("Engajamento", "Avaliações",
     "CALCULATE (\n    SUMX ( VALUES ( dProduto[grupo_avaliacao] ), CALCULATE ( MAX ( dProduto[qtd_avaliacoes] ) ) ),\n    dProduto[flag_sem_avaliacao] = FALSE ()\n)", "#,##0",
     "Total de avaliações contando cada grupo de variantes uma única vez (variantes compartilham avaliações na Amazon)."),
    ("Engajamento", "% das Avaliações",
     "DIVIDE ( [Avaliações], CALCULATE ( [Avaliações], ALLSELECTED ( dProduto ) ) )", "0.0%",
     "Participação no total de avaliações da seleção."),
    ("Engajamento", "Avaliações por Produto (mediana)",
     "CALCULATE ( MEDIAN ( dProduto[qtd_avaliacoes] ), dProduto[flag_sem_avaliacao] = FALSE () )", "#,##0",
     "Mediana de avaliações por produto: menos sensível aos campeões de venda que a média."),
    ("Satisfação", "Nota Média", "AVERAGE ( dProduto[rating] )", "0.00", "Média simples da nota (1 a 5)."),
    ("Satisfação", "% Produtos Abaixo de 4",
     "DIVIDE (\n    CALCULATE ( COUNTROWS ( dProduto ), dProduto[rating] < 4, dProduto[flag_sem_avaliacao] = FALSE () ),\n    [Produtos Avaliados]\n)",
     "0.0%", "Parcela de produtos com nota menor que 4: o limiar em que o cliente percebe o produto como mediano."),
    ("Satisfação", "Nota Ponderada",
     "VAR C = CALCULATE ( AVERAGE ( dProduto[rating] ), ALL ( dProduto ) )\n"
     "VAR m = CALCULATE ( PERCENTILE.INC ( dProduto[qtd_avaliacoes], 0.25 ), ALL ( dProduto ), dProduto[flag_sem_avaliacao] = FALSE () )\n"
     "RETURN\n    AVERAGEX (\n        FILTER ( dProduto, NOT dProduto[flag_sem_avaliacao] ),\n"
     "        DIVIDE ( dProduto[qtd_avaliacoes], dProduto[qtd_avaliacoes] + m ) * dProduto[rating]\n"
     "            + DIVIDE ( m, dProduto[qtd_avaliacoes] + m ) * C\n    )",
     "0.00", "Média bayesiana (fórmula IMDb): produtos com poucas avaliações são puxados para a média geral, evitando que nota 5 com 2 avaliações lidere rankings."),
    ("Preço e Desconto", "Desconto Médio", "AVERAGE ( dProduto[desconto_pct] )", "0.0%", "Média do percentual de desconto."),
    ("Preço e Desconto", "Preço Mediano (R$)", "MEDIAN ( dProduto[preco_desconto_brl] )", '"R$" #,##0.00',
     "Mediana do preço com desconto, convertido de ₹ para R$ pela cotação do parâmetro CotacaoINRBRL."),
    ("Preço e Desconto", "Preço Médio Original (R$)", "AVERAGE ( dProduto[preco_original_brl] )", '"R$" #,##0.00', None),
    ("Preço e Desconto", "Preço Médio com Desconto (R$)", "AVERAGE ( dProduto[preco_desconto_brl] )", '"R$" #,##0.00', None),
    ("Preço e Desconto", "Economia Média (R$)", "AVERAGE ( dProduto[economia_brl] )", '"R$" #,##0.00',
     "Diferença média em reais entre preço original e preço com desconto."),
    ("Customer Insights", "Trechos de Review", "COUNTROWS ( fReview )", "#,##0",
     "Trechos de review analisados (até 8 reviews por produto na fonte)."),
    ("Customer Insights", "% Trechos Positivos",
     'DIVIDE ( CALCULATE ( COUNTROWS ( fReview ), fReview[sentimento] = "Positivo" ), [Trechos de Review] )', "0.0%", None),
    ("Customer Insights", "% Trechos Negativos",
     'DIVIDE ( CALCULATE ( COUNTROWS ( fReview ), fReview[sentimento] = "Negativo" ), [Trechos de Review] )', "0.0%", None),
    ("Customer Insights", "Sentimento Médio", "AVERAGE ( fReview[sentimento_score] )", "0.00",
     "Score VADER médio (-1 muito negativo a +1 muito positivo)."),
    ("Customer Insights", "Menções", "COUNTROWS ( fReviewTema )", "#,##0", "Trechos que citam o tema."),
    ("Customer Insights", "% Negativo do Tema",
     'DIVIDE ( CALCULATE ( [Menções], fReview[sentimento] = "Negativo" ), [Menções] )', "0.0%",
     "Entre os trechos que citam o tema, quantos são negativos."),
    ("Customer Insights", "% dos Trechos que Citam",
     "DIVIDE ( [Menções], CALCULATE ( [Trechos de Review], REMOVEFILTERS ( fReviewTema ) ) )", "0.0%",
     "Frequência do tema: menções / todos os trechos."),
    ("Riscos", "Produtos com Suspeita de Falsificação",
     "CALCULATE ( DISTINCTCOUNT ( fReview[product_id] ), fReview[sinal_falsificacao] = TRUE () )", "#,##0",
     "Produtos com review citando fake / not original / used. Triagem: requer leitura manual."),
    ("Riscos", "Produtos com Alerta de Segurança",
     "CALCULATE ( DISTINCTCOUNT ( fReview[product_id] ), fReview[sinal_seguranca] = TRUE () )", "#,##0",
     "Produtos com review citando faísca, choque, superaquecimento ou fumaça. Triagem: requer leitura manual."),
    ("Riscos", "Falhas Relatadas",
     "CALCULATE ( COUNTROWS ( fReview ), NOT ISBLANK ( fReview[dias_ate_falha] ) )", "#,##0",
     "Trechos que relatam defeito informando o tempo de uso (ex.: stopped working after 2 months)."),
    ("Riscos", "% Falhas no 1º Mês",
     "DIVIDE ( CALCULATE ( [Falhas Relatadas], fReview[faixa_tempo_falha] IN { \"1. Até 1 semana\", \"2. Até 1 mês\" } ), "
     "[Falhas Relatadas] )", "0.0%",
     "Falhas relatadas em até 30 dias de uso (mesmas faixas do gráfico 'Quando o defeito aparece'). "
     "Filtrar dias_ate_falha aqui daria 100%: [Falhas Relatadas] já filtra essa coluna e sobrescreveria o filtro."),
]

# Recomendacoes (pagina 5): area, achado, evidencia, acao
RECOMENDACOES = [
    ("Diretoria", "Engajamento muito concentrado", "10% dos produtos concentram 62% das avaliações",
     "Proteger os campeões (estoque, preço e qualidade) e monitorar a dependência de poucos itens e marcas"),
    ("Pricing", "Desconto alto não compra satisfação", "Com desconto ≥ 80%, 42% dos produtos têm nota < 4; com até 20%, só 17%",
     "Limitar descontos acima de 60% a produtos com nota ≥ 4 e medir o efeito antes de ampliar"),
    ("Pricing", "Em eletrodomésticos, desconto alto acompanha nota baixa",
     "Correlação desconto × nota de -0,50 em liquidificadores e aquecedores de água e -0,46 em Smart TVs",
     "Política de desconto por categoria: em eletro, investir em qualidade e garantia em vez de desconto"),
    ("Pricing", "% de desconto não move engajamento", "Correlação ≈ 0 entre economia em R$ e avaliações; -0,13 para % de desconto",
     "Testar outras alavancas (frete, bundle, garantia estendida) no lugar de desconto linear"),
    ("Marketing", "Produtos bem avaliados e pouco vistos", "372 produtos 'Oportunidade' (nota ≥ 4,1) com só 3,1% das avaliações",
     "Campanhas de visibilidade e anúncios patrocinados para esses produtos"),
    ("Marketing", "Títulos curtos performam melhor", "Títulos mais curtos: nota 4,15 e cerca de 2× mais avaliações que os mais longos",
     "Padronizar títulos objetivos, sem excesso de palavras-chave"),
    ("Marketing", "Presente é ocasião de compra satisfatória", "Reviews de presente têm 3% de trechos negativos contra 11% na média",
     "Campanhas de datas comemorativas para smartphones e smartwatches"),
    ("Compras", "Marcas com qualidade baixa e recorrente", "Boult: 100% dos produtos com nota < 4; pTron: 87%",
     "Plano de qualidade com o fornecedor ou substituição; priorizar marcas consistentes (Logitech, SanDisk, TP-Link) e a marca própria (AmazonBasics: 4,29)"),
    ("Compras", "Espaços vazios no sortimento", "Air fryers, HDs externos e mouses gamer: nota ≥ 4,38 com apenas 3 a 8 produtos",
     "Ampliar o sortimento nessas categorias"),
    ("Qualidade e Jurídico", "Suspeita de falsificação", "36 produtos com menção a fake/not original; trechos 3× mais negativos (micro SD, cabos, controles)",
     "Auditar vendedores terceiros dessas categorias"),
    ("Qualidade e Jurídico", "Nota alta escondendo problemas", "21 produtos com nota ≥ 4,2 e 3 em cada 8 reviews negativas",
     "Monitorar o texto das reviews, não só a nota média"),
    ("Pós-venda", "Defeitos precoces", "Metade das falhas relatadas ocorre no 1º mês; cabos USB lideram",
     "Inspeção de lote nos fornecedores críticos e troca expressa no 1º mês"),
    ("Pós-venda", "Fones de ouvido: maior risco do portfólio", "Subcategoria com pior nota (3,92) e 52% dos produtos abaixo de 4",
     "Revisar o sortimento de fones e reforçar o suporte pós-venda"),
    ("Pós-venda", "Produtos caros geram dúvidas de instalação", "Instalação citada em 15% das reviews dos produtos caros contra 6% nos baratos",
     "Oferecer serviço de instalação ou conteúdo de onboarding nos itens de maior valor"),
]


def tmdl_colunas(cols) -> str:
    blocos = []
    for nome, tipo, fmt, oculta, sort_by in cols:
        linhas = [f"\tcolumn {nome}", f"\t\tdataType: {tipo}"]
        if fmt:
            linhas.append(f"\t\tformatString: {fmt}")
        if oculta:
            linhas.append("\t\tisHidden")
        linhas.append(f"\t\tsummarizeBy: none")
        linhas.append(f"\t\tsourceColumn: {nome}")
        if sort_by:
            linhas.append(f"\t\tsortByColumn: {sort_by}")
        blocos.append("\n".join(linhas))
    return "\n\n".join(blocos)


def tmdl_tabela_m(nome, cols, m, descricao) -> str:
    return (f"/// {descricao}\ntable {nome}\n\n{tmdl_colunas(cols)}\n\n"
            f"\tpartition {nome} = m\n\t\tmode: import\n\t\tsource =\n{indentar(m, 4)}\n")


def tmdl_medidas() -> str:
    blocos = []
    for pasta, nome, dax, fmt, desc in MEDIDAS:
        nome_q = f"'{nome}'"
        cab = f"\t/// {desc}\n" if desc else ""
        if "\n" in dax:
            corpo = f"\tmeasure {nome_q} =\n{indentar(dax, 3)}"
        else:
            corpo = f"\tmeasure {nome_q} = {dax}"
        blocos.append(f"{cab}{corpo}\n\t\tformatString: {fmt}\n\t\tdisplayFolder: {pasta}")
    return ("/// Tabela só de medidas (organizadas em pastas por tema).\ntable _Medidas\n\n"
            + "\n\n".join(blocos)
            + "\n\n\tcolumn Coluna\n\t\tdataType: string\n\t\tisHidden\n\t\tisNameInferred\n\t\tsourceColumn: [Coluna]\n\n"
            "\tpartition _Medidas = calculated\n\t\tmode: import\n\t\tsource = ROW ( \"Coluna\", \"\" )\n")


def tmdl_recomendacoes() -> str:
    def s(x):
        return '"' + x.replace('"', '""') + '"'
    linhas = ",\n".join(f"    {{ {i}, {s(a)}, {s(b)}, {s(c)}, {s(d)} }}" for i, (a, b, c, d) in enumerate(RECOMENDACOES, 1))
    dax = ('DATATABLE (\n    "Ordem", INTEGER,\n    "Área", STRING,\n    "Achado", STRING,\n    "Evidência", STRING,\n'
           f'    "Ação recomendada", STRING,\n    {{\n{linhas}\n    }}\n)')
    cols = []
    for nome, tipo in [("Ordem", "int64"), ("Área", "string"), ("Achado", "string"), ("Evidência", "string"),
                       ("Ação recomendada", "string")]:
        n = f"'{nome}'" if (" " in nome or not nome.isascii()) else nome
        cols.append(f"\tcolumn {n}\n\t\tdataType: {tipo}\n\t\tisNameInferred\n\t\tsummarizeBy: none\n\t\tsourceColumn: [{nome}]")
    return ("/// Recomendações por área (lente por área na página 5). Cada linha liga um achado ao número que o sustenta.\n"
            "table dRecomendacao\n\n" + "\n\n".join(cols)
            + f"\n\n\tpartition dRecomendacao = calculated\n\t\tmode: import\n\t\tsource =\n{indentar(dax, 4)}\n")


def gerar_modelo() -> None:
    d = MODELO / "definition"
    escrever(MODELO / ".platform", {
        "$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": NOME},
        "config": {"version": "2.0", "logicalId": uid("model")}})
    escrever(MODELO / "definition.pbism", {
        "$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {}})
    escrever(d / "database.tmdl", "database\n\tcompatibilityLevel: 1601\n")
    escrever(d / "model.tmdl",
             "model Model\n\tculture: pt-BR\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
             "\tdiscourageImplicitMeasures\n\tsourceQueryCulture: pt-BR\n\tdataAccessOptions\n"
             "\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n"
             "ref table dProduto\nref table fReview\nref table fReviewTema\nref table dRecomendacao\nref table _Medidas\n")
    escrever(d / "expressions.tmdl",
             '/// Pasta com amazon.csv, fReview.csv e fReviewTema.csv (terminar com \\)\n'
             'expression PastaDados = "C:\\TechChallenge4\\dados\\" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n\n'
             f'/// Cotação ₹ -> R$: PTAX USD/BRL (BCB, 13/11/2026: 5,6518) x INR/USD (BCE, 13/11/2026: 0,010611)\n'
             f'expression CotacaoINRBRL = {COTACAO_INR_BRL} meta [IsParameterQuery=true, Type="Number", IsParameterQueryRequired=true]\n')
    escrever(d / "tables" / "dProduto.tmdl", tmdl_tabela_m(
        "dProduto", COLS_PRODUTO, M_PRODUTO, "Produtos tratados (1 linha por product_id). Tratamento completo no Power Query, passos comentados."))
    escrever(d / "tables" / "fReview.tmdl", tmdl_tabela_m(
        "fReview", COLS_REVIEW, M_REVIEW, "Trechos de review com sentimento VADER e sinais de risco (gerado em Python)."))
    escrever(d / "tables" / "fReviewTema.tmdl", tmdl_tabela_m(
        "fReviewTema", COLS_TEMA, M_TEMA, "Ponte trecho x tema (um trecho pode citar vários temas)."))
    escrever(d / "tables" / "_Medidas.tmdl", tmdl_medidas())
    escrever(d / "tables" / "dRecomendacao.tmdl", tmdl_recomendacoes())
    escrever(d / "relationships.tmdl",
             f"relationship {uid('rel1')}\n\tfromColumn: fReview.product_id\n\ttoColumn: dProduto.product_id\n\n"
             f"relationship {uid('rel2')}\n\tcrossFilteringBehavior: bothDirections\n"
             f"\tfromColumn: fReviewTema.trecho_id\n\ttoColumn: fReview.trecho_id\n")


# =========================================================== RELATORIO (PBIR)
def lit(valor) -> dict:
    if isinstance(valor, bool):
        v = "true" if valor else "false"
    elif isinstance(valor, (int, float)):
        v = f"{valor}D"
    else:
        v = "'" + str(valor).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": v}}}


def campo(ref: str) -> dict:
    """'dProduto.categoria' (coluna) ou '[Nota Média]' (medida em _Medidas)."""
    if ref.startswith("["):
        nome = ref[1:-1]
        return {"Measure": {"Expression": {"SourceRef": {"Entity": "_Medidas"}}, "Property": nome}}, f"_Medidas.{nome}", nome
    ent, prop = ref.split(".", 1)
    return {"Column": {"Expression": {"SourceRef": {"Entity": ent}}, "Property": prop}}, ref, prop


def projecoes(refs) -> dict:
    out = []
    for r in refs:
        f, qref, nat = campo(r)
        out.append({"field": f, "queryRef": qref, "nativeQueryRef": nat})
    return {"projections": out}


COR_TITULO = "#232F3E"
COR_DESTAQUE = "#FF9900"


def container_objs(titulo: str | None) -> dict:
    objs = {}
    if titulo:
        objs["title"] = [{"properties": {"show": lit(True), "text": lit(titulo), "fontSize": lit(11)}}]
    return objs


class Pagina:
    def __init__(self, nome, titulo, subtitulo):
        self.nome, self.titulo, self.visuais = nome, titulo, []
        self.texto(f"{titulo}", 20, 8, 900, 40, tamanho=20, negrito=True, cor=COR_TITULO)
        self.texto(subtitulo, 20, 44, 1240, 28, tamanho=11, cor="#555555")

    def _add(self, nome, x, y, w, h, visual, filtro=None):
        v = {"$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.0.0/schema.json",
             "name": nome, "position": {"x": x, "y": y, "z": len(self.visuais) * 1000,
                                        "height": h, "width": w, "tabOrder": len(self.visuais) * 1000},
             "visual": visual}
        if filtro:
            v["filterConfig"] = filtro
        self.visuais.append(v)

    def texto(self, conteudo, x, y, w, h, tamanho=11, negrito=False, cor="#252423"):
        paragrafos = []
        for linha in conteudo.split("\n"):
            estilo = {"fontSize": f"{tamanho}pt", "color": cor}
            if negrito:
                estilo["fontWeight"] = "bold"
            paragrafos.append({"textRuns": [{"value": linha, "textStyle": estilo}]})
        self._add(f"txt{len(self.visuais):02d}", x, y, w, h, {
            "visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paragrafos}}]},
            "drillFilterOtherVisuals": True})

    def visual(self, tipo, papeis: dict, x, y, w, h, titulo=None, ordenar=None, objetos=None):
        q = {"queryState": {papel: projecoes(refs) for papel, refs in papeis.items()}}
        if ordenar:
            ref, direcao = ordenar
            q["sortDefinition"] = {"sort": [{"field": campo(ref)[0], "direction": direcao}], "isDefaultSort": False}
        vis = {"visualType": tipo, "query": q, "drillFilterOtherVisuals": True}
        if objetos:
            vis["objects"] = objetos
        co = container_objs(titulo)
        if co:
            vis["visualContainerObjects"] = co
        self._add(f"v{len(self.visuais):02d}{tipo[:10]}", x, y, w, h, vis)

    def cartao(self, medida, x, y, w=195, h=95, titulo=None):
        self.visual("card", {"Values": [medida]}, x, y, w, h, titulo=titulo or medida[1:-1],
                    objetos={"categoryLabels": [{"properties": {"show": lit(False)}}]})

    def segmentacao(self, coluna, x, y, w=240, h=60, titulo=None):
        self.visual("slicer", {"Values": [coluna]}, x, y, w, h, titulo=titulo,
                    objetos={"data": [{"properties": {"mode": lit("Dropdown")}}]})

    def gravar(self, raiz: Path):
        escrever(raiz / self.nome / "page.json", {
            "$schema": f"{SCHEMA}/item/report/definition/page/1.4.0/schema.json",
            "name": self.nome, "displayName": self.titulo, "displayOption": "FitToPage",
            "height": 720, "width": 1280})
        for v in self.visuais:
            escrever(raiz / self.nome / "visuals" / v["name"] / "visual.json", v)


def paginas() -> list[Pagina]:
    P = []
    # ---------------------------------------------------------------- 1. Visão executiva
    p = Pagina("p1Executiva", "1. Visão Executiva",
               "Preço → Desconto → Engajamento → Satisfação  |  1.351 produtos Amazon, preços convertidos para R$")
    for i, (m, t) in enumerate([("[Produtos]", None), ("[Avaliações]", "Avaliações (sem variantes)"),
                                ("[Nota Média]", None), ("[% Produtos Abaixo de 4]", None),
                                ("[Desconto Médio]", None), ("[Preço Mediano (R$)]", None)]):
        p.cartao(m, 20 + i * 207, 80, titulo=t)
    p.visual("clusteredBarChart", {"Category": ["dProduto.categoria"], "Y": ["[Avaliações]"]},
             20, 190, 410, 260, titulo="Avaliações por categoria", ordenar=("[Avaliações]", "Descending"))
    p.visual("clusteredColumnChart", {"Category": ["dProduto.quadrante"], "Y": ["[% das Avaliações]"]},
             440, 190, 400, 260, titulo="Quadrantes: participação nas avaliações")
    p.visual("clusteredColumnChart", {"Category": ["dProduto.faixa_desconto"], "Y": ["[% Produtos Abaixo de 4]"]},
             850, 190, 410, 260, titulo="% de produtos com nota < 4 por faixa de desconto",
             ordenar=("dProduto.faixa_desconto", "Ascending"))
    p.texto("Mensagens-chave\n"
            "• Engajamento concentrado: 10% dos produtos = 62% das avaliações.\n"
            "• Desconto alto não compra satisfação: com desconto ≥ 80%, 42% dos produtos têm nota < 4 (contra 17% com até 20%).\n"
            "• 372 produtos bem avaliados recebem só 3,1% das avaliações: oportunidade de visibilidade.\n"
            "• Fones de ouvido: maior risco (pior nota e alto volume).",
            20, 465, 1000, 140, tamanho=11)
    p.segmentacao("dProduto.categoria", 1030, 470, titulo="Categoria")
    P.append(p)

    # ---------------------------------------------------------------- 2. Produtos e categorias
    p = Pagina("p2Produtos", "2. Produtos e Categorias",
               "Engajamento (avaliações) × Satisfação (nota): onde estão as estrelas, os riscos e as oportunidades")
    p.segmentacao("dProduto.categoria", 20, 75, titulo="Categoria")
    p.segmentacao("dProduto.subcategoria", 270, 75, titulo="Subcategoria")
    p.segmentacao("dProduto.quadrante", 520, 75, titulo="Quadrante")
    p.segmentacao("dProduto.marca", 770, 75, titulo="Marca")
    p.visual("scatterChart", {"Category": ["dProduto.product_name"], "Series": ["dProduto.quadrante"],
                              "X": ["[Avaliações]"], "Y": ["[Nota Média]"]},
             20, 145, 620, 300, titulo="Cada ponto é um produto: avaliações × nota")
    p.visual("tableEx", {"Values": ["dProduto.subcategoria", "[Produtos]", "[Nota Média]", "[% Produtos Abaixo de 4]",
                                    "[Avaliações]", "[Desconto Médio]"]},
             650, 145, 610, 300, titulo="Subcategorias (ordenar por nota)", ordenar=("[Nota Média]", "Ascending"))
    p.visual("tableEx", {"Values": ["dProduto.product_name", "dProduto.quadrante", "[Nota Média]", "[Nota Ponderada]",
                                    "[Avaliações]", "[Desconto Médio]"]},
             20, 455, 820, 255, titulo="Produtos (filtre por quadrante: Risco e Oportunidade)",
             ordenar=("[Avaliações]", "Descending"))
    p.visual("tableEx", {"Values": ["dProduto.marca", "[Produtos]", "[Nota Média]", "[% Produtos Abaixo de 4]", "[Avaliações]"]},
             850, 455, 410, 255, titulo="Marcas (lente Compras)", ordenar=("[Produtos]", "Descending"))
    P.append(p)

    # ---------------------------------------------------------------- 3. Preços e estratégia
    p = Pagina("p3Precos", "3. Preços e Estratégia Comercial",
               "Desconto alto não traz mais engajamento nem mais satisfação, e em eletrodomésticos indica produto pior")
    p.segmentacao("dProduto.categoria", 20, 75, titulo="Categoria")
    p.segmentacao("dProduto.subcategoria", 270, 75, titulo="Subcategoria")
    p.cartao("[Desconto Médio]", 530, 72, w=170, h=70)
    p.cartao("[Preço Médio Original (R$)]", 710, 72, w=180, h=70)
    p.cartao("[Preço Médio com Desconto (R$)]", 900, 72, w=180, h=70)
    p.cartao("[Economia Média (R$)]", 1090, 72, w=170, h=70)
    p.visual("lineClusteredColumnComboChart", {"Category": ["dProduto.faixa_desconto"], "Y": ["[% Produtos Abaixo de 4]"],
                                               "Y2": ["[Nota Média]"]},
             20, 155, 610, 270, titulo="Faixa de desconto: % abaixo de 4 (colunas) e nota média (linha)",
             ordenar=("dProduto.faixa_desconto", "Ascending"))
    p.visual("clusteredColumnChart", {"Category": ["dProduto.faixa_desconto"], "Y": ["[Avaliações por Produto (mediana)]"]},
             640, 155, 620, 270, titulo="Engajamento por faixa de desconto (mediana de avaliações por produto)",
             ordenar=("dProduto.faixa_desconto", "Ascending"))
    p.visual("scatterChart", {"Category": ["dProduto.categoria_folha"], "X": ["[Desconto Médio]"], "Y": ["[Nota Média]"],
                              "Size": ["[Produtos]"]},
             20, 435, 610, 275, titulo="Categorias folha: desconto médio × nota (tamanho = nº de produtos)")
    p.visual("tableEx", {"Values": ["dProduto.faixa_preco", "[Produtos]", "[Nota Média]", "[Avaliações por Produto (mediana)]",
                                    "[Desconto Médio]"]},
             640, 435, 620, 135, titulo="Faixas de preço (quartis)", ordenar=("dProduto.faixa_preco", "Ascending"))
    p.texto("• Correlação % desconto × avaliações: -0,13; economia em R$ × avaliações: ≈ 0.\n"
            "• Na mesma categoria: desconto × nota = -0,50 (liquidificadores, aquecedores de água), -0,46 (Smart TV).\n"
            "• Hipótese testada e não confirmada: preço original inflado para simular desconto (19 casos, sem efeito).",
            640, 578, 620, 132, tamanho=10)
    P.append(p)

    # ---------------------------------------------------------------- 4. Customer insights
    p = Pagina("p4Clientes", "4. Customer Insights",
               "O que os clientes valorizam, do que reclamam e quais riscos aparecem no texto das reviews")
    for i, (m, t) in enumerate([("[Trechos de Review]", None), ("[% Trechos Positivos]", None),
                                ("[% Trechos Negativos]", None), ("[% Falhas no 1º Mês]", None),
                                ("[Produtos com Suspeita de Falsificação]", "Suspeita de falsificação (produtos)"),
                                ("[Produtos com Alerta de Segurança]", "Alerta de segurança (produtos)")]):
        p.cartao(m, 20 + i * 207, 75, h=80, titulo=t)
    p.visual("barChart", {"Category": ["fReviewTema.tema"], "Y": ["[Menções]"], "Series": ["fReview.sentimento"]},
             20, 165, 620, 300, titulo="Temas mais citados, por sentimento", ordenar=("[Menções]", "Descending"))
    p.visual("clusteredBarChart", {"Category": ["fReviewTema.tema"], "Y": ["[% Negativo do Tema]"]},
             650, 165, 300, 300, titulo="% negativo por tema", ordenar=("[% Negativo do Tema]", "Descending"))
    p.visual("clusteredColumnChart", {"Category": ["fReview.faixa_tempo_falha"], "Y": ["[Falhas Relatadas]"]},
             960, 165, 300, 300, titulo="Quando o defeito aparece", ordenar=("fReview.faixa_tempo_falha", "Ascending"))
    p.segmentacao("fReview.sentimento", 20, 475, w=200, titulo="Sentimento")
    p.segmentacao("fReviewTema.tema", 20, 545, w=200, titulo="Tema")
    p.segmentacao("dProduto.categoria", 20, 615, w=200, titulo="Categoria")
    p.visual("tableEx", {"Values": ["fReview.texto", "dProduto.product_name", "fReview.sentimento_score"]},
             230, 475, 1030, 235, titulo="O que os clientes dizem (filtre por tema e sentimento)",
             ordenar=("fReview.sentimento_score", "Ascending"))
    P.append(p)

    # ---------------------------------------------------------------- 5. Recomendações
    p = Pagina("p5Recomendacoes", "5. Recomendações",
               "Cada recomendação ligada ao número que a sustenta. Use a lente por área para ver as ações de cada time.")
    p.segmentacao("dRecomendacao.Área", 20, 75, w=300, titulo="Lente por área")
    p.visual("tableEx", {"Values": ["dRecomendacao.Área", "dRecomendacao.Achado", "dRecomendacao.Evidência",
                                    "dRecomendacao.Ação recomendada"]},
             20, 145, 1240, 400, titulo="Achados e ações", ordenar=("dRecomendacao.Ordem", "Ascending"))
    p.texto("O que a liderança deve levar desta análise\n"
            "1. Desconto não é alavanca de satisfação nem de engajamento: rever a política por categoria.\n"
            "2. Visibilidade está desalinhada com qualidade: há 372 produtos bem avaliados e pouco vistos.\n"
            "3. O texto das reviews revela riscos que a nota esconde: defeitos no 1º mês, falsificação e marcas recorrentes.",
            20, 560, 1240, 150, tamanho=12, cor=COR_TITULO)
    P.append(p)
    return P


TEMA = {
    "name": "TechChallenge4",
    "dataColors": ["#232F3E", "#FF9900", "#146EB4", "#C0392B", "#2E8B57", "#8E8E8E", "#6C4AB6", "#D4A017"],
    "background": "#FFFFFF", "foreground": "#252423", "tableAccent": "#FF9900",
    "good": "#2E8B57", "neutral": "#D4A017", "bad": "#C0392B",
}


def gerar_relatorio() -> None:
    escrever(RELAT / ".platform", {
        "$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": NOME},
        "config": {"version": "2.0", "logicalId": uid("report")}})
    escrever(RELAT / "definition.pbir", {
        "$schema": f"{SCHEMA}/item/report/definitionProperties/1.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NOME}.SemanticModel"}}})
    escrever(RELAT / "StaticResources" / "RegisteredResources" / "TechChallenge4.json", TEMA)
    d = RELAT / "definition"
    escrever(d / "version.json", {"$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json",
                                  "version": "2.0.0"})
    escrever(d / "report.json", {
        "$schema": f"{SCHEMA}/item/report/definition/report/1.3.0/schema.json",
        "layoutOptimization": "None",
        "themeCollection": {
            "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": "5.61", "type": "SharedResources"},
            "customTheme": {"name": "TechChallenge4.json", "reportVersionAtImport": "5.61", "type": "RegisteredResources"}},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "TechChallenge4.json", "path": "TechChallenge4.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True}})
    pags = paginas()
    import shutil
    if (d / "pages").exists():
        shutil.rmtree(d / "pages")
    for pg in pags:
        pg.gravar(d / "pages")
    escrever(d / "pages" / "pages.json", {
        "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [pg.nome for pg in pags], "activePageName": pags[0].nome})


def main() -> None:
    import shutil
    if (MODELO / "definition").exists():
        shutil.rmtree(MODELO / "definition")
    gerar_modelo()
    gerar_relatorio()
    escrever(PBI / f"{NOME}.pbip", {
        "$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
        "artifacts": [{"report": {"path": f"{NOME}.Report"}}], "settings": {"enableAutoRecovery": True}})
    print(f"PBIP gerado em {PBI}")


if __name__ == "__main__":
    main()
