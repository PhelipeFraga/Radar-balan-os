"""Números de cada instituição no IF.data do Banco Central (fase 3).

Usa o conglomerado prudencial (o grupo inteiro, como o BC supervisiona) quando
existe; senão, a instituição individual. Os números saem 2 a 3 meses depois do
fim do trimestre.

Indicadores:
- Lucro líquido do trimestre: o IF.data soma o lucro no semestre (jan-jun, jul-dez),
  então junho e dezembro descontam o trimestre anterior.
- Carteira de crédito (classificada).
- Índice de Basileia.
- Estágio 3 (ativos problemáticos) e Over 90 (inadimplência acima de 90 dias),
  em % da carteira: só existem a partir de 2025, com a Resolução CMN 4.966.
"""

import json
import time
import urllib.parse
import urllib.request
from datetime import date

API = "https://olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/odata"
TRIMESTRES = 8


def _get(caminho, params):
    url = f"{API}/{caminho}?" + urllib.parse.urlencode({**params, "$format": "json"}, safe="@'$=,")
    for i in range(3):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))["value"]
        except Exception as erro:
            if i == 2:
                raise
            print(f"  nova tentativa no Banco Central ({erro})")
            time.sleep(10 * (i + 1))


def _trimestres(hoje, n):
    """Do mais recente possível para trás: 202606, 202603, ..."""
    ano, mes = hoje.year, (hoje.month - 1) // 3 * 3
    if mes == 0:
        ano, mes = ano - 1, 12
    lista = []
    while len(lista) < n:
        lista.append(ano * 100 + mes)
        mes -= 3
        if mes == 0:
            ano, mes = ano - 1, 12
    return lista


def _codigos(raizes, anomes):
    """Raiz do CNPJ (8 dígitos) -> código do conglomerado prudencial no IF.data."""
    cad = _get("IfDataCadastro(AnoMes=@AnoMes)", {"@AnoMes": anomes})
    codigos = {}
    for raiz in raizes:
        lider = [c for c in cad if str(c.get("CnpjInstituicaoLider") or "") == raiz]
        prud = [c for c in lider if "PRUDENCIAL" in (c.get("NomeInstituicao") or "").upper()]
        if prud:
            codigos[raiz] = prud[0]["CodInst"]
        elif any(c["CodInst"] == raiz for c in cad):
            codigos[raiz] = raiz
    return codigos


def _valores(anomes, codigos):
    """{codigo: {coluna: saldo}} para os relatórios Resumo (1) e Carteira por instrumentos (16)."""
    alvo = set(codigos.values())
    saida = {}
    for rel in ("1", "16"):
        try:
            linhas = _get("IfDataValores(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,Relatorio=@Relatorio)",
                          {"@AnoMes": anomes, "@TipoInstituicao": 1, "@Relatorio": f"'{rel}'"})
        except Exception as erro:
            print(f"  IF.data {anomes} relatório {rel} indisponível: {erro}")
            continue
        if not linhas and rel == "16":
            linhas = _get("IfDataValores(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,Relatorio=@Relatorio)",
                          {"@AnoMes": anomes, "@TipoInstituicao": 3, "@Relatorio": f"'{rel}'"})
        for l in linhas:
            if l["CodInst"] in alvo and l.get("Grupo") is None:
                saida.setdefault(l["CodInst"], {})[l["NomeColuna"].strip()] = l["Saldo"]
    return saida


def _pega(v, inicio):
    for nome, saldo in v.items():
        if inicio in nome:
            return saldo
    return None


def coletar(raizes, hoje, cache):
    """{raiz: [ {periodo, lucro, carteira, basileia, estagio3, over90}, ... ]} do mais antigo ao mais novo."""
    # Um trimestre a mais, para calcular o lucro do trimestre em junho/dezembro.
    candidatos = _trimestres(hoje, TRIMESTRES + 3)
    codigos = None
    brutos = {}
    for anomes in candidatos:
        chave = str(anomes)
        recente = anomes >= candidatos[2]  # os 2-3 mais novos podem ser revisados: busca de novo
        if chave in cache and not recente:
            brutos[anomes] = cache[chave]
            continue
        if codigos is None:
            codigos = _codigos(raizes, max(candidatos[3], 202503))
        dados = _valores(anomes, codigos)
        if not dados:
            continue  # trimestre ainda não publicado
        por_raiz = {raiz: dados.get(cod, {}) for raiz, cod in codigos.items()}
        brutos[anomes] = por_raiz
        cache[chave] = por_raiz
        print(f"  IF.data {anomes}: {sum(1 for v in por_raiz.values() if v)} instituições")

    publicados = sorted(brutos)[-(TRIMESTRES + 1):]
    saida = {}
    for raiz in raizes:
        serie = []
        for i, anomes in enumerate(publicados):
            v = brutos[anomes].get(raiz) or {}
            if not v:
                continue
            ano, mes = divmod(anomes, 100)
            lucro = _pega(v, "Lucro L")
            if lucro is not None and mes in (6, 12):
                anterior = brutos.get(publicados[i - 1], {}).get(raiz, {}) if i > 0 else {}
                lucro_ant = _pega(anterior, "Lucro L") if publicados[i - 1] == anomes - 3 else None
                lucro = lucro - lucro_ant if lucro_ant is not None else None
            total = _pega(v, "Total Geral")
            prob, inad = _pega(v, "Ativos problem"), _pega(v, "Inadimpl")
            serie.append({
                "periodo": f"{mes // 3}T{str(ano)[2:]}",
                "lucro": lucro,
                "carteira": _pega(v, "Carteira de Cr"),
                "basileia": _pega(v, "de Basileia"),
                "estagio3": prob / total if prob is not None and total else None,
                "over90": inad / total if inad is not None and total else None,
            })
        saida[raiz] = serie[-TRIMESTRES:]
    return saida
