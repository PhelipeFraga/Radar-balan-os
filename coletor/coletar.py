"""Coletor do Radar de Balanços.

Roda no GitHub Actions (ou no PC) e gera docs/dados.json e docs/agenda.ics
a partir de dados públicos da CVM e de notícias. Não usa nenhuma IA.

Fontes:
- Cadastro de companhias abertas da CVM: quais bancos existem.
- IPE (documentos eventuais) da CVM: o "Calendário de Eventos Corporativos"
  de cada banco, um PDF em modelo padrão com as datas de ITR e DFP.
- ITR e DFP da CVM: confirma que o balanço foi entregue e dá o link do PDF.
- Google Notícias: avisa que o resultado saiu antes de a CVM atualizar a base
  (a base aberta da CVM só é atualizada uma vez por semana).
"""

import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pypdf import PdfReader

import sec

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "docs"
CACHE = RAIZ / "coletor" / "cache"
CVM = "https://dados.cvm.gov.br/dados/CIA_ABERTA"
BRT = timezone(timedelta(hours=-3))
HOJE = datetime.now(BRT).date()
AGENTE = {"User-Agent": "Mozilla/5.0 (RadarDeBalancos; coletor pessoal de dados publicos)"}

SETORES = {"Bancos", "Emp. Adm. Part. - Bancos", "Intermediação Financeira"}

# Nome curto para exibir e para buscar notícias. Quem não está aqui usa o nome comercial.
NOMES = {
    1023: "Banco do Brasil", 906: "Bradesco", 19348: "Itaú Unibanco",
    20532: "Santander Brasil", 22616: "BTG Pactual", 20958: "ABC Brasil",
    24600: "Banco BMG", 922: "Banco da Amazônia", 20796: "Daycoval",
    1120: "Banese", 1171: "Banpará", 1210: "Banrisul", 1228: "Banco do Nordeste",
    1325: "Mercantil do Brasil", 1309: "Mercantil Investimentos", 20567: "Banco Pine",
    21466: "Banco RCI Brasil", 1155: "Banestes", 14206: "BRB", 25860: "BR Partners",
    20729: "Paraná Banco", 7617: "Itaúsa", 21733: "Cielo", 27634: "B100",
}
# Site de relações com investidores (onde o release aparece primeiro).
RI = {
    1023: "https://ri.bb.com.br", 906: "https://www.bradescori.com.br", 19348: "https://www.itau.com.br/relacoes-com-investidores",
    20532: "https://www.santander.com.br/ri", 22616: "https://ri.btgpactual.com", 20958: "https://ri.abcbrasil.com.br",
    24600: "https://www.bancobmg.com.br/ri", 922: "https://ri.bancoamazonia.com.br", 20796: "https://www.daycoval.com.br/ri",
    1120: "https://ri.banese.com.br", 1171: "https://ri.banpara.b.br", 1210: "https://www.banrisul.com.br/ri",
    1228: "https://ri.bnb.gov.br", 1325: "https://ri.bancomercantil.com.br", 1309: "https://ri.bancomercantil.com.br",
    20567: "https://ri.pine.com", 21466: "https://www.bancorci.com.br/relacao-com-investidores", 1155: "https://ri.banestes.com.br",
    14206: "https://ri.brb.com.br", 25860: "https://ri.brpartners.com.br", 20729: "https://ri.paranabanco.com.br",
    21733: "https://ri.cielo.com.br", 27634: "https://ri.b100sa.com.br",
}

# Registradas nesses setores, mas sem operação de crédito relevante.
EXCLUIR = {15717, 6041}  # Cadip, Investimentos Bemge


def baixar(url, tentativas=3):
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=AGENTE), timeout=90) as r:
                return r.read()
        except Exception as erro:  # rede instável: tenta de novo
            if i == tentativas - 1:
                raise
            print(f"  nova tentativa ({erro})")
            time.sleep(5 * (i + 1))


def csv_do_zip(url, nome):
    with zipfile.ZipFile(io.BytesIO(baixar(url))) as z:
        texto = z.read(nome).decode("latin-1")
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


def csv_simples(url):
    return list(csv.DictReader(io.StringIO(baixar(url).decode("latin-1")), delimiter=";"))


def sigla(nome):
    partes = [p for p in re.split(r"\s+", nome) if p[0:1].isalpha() and p.lower() not in {"do", "da", "de", "dos"}]
    if len(partes) >= 2:
        return (partes[0][0] + partes[1][0]).upper()
    return nome[:2].upper()


# ---------- 1. Quais instituições ----------

def carregar_instituicoes():
    linhas = csv_simples(f"{CVM}/CAD/DADOS/cad_cia_aberta.csv")
    inst = {}
    for l in linhas:
        if l["SIT"] != "ATIVO" or l["SETOR_ATIV"] not in SETORES:
            continue
        cod = int(l["CD_CVM"])
        if cod in EXCLUIR:
            continue
        nome = NOMES.get(cod) or l["DENOM_COMERC"].title()
        inst[cod] = {
            "id": cod,
            "nome": nome,
            "sigla": sigla(nome),
            "razao_social": l["DENOM_SOCIAL"],
            "cnpj": l["CNPJ_CIA"],
            "setor": l["SETOR_ATIV"],
            "orgao": "CVM",
            "ri": RI.get(cod),
            "eventos": [],
        }
    return inst


# ---------- 2. Datas previstas (calendário da CVM) ----------

MODELO = [
    (re.compile(r"1º trimestre\s+(\d{2}/\d{2}/\d{4})"), "ITR", "1T"),
    (re.compile(r"2º trimestre\s+(\d{2}/\d{2}/\d{4})"), "ITR", "2T"),
    (re.compile(r"3º trimestre\s+(\d{2}/\d{2}/\d{4})"), "ITR", "3T"),
    (re.compile(r"DFP relativas ao exercício social findo em \d{2}/\d{2}/(\d{4})\s+(\d{2}/\d{2}/\d{4})"), "DFP", "4T"),
]


def ler_calendario(pdf_bytes):
    """Lê o PDF do calendário (modelo padrão da CVM) e devolve as datas de entrega."""
    texto = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_bytes)).pages)
    texto = re.sub(r"[ \t]+", " ", texto)
    achados = []
    for regex, tipo, tri in MODELO:
        m = regex.search(texto)
        if not m:
            continue
        if tipo == "DFP":
            ano_ref, quando = int(m.group(1)), m.group(2)
        else:
            quando = m.group(1)
            ano_ref = int(quando[-4:])
        d = datetime.strptime(quando, "%d/%m/%Y").date()
        achados.append({"tipo": tipo, "tri": tri, "ano": ano_ref, "data": d.isoformat()})
    return achados


def carregar_ipe():
    docs = []
    for ano in (HOJE.year - 1, HOJE.year):
        try:
            docs += csv_do_zip(f"{CVM}/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip", f"ipe_cia_aberta_{ano}.csv")
        except Exception as erro:
            print(f"  IPE {ano} indisponível: {erro}")
    return docs


def datas_previstas(inst, docs):
    cache_arq = CACHE / "calendarios.json"
    cache = json.loads(cache_arq.read_text(encoding="utf-8")) if cache_arq.exists() else {}
    # Cada banco entrega vários calendários (um por ano e as revisões). Lê todos,
    # do mais antigo para o mais novo, e a versão mais nova de cada data vence.
    calendarios = sorted(
        (d for d in docs if int(d["Codigo_CVM"]) in inst and d["Categoria"] == "Calendário de Eventos Corporativos"),
        key=lambda d: (d["Data_Entrega"], d["Versao"]),
    )
    datas = {}
    for d in calendarios:
        cod = int(d["Codigo_CVM"])
        chave = d["Protocolo_Entrega"] + "-" + d["Versao"]
        if chave not in cache:
            try:
                cache[chave] = ler_calendario(baixar(d["Link_Download"]))
                print(f"  calendário lido: {inst[cod]['nome']} ({len(cache[chave])} datas)")
            except Exception as erro:  # não guarda no cache: tenta de novo na próxima rodada
                print(f"  calendário ilegível: {inst[cod]['nome']} ({erro})")
                continue
        por_evento = datas.setdefault(cod, {})
        for x in cache[chave]:
            por_evento[(x["tipo"], x["tri"], x["ano"])] = x
    datas = {cod: list(v.values()) for cod, v in datas.items()}
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_arq.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return datas


# ---------- 2b. PDFs do resultado (release, análise gerencial, demonstrações) ----------

DOCUMENTOS = {
    "Press-release": (1, "Release de resultados"),
    "Relatório de Análise Gerencial": (2, "Análise gerencial"),
    "Demonstrações Financeiras Intermediárias": (3, "Demonstrações financeiras"),
    "Demonstrações Financeiras Anuais Completas": (3, "Demonstrações financeiras"),
}


def documentos_resultado(inst, docs):
    """{(cod, tri, ano): [docs]} com a versão mais nova de cada tipo de PDF."""
    achados = {}
    for d in docs:
        cod = int(d["Codigo_CVM"])
        if cod not in inst or d["Categoria"] != "Dados Econômico-Financeiros" or d["Tipo"] not in DOCUMENTOS:
            continue
        try:
            ref = date.fromisoformat(d["Data_Referencia"])
        except ValueError:
            continue
        if ref.month not in (3, 6, 9, 12):
            continue
        tri = f"{(ref.month - 1) // 3 + 1}T"
        ordem, nome = DOCUMENTOS[d["Tipo"]]
        grupo = achados.setdefault((cod, tri, ref.year), {})
        atual = grupo.get(nome)
        if not atual or (d["Data_Entrega"], d["Versao"]) > (atual["entregue"], atual["versao"]):
            grupo[nome] = {"nome": nome, "ordem": ordem, "entregue": d["Data_Entrega"], "versao": d["Versao"],
                           "link": d["Link_Download"].replace("http://", "https://")}
    return {k: [{"nome": x["nome"], "link": x["link"], "entregue": x["entregue"]}
                for x in sorted(v.values(), key=lambda x: x["ordem"])] for k, v in achados.items()}


def baixa_pdf(link, cache):
    """Alguns PDFs a CVM não entrega (devolve uma página de erro). Lê só o começo do arquivo para saber."""
    if cache.get(link):
        return True
    try:
        with urllib.request.urlopen(urllib.request.Request(link, headers=AGENTE), timeout=60) as r:
            ok = r.read(5) == b"%PDF-"
    except Exception:
        ok = False
    if ok:
        cache[link] = True  # só guarda o sucesso; o que falhou é testado de novo na próxima rodada
    return ok


def filtrar_pdfs(pdfs):
    cache_arq = CACHE / "pdfs.json"
    cache = json.loads(cache_arq.read_text(encoding="utf-8")) if cache_arq.exists() else {}
    limite = (HOJE - timedelta(days=200)).isoformat()
    filtrados = {}
    for chave, lista in pdfs.items():
        if max(x["entregue"] for x in lista) < limite:
            continue
        bons = [x for x in lista if baixa_pdf(x["link"], cache)]
        if bons:
            filtrados[chave] = bons
    cache_arq.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    falhas = sum(len(v) for v in pdfs.values() if max(x["entregue"] for x in v) >= limite) - sum(len(v) for v in filtrados.values())
    print(f"  {sum(len(v) for v in filtrados.values())} PDFs ok, {falhas} indisponíveis na CVM")
    return filtrados


# ---------- 3. Balanços já entregues (ITR/DFP) ----------

def entregues(inst):
    feitos = {}
    for tipo in ("ITR", "DFP"):
        for ano in (HOJE.year - 1, HOJE.year):
            nome = f"{tipo.lower()}_cia_aberta_{ano}"
            try:
                linhas = csv_do_zip(f"{CVM}/DOC/{tipo}/DADOS/{nome}.zip", f"{nome}.csv")
            except Exception as erro:
                print(f"  {tipo} {ano} indisponível: {erro}")
                continue
            for l in linhas:
                cod = int(l["CD_CVM"])
                if cod not in inst:
                    continue
                ref = date.fromisoformat(l["DT_REFER"])
                tri = f"{(ref.month - 1) // 3 + 1}T"
                chave = (cod, tipo, tri, ref.year)
                if chave not in feitos or l["DT_RECEB"] < feitos[chave]["recebido"]:
                    # O LINK_DOC baixa um .zip pesado; o visualizador da CVM abre direto no celular.
                    seq = re.search(r"NumeroSequencialDocumento=(\d+)", l["LINK_DOC"])
                    link = (f"https://www.rad.cvm.gov.br/ENET/frmGerenciaPaginaFRE.aspx?NumeroSequencialDocumento={seq.group(1)}&CodigoTipoInstituicao=1"
                            if seq else l["LINK_DOC"].replace("http://", "https://"))
                    feitos[chave] = {"recebido": l["DT_RECEB"], "link": link}
    return feitos


# ---------- 4. Prazo legal quando não há data informada ----------

def prazo_legal(tipo, tri, ano):
    if tipo == "DFP":  # até 3 meses depois do fim do exercício
        return date(ano + 1, 3, 31)
    fim = {"1T": date(ano, 3, 31), "2T": date(ano, 6, 30), "3T": date(ano, 9, 30)}[tri]
    return fim + timedelta(days=45)  # ITR: até 45 dias depois do fim do trimestre


def trimestres_relevantes():
    """Os últimos 2 períodos já encerrados e o próximo, para o calendário."""
    periodos = []
    for ano in (HOJE.year - 1, HOJE.year, HOJE.year + 1):
        periodos += [("ITR", "1T", ano), ("ITR", "2T", ano), ("ITR", "3T", ano), ("DFP", "4T", ano)]
    janela_ini, janela_fim = HOJE - timedelta(days=200), HOJE + timedelta(days=200)
    return [p for p in periodos if janela_ini <= prazo_legal(*p) <= janela_fim]


# ---------- 5. Notícia de que o resultado saiu ----------

def noticia_resultado(nome, tri, ano):
    rotulo = {"1T": "primeiro trimestre", "2T": "segundo trimestre", "3T": "terceiro trimestre", "4T": "quarto trimestre"}[tri]
    busca = f'"{nome}" (lucro OR resultado) "{rotulo}" when:4d'
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": busca, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"})
    try:
        raiz = ET.fromstring(baixar(url))
    except Exception as erro:
        print(f"  notícias indisponíveis para {nome}: {erro}")
        return None
    for item in raiz.iter("item"):
        titulo = item.findtext("title") or ""
        if nome.split()[0].lower() in titulo.lower():
            return {"titulo": titulo, "link": item.findtext("link"), "quando": item.findtext("pubDate")}
    return None


# ---------- Montagem ----------

def montar():
    print("Instituições...")
    inst = carregar_instituicoes()
    print(f"  {len(inst)} instituições")
    print("Calendários...")
    ipe = carregar_ipe()
    previstas = datas_previstas(inst, ipe)
    print("PDFs dos resultados...")
    pdfs = filtrar_pdfs(documentos_resultado(inst, ipe))
    print("Entregas na CVM...")
    feitos = entregues(inst)
    periodos = trimestres_relevantes()

    for cod, i in inst.items():
        for tipo, tri, ano in periodos:
            ev = {"tipo": tipo, "periodo": f"{tri}{str(ano)[2:]}", "tri": tri, "ano": ano}
            info = next((x for x in previstas.get(cod, []) if x["tipo"] == tipo and x["tri"] == tri and x["ano"] == ano), None)
            if info:
                ev["data"], ev["fonte"] = info["data"], "confirmada"
            else:
                ev["data"], ev["fonte"] = prazo_legal(tipo, tri, ano).isoformat(), "prazo"
            entrega = feitos.get((cod, tipo, tri, ano))
            if pdfs.get((cod, tri, ano)):
                ev["docs"] = pdfs[(cod, tri, ano)]
                if not entrega:  # o release costuma chegar à base antes do ITR
                    entrega = {"recebido": min(x["entregue"] for x in ev["docs"]), "link": None}
            if entrega:
                ev["status"], ev["saiu_em"] = "saiu", entrega["recebido"]
                if entrega["link"]:
                    ev["pdf"] = entrega["link"]
            else:
                ev["status"] = "previsto"
                prevista = date.fromisoformat(ev["data"])
                # Perto da data, procura notícia (a base da CVM só atualiza semanalmente).
                if prevista - timedelta(days=1) <= HOJE <= prevista + timedelta(days=5):
                    n = noticia_resultado(i["nome"], tri, ano)
                    if n:
                        ev["status"], ev["saiu_em"], ev["noticia"] = "saiu", HOJE.isoformat(), n
                        print(f"  saiu (notícia): {i['nome']} {ev['periodo']}")
            i["eventos"].append(ev)

    print("Fintechs na SEC...")
    inst.update(fintechs_sec(periodos))

    lista = sorted(inst.values(), key=lambda x: x["nome"])
    SAIDA.mkdir(exist_ok=True)
    dados = {"atualizado": datetime.now(BRT).isoformat(timespec="minutes"), "instituicoes": lista}
    (SAIDA / "dados.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    escrever_agenda(lista)
    print(f"Pronto: {sum(len(i['eventos']) for i in lista)} eventos.")


def fintechs_sec(periodos):
    cache_arq = CACHE / "sec.json"
    cache = json.loads(cache_arq.read_text(encoding="utf-8")) if cache_arq.exists() else {}
    dados = sec.coletar(cache, HOJE)
    cache_arq.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    inst = {}
    for cik, d in dados.items():
        info = d["info"]
        i = {"id": cik, "nome": info["nome"], "sigla": info["sigla"], "razao_social": info["nome"],
             "setor": info["bolsa"], "orgao": "SEC", "cik": cik, "eventos": []}
        for _tipo, tri, ano in periodos:
            chave = (tri, ano)
            ev = {"tipo": "ITR", "periodo": f"{tri}{str(ano)[2:]}", "tri": tri, "ano": ano}
            res = d["resultados"].get(chave)
            if chave in d["avisos"]:
                ev["data"], ev["fonte"] = d["avisos"][chave], "confirmada"
            elif res:
                ev["data"], ev["fonte"] = res["recebido"], "confirmada"
            else:
                estimada = sec.estimar(d["resultados"], tri, ano)
                if not estimada:
                    continue
                ev["data"], ev["fonte"] = estimada, "estimada"
            if res:
                ev["status"], ev["saiu_em"], ev["pdf"] = "saiu", res["recebido"], res["link"]
            else:
                ev["status"] = "previsto"
            i["eventos"].append(ev)
        inst[cik] = i
    return inst


def escrever_agenda(lista):
    """Arquivo .ics: assinado no celular, as datas aparecem na agenda."""
    linhas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Radar de Balancos//PT", "X-WR-CALNAME:Radar de Balanços", "CALSCALE:GREGORIAN"]
    agora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for i in lista:
        for ev in i["eventos"]:
            d = date.fromisoformat(ev["data"])
            texto = {"confirmada": "data confirmada", "prazo": "prazo legal", "estimada": "estimativa pelo ano anterior"}[ev["fonte"]]
            linhas += [
                "BEGIN:VEVENT",
                f"UID:{i['id']}-{ev['tipo']}-{ev['periodo']}@radar-balancos",
                f"DTSTAMP:{agora}",
                f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}",
                f"SUMMARY:{i['nome']} · balanço {ev['periodo']}",
                f"DESCRIPTION:{texto}",
                "BEGIN:VALARM", "TRIGGER:-PT12H", "ACTION:DISPLAY", f"DESCRIPTION:{i['nome']} divulga amanhã", "END:VALARM",
                "END:VEVENT",
            ]
    linhas.append("END:VCALENDAR")
    (SAIDA / "agenda.ics").write_text("\r\n".join(linhas) + "\r\n", encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    montar()
