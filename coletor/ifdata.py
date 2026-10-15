"""Números de cada instituição no IF.data do Banco Central (fase 3).

Visão por ano: os 4 anos fechados anteriores (lucro do ano inteiro; os demais
indicadores na posição de 31/12) e o ano atual acumulado até o último trimestre
publicado, sempre comparado com o mesmo período do ano anterior.

Detalhes do IF.data:
- O lucro vem somado no semestre (jan-jun, jul-dez). Ano = junho + dezembro;
  acumulado até setembro = junho + setembro.
- Estágio 3 ("ativos problemáticos") e Over 90 ("inadimplência", atraso acima de
  90 dias) só existem desde 2025 (Resolução CMN 4.966), no conglomerado prudencial.
- Antes de 2025 a carteira E-H (conglomerado financeiro) ocupa o lugar do Estágio 3,
  como a medida de crédito problemático da regra antiga (Resolução 2.682). Escolha do Phelipe.
- Vencidos: "vencido a partir de 15 dias" (relatórios 11 e 13, pessoa física e
  jurídica) sobre a carteira total. Existe em todos os anos, então substitui o Over 90
  e dá uma base contínua (escolha do Phelipe). Mede parcelas atrasadas, não o saldo do
  contrato; até 2024 vem do conglomerado financeiro, depois do prudencial.
- Saem 2 a 3 meses depois do fim do trimestre.
"""

import json
import time
import urllib.parse
import urllib.request

API = "https://olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/odata"
ANOS = 4
ROTULO_ACUMULADO = {3: "1º tri", 6: "1º semestre", 9: "jan–set", 12: "ano"}


def _get(caminho, params):
    url = f"{API}/{caminho}?" + urllib.parse.urlencode({**params, "$format": "json"}, safe="@'$=,", quote_via=urllib.parse.quote)
    for i in range(3):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))["value"]
        except Exception as erro:
            if i == 2:
                raise
            print(f"  nova tentativa no Banco Central ({erro})")
            time.sleep(10 * (i + 1))


def _relatorio(anomes, tipo, rel, codigos):
    params = {"@AnoMes": anomes, "@TipoInstituicao": tipo, "@Relatorio": f"'{rel}'"}
    if len(codigos) <= 40:  # poucos: filtra no Banco Central; muitos (pares): baixa tudo e filtra aqui
        params["$filter"] = " or ".join(f"CodInst eq '{c}'" for c in sorted(codigos))
    linhas = _get("IfDataValores(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,Relatorio=@Relatorio)", params)
    return [l for l in linhas if l["CodInst"] in codigos] if len(codigos) > 40 else linhas


def _codigos(raizes, anomes):
    """Raiz do CNPJ -> (código prudencial, código do conglomerado financeiro)."""
    cad = _get("IfDataCadastro(AnoMes=@AnoMes)", {"@AnoMes": anomes})
    codigos = {}
    for raiz in raizes:
        lider = [c for c in cad if str(c.get("CnpjInstituicaoLider") or "") == raiz]
        propria = next((c for c in lider if c["CodInst"] == raiz), None)
        prud = next((c["CodInst"] for c in lider if "PRUDENCIAL" in (c.get("NomeInstituicao") or "").upper()), None)
        prud = prud or (propria or {}).get("CodConglomeradoPrudencial") or (raiz if propria else None)
        fin = (propria or {}).get("CodConglomeradoFinanceiro") or (raiz if propria else None)
        if prud or fin:
            codigos[raiz] = (prud, fin)
    return codigos


def _pega(v, trecho):
    for nome, saldo in v.items():
        if trecho in nome:
            return saldo
    return None


def _mes(codigos, anomes):
    """{raiz: {...indicadores daquele mês}} ou {} se o mês ainda não saiu."""
    prud = {c[0] for c in codigos.values() if c[0]}
    fin = {c[1] for c in codigos.values() if c[1]}
    resumo = _relatorio(anomes, 1, "1", prud)
    if not resumo:
        return {}
    por_cod = {}
    for l in resumo:
        por_cod.setdefault(l["CodInst"], {})[l["NomeColuna"].strip()] = l["Saldo"]
    novo = {}
    if anomes >= 202503:
        for l in _relatorio(anomes, 1, "16", prud):
            if l.get("Grupo") is None:
                novo.setdefault(l["CodInst"], {})[l["NomeColuna"].strip()] = l["Saldo"]
    vencidos = {}
    tipo, codigos_venc = (2, fin) if anomes < 202503 else (1, prud)
    for rel in ("11", "13"):  # pessoa física e pessoa jurídica
        for l in _relatorio(anomes, tipo, rel, codigos_venc):
            tot = vencidos.setdefault(l["CodInst"], {"vencido": 0.0, "total": 0.0})
            if l.get("Grupo") and "Vencido" in l["NomeColuna"]:
                tot["vencido"] += l["Saldo"] or 0
            if l.get("Grupo") is None and "Total da Carteira" in l["NomeColuna"]:
                tot["total"] += l["Saldo"] or 0
    niveis = {}
    if anomes < 202503:
        for l in _relatorio(anomes, 2, "8", fin):  # carteira por nível de risco (AA a H)
            nivel = l["NomeColuna"].strip()
            if nivel in ("AA", "A", "B", "C", "D", "E", "F", "G", "H"):
                tot = niveis.setdefault(l["CodInst"], {"eh": 0.0, "total": 0.0})
                tot["total"] += l["Saldo"] or 0
                if nivel in ("E", "F", "G", "H"):
                    tot["eh"] += l["Saldo"] or 0
    saida = {}
    for raiz, (cp, cf) in codigos.items():
        v = por_cod.get(cp, {})
        if not v:
            continue
        item = {"lucro_sem": _pega(v, "Lucro L"), "carteira": _pega(v, "Carteira de Cr"), "basileia": _pega(v, "de Basileia"),
                "estagio3": None, "vencidos": None, "estagio_tipo": None}
        n = novo.get(cp)
        if n and _pega(n, "Total Geral"):
            total = _pega(n, "Total Geral")
            prob = _pega(n, "Ativos problem")
            item["estagio3"] = prob / total if prob is not None else None
            item["estagio_tipo"] = "E3"
        venc = vencidos.get(cf if anomes < 202503 else cp)
        if venc and venc["total"]:
            item["vencidos"] = venc["vencido"] / venc["total"]
        eh = niveis.get(cf)
        if eh and eh["total"]:
            item["estagio3"] = eh["eh"] / eh["total"]
            item["estagio_tipo"] = "EH"
        saida[raiz] = item
    return saida


def _ultimo_publicado(hoje, codigos):
    teste = {next(c[0] for c in codigos.values() if c[0])}
    ano, mes = hoje.year, (hoje.month - 1) // 3 * 3
    for _ in range(4):
        if mes == 0:
            ano, mes = ano - 1, 12
        if _relatorio(ano * 100 + mes, 1, "1", teste):
            return ano * 100 + mes
        mes -= 3
    raise RuntimeError("nenhum trimestre recente publicado")


def coletar(raizes, hoje, cache):
    """{raiz: {"anos": [...4 anos], "atual": {...}, "anterior": {...}, "ate": AAAAMM}}."""
    codigos = _codigos(raizes, 202512)
    ultimo = _ultimo_publicado(hoje, codigos)
    ano_atual, mes_atual = divmod(ultimo, 100)
    anos = list(range(ano_atual - ANOS, ano_atual))
    meses = set()
    for a in anos:
        meses |= {a * 100 + 6, a * 100 + 12}
    for a in (ano_atual - 1, ano_atual):
        meses.add(a * 100 + mes_atual)
        if mes_atual > 6:
            meses.add(a * 100 + 6)

    dados = {}
    for anomes in sorted(meses):
        chave = str(anomes)
        if chave in cache and anomes < ultimo - 100:  # dados com mais de um ano não mudam
            dados[anomes] = cache[chave]
            continue
        dados[anomes] = _mes(codigos, anomes)
        cache[chave] = dados[anomes]
        print(f"  IF.data {anomes}: {len(dados[anomes])} instituições")

    def periodo(raiz, ano, mes, rotulo):
        fim = (dados.get(ano * 100 + mes) or {}).get(raiz)
        if not fim:
            return None
        lucro = fim["lucro_sem"]
        if mes > 6:
            meio = (dados.get(ano * 100 + 6) or {}).get(raiz) or {}
            lucro = lucro + meio["lucro_sem"] if lucro is not None and meio.get("lucro_sem") is not None else None
        return {"rotulo": rotulo, "lucro": lucro, "carteira": fim["carteira"], "basileia": fim["basileia"],
                "estagio3": fim["estagio3"], "vencidos": fim["vencidos"], "estagio_tipo": fim["estagio_tipo"]}

    acumulado = ROTULO_ACUMULADO[mes_atual]
    saida = {}
    for raiz in raizes:
        if raiz not in codigos:
            continue
        lista = [p for p in (periodo(raiz, a, 12, str(a)) for a in anos) if p]
        atual = periodo(raiz, ano_atual, mes_atual, f"{acumulado} {ano_atual}")
        anterior = periodo(raiz, ano_atual - 1, mes_atual, f"{acumulado} {ano_atual - 1}")
        if atual or lista:
            saida[raiz] = {"anos": lista, "atual": atual, "anterior": anterior, "ate": ultimo, "cod": codigos[raiz][0]}
    return saida


SEGMENTOS = ("S1", "S2", "S3", "S4")


def pares(ultimo):
    """Todas as instituições do IF.data por segmento do BC (S1 a S4), no último período publicado.

    {"ate": AAAAMM, "segmentos": {"S1": [{"cod", "nome", "lucro", "carteira", "basileia", "estagio3", "vencidos"}]},
     "segmento_de": {cod: "S1"}}
    """
    cad = {c["CodInst"]: c for c in _get("IfDataCadastro(AnoMes=@AnoMes)", {"@AnoMes": ultimo})}
    resumo = _get("IfDataValores(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,Relatorio=@Relatorio)",
                  {"@AnoMes": ultimo, "@TipoInstituicao": 1, "@Relatorio": "'1'"})
    cods = {l["CodInst"] for l in resumo}

    # Segmento por conglomerado: o próprio registro, o líder ou qualquer instituição do grupo que o informe.
    seg_grupo = {}
    for c in cad.values():
        if c.get("Sr"):
            for chave in (c.get("CodConglomeradoPrudencial"), c.get("CodConglomeradoFinanceiro")):
                if chave and seg_grupo.get(chave, "S9") > c["Sr"]:
                    seg_grupo[chave] = c["Sr"]

    def segmento(cod):
        c = cad.get(cod) or {}
        lider = str(c.get("CnpjInstituicaoLider") or "")
        return c.get("Sr") or (cad.get(lider) or {}).get("Sr") or seg_grupo.get(cod)

    todos = {cod: (cod, None) for cod in cods if segmento(cod) in SEGMENTOS}
    fim = _mes(todos, ultimo)
    meio = _mes(todos, ultimo // 100 * 100 + 6) if ultimo % 100 > 6 else {}
    segmentos, segmento_de = {}, {}
    for cod, v in fim.items():
        lucro = v["lucro_sem"]
        if meio:
            m = meio.get(cod) or {}
            lucro = lucro + m["lucro_sem"] if lucro is not None and m.get("lucro_sem") is not None else None
        nome = (cad.get(cod) or {}).get("NomeInstituicao") or cod
        nome = nome.replace(" - PRUDENCIAL", "").replace("- PRUDENCIAL", "").strip()
        seg = segmento(cod)
        segmento_de[cod] = seg
        segmentos.setdefault(seg, []).append({"cod": cod, "nome": nome, "lucro": lucro, "carteira": v["carteira"],
                                              "basileia": v["basileia"], "estagio3": v["estagio3"], "vencidos": v["vencidos"]})
    print(f"  pares: {', '.join(f'{s} {len(segmentos.get(s, []))}' for s in SEGMENTOS)}")
    return {"ate": ultimo, "segmentos": segmentos, "segmento_de": segmento_de}
