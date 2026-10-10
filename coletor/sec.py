"""Fintechs brasileiras com sede no exterior (Nubank, Inter&Co, XP, PagBank).

Elas entregam os resultados à SEC (EUA) em formulários 6-K, não à CVM.
Do 6-K o robô tira duas coisas:
- o aviso de data ("will report its third quarter 2026 results on November 12, 2026"): data confirmada;
- o próprio release de resultados: "saiu".
Sem aviso, estima a data pelo mesmo trimestre do ano anterior.
"""

import json
import os
import re
import time
import urllib.request
from datetime import date, datetime, timedelta
from html import unescape

# A SEC exige que robôs se identifiquem com um contato (sec.gov/developer).
CONTATO = os.environ.get("SEC_CONTATO", "")

FINTECHS = {
    1691493: {"nome": "Nubank", "sigla": "NU", "bolsa": "NYSE · BDR na B3"},
    1912938: {"nome": "Inter&Co", "sigla": "IN", "bolsa": "Nasdaq · BDR na B3"},
    1787425: {"nome": "XP Inc.", "sigla": "XP", "bolsa": "Nasdaq · BDR na B3"},
    1712807: {"nome": "PagBank", "sigla": "PB", "bolsa": "NYSE"},
}

TRI = {"first": "1T", "second": "2T", "third": "3T", "fourth": "4T", "1q": "1T", "2q": "2T", "3q": "3T", "4q": "4T",
       "q1": "1T", "q2": "2T", "q3": "3T", "q4": "4T"}
MESES = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                     "september", "october", "november", "december"], 1)}

R_PERIODO = re.compile(r"\b(first|second|third|fourth)\s+quarter\s+(?:of\s+|fiscal\s+year\s+)?(20\d\d)|\b([1-4]q|q[1-4])\s?'?(\d{2}|20\d\d)\b", re.I)
R_AVISO = re.compile(r"(?:will|to)\s+(?:report|announce|release|publish|disclose)", re.I)
R_RESULTADO = re.compile(r"(?:reports?|announces?|delivers?|posts?)\b.{0,80}?\b(?:results|earnings)|(?:results|earnings)\s+(?:release|for the)", re.I)
R_DATA = re.compile(r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(20\d\d)", re.I)


def _baixar(url):
    if not CONTATO:
        raise RuntimeError("SEC_CONTATO não definido")
    pedido = urllib.request.Request(url, headers={"User-Agent": f"Radar de Balancos {CONTATO}", "Accept-Encoding": "identity"})
    time.sleep(0.2)  # bem abaixo do limite de 10 pedidos por segundo da SEC
    with urllib.request.urlopen(pedido, timeout=60) as r:
        return r.read()


def _texto(html):
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", t)))


def _periodo(trecho):
    m = R_PERIODO.search(trecho)
    if not m:
        return None
    if m.group(1):
        return TRI[m.group(1).lower()], int(m.group(2))
    ano = int(m.group(4))
    return TRI[m.group(3).lower()], ano if ano > 2000 else 2000 + ano


def ler_6k(texto, entregue):
    """Classifica um 6-K: aviso de data, release de resultado ou nada."""
    for m in R_AVISO.finditer(texto):
        trecho = texto[m.start(): m.start() + 300]
        p, d = _periodo(trecho), R_DATA.search(trecho)
        if p and d and ("result" in trecho.lower() or "earning" in trecho.lower()):
            quando = date(int(d.group(3)), MESES[d.group(1).lower()], int(d.group(2)))
            if quando >= entregue:
                return {"tipo": "aviso", "tri": p[0], "ano": p[1], "data": quando.isoformat()}
    inicio = texto[:4000]
    if R_RESULTADO.search(inicio):
        p = _periodo(inicio)
        if p:
            return {"tipo": "resultado", "tri": p[0], "ano": p[1]}
    return None


def coletar(cache, hoje):
    """Devolve {cik: {"info": ..., "avisos": {...}, "resultados": {...}}}."""
    saida = {}
    if not CONTATO:
        print("  desligado: falta o contato exigido pela SEC (segredo SEC_CONTATO)")
        return saida
    for cik, info in FINTECHS.items():
        try:
            sub = json.loads(_baixar(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
        except Exception as erro:
            print(f"  SEC indisponível para {info['nome']}: {erro}")
            continue
        rec = sub["filings"]["recent"]
        avisos, resultados = {}, {}
        for forma, entregue, acesso, doc in zip(rec["form"], rec["filingDate"], rec["accessionNumber"], rec["primaryDocument"]):
            entregue_d = date.fromisoformat(entregue)
            if forma != "6-K" or entregue_d < hoje - timedelta(days=500):
                continue
            pasta = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acesso.replace('-', '')}"
            if acesso not in cache:
                try:
                    cache[acesso] = ler_6k(_texto(_baixar(f"{pasta}/{doc}").decode("utf-8", "ignore")), entregue_d)
                except Exception as erro:
                    print(f"  6-K ilegível ({info['nome']} {acesso}): {erro}")
                    continue
            achado = cache[acesso]
            if not achado:
                continue
            chave = (achado["tri"], achado["ano"])
            if achado["tipo"] == "aviso":
                avisos.setdefault(chave, achado["data"])  # o mais recente vem primeiro
            elif chave not in resultados or entregue < resultados[chave]["recebido"]:
                resultados[chave] = {"recebido": entregue, "link": f"{pasta}/{acesso}-index.htm"}
        saida[cik] = {"info": info, "avisos": avisos, "resultados": resultados}
        print(f"  {info['nome']}: {len(avisos)} avisos de data, {len(resultados)} resultados")
    return saida


def estimar(resultados, tri, ano):
    """Mesmo trimestre do ano anterior + 52 semanas (cai no mesmo dia da semana)."""
    antes = resultados.get((tri, ano - 1))
    if not antes:
        return None
    return (date.fromisoformat(antes["recebido"]) + timedelta(weeks=52)).isoformat()
