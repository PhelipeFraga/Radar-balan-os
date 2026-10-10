// Radar de Balanços: lê dados.json (gerado pelo coletor) e desenha as telas.
"use strict";

const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const SEMANA = ["DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SÁB"];
const SEMANA_LONGA = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"];
const TRIMESTRE = { "1T": "1º trimestre", "2T": "2º trimestre", "3T": "3º trimestre", "4T": "4º trimestre" };
const CVM_BUSCA = "https://www.rad.cvm.gov.br/ENETWeb/frmConsultaExternaCVM.aspx";

const tela = document.getElementById("tela");
const estado = { dados: null, erro: null, mes: null, diaEscolhido: null, busca: "", filtro: "todas" };

// ---------- utilidades ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dataLocal = (iso) => { const [a, m, d] = iso.slice(0, 10).split("-").map(Number); return new Date(a, m - 1, d); };
const hoje = () => { const h = new Date(); return new Date(h.getFullYear(), h.getMonth(), h.getDate()); };
const isoDe = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const diasEntre = (a, b) => Math.round((b - a) / 86400000);
const curta = (d) => `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
const longa = (d) => `${SEMANA_LONGA[d.getDay()]}, ${d.getDate()} de ${MESES[d.getMonth()]}`;
const descricao = (ev) => ev.tipo === "DFP" ? `Balanço anual de ${ev.ano}` : `Resultado do ${TRIMESTRE[ev.tri]} de ${ev.ano}`;
const descricaoCurta = (ev) => ev.tipo === "DFP" ? `Balanço anual ${ev.ano}` : `Resultado ${ev.tri.replace("T", "º tri")} ${ev.ano}`;

function seguindo() {
  try {
    const salvo = JSON.parse(localStorage.getItem("radar.desligadas") || "[]");
    return (id) => !salvo.includes(id);
  } catch { return () => true; }
}
function alternar(id) {
  try {
    const salvo = new Set(JSON.parse(localStorage.getItem("radar.desligadas") || "[]"));
    salvo.has(id) ? salvo.delete(id) : salvo.add(id);
    localStorage.setItem("radar.desligadas", JSON.stringify([...salvo]));
  } catch { /* sem armazenamento: a escolha vale só nesta visita */ }
}

// Todos os eventos, já ligados à instituição.
function eventos({ soSeguidas = true } = {}) {
  if (!estado.dados) return [];
  const segue = seguindo();
  const lista = [];
  for (const inst of estado.dados.instituicoes) {
    if (soSeguidas && !segue(inst.id)) continue;
    for (const ev of inst.eventos) lista.push({ inst, ev, data: dataLocal(ev.data) });
  }
  return lista;
}
const chave = (x) => `${x.inst.id}-${x.ev.tipo}-${x.ev.periodo}`;
const selo = (ev) => ev.status === "saiu"
  ? `<span class="selo saiu">Saiu</span>`
  : ev.fonte === "confirmada" ? `<span class="selo conf">Data confirmada</span>`
  : ev.fonte === "estimada" ? `<span class="selo prazo">Estimativa</span>` : `<span class="selo prazo">Prazo legal</span>`;
const seta = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>`;
const voltar = (href) => `<a class="redondo" href="${href}" aria-label="Voltar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 6-6 6 6 6"/></svg></a>`;

function linhaEvento(x, comDia = true) {
  const d = x.data;
  const esquerda = comDia
    ? `<div class="dia">${d.getMonth() !== hoje().getMonth() ? `<i>${MESES[d.getMonth()].slice(0, 3).toUpperCase()}</i>` : ""}<b>${d.getDate()}</b><span>${SEMANA[d.getDay()]}</span></div>`
    : `<div class="logo">${esc(x.inst.sigla)}</div>`;
  return `<a class="item" href="#evento/${chave(x)}">${esquerda}
    <div class="meio"><div class="nome">${esc(x.inst.nome)}</div><div class="info">${descricaoCurta(x.ev)}</div></div>${selo(x.ev)}</a>`;
}

// ---------- telas ----------
function telaHoje() {
  const h = hoje();
  const todos = eventos();
  const saidos = todos.filter((x) => x.ev.status === "saiu" && x.ev.saiu_em)
    .sort((a, b) => b.ev.saiu_em.localeCompare(a.ev.saiu_em));
  const ultimo = saidos[0];
  let destaque = "";
  if (ultimo) {
    const quando = dataLocal(ultimo.ev.saiu_em);
    const recente = diasEntre(quando, h) <= 3;
    const rotulo = recente ? (diasEntre(quando, h) === 0 ? "SAIU HOJE" : "SAIU AGORA · " + curta(quando)) : "ÚLTIMO QUE SAIU · " + curta(quando);
    destaque = `<a class="destaque" href="#evento/${chave(ultimo)}">
      <div class="rotulo">${recente ? '<div class="ponto"></div>' : ""}${rotulo}</div>
      <div style="display:flex;align-items:center;gap:14px"><div class="logo">${esc(ultimo.inst.sigla)}</div>
        <div style="display:flex;flex-direction:column;gap:2px;min-width:0"><div style="font-size:19px;font-weight:800">${esc(ultimo.inst.nome)}</div>
        <div style="font-size:14px;color:#C9D2E8">${descricao(ultimo.ev)}</div></div></div>
      <div class="acao">Abrir balanço ${seta}</div></a>`;
  }
  const futuros = todos.filter((x) => x.ev.status !== "saiu" && x.data >= h).sort((a, b) => a.data - b.data);
  const semana = futuros.filter((x) => diasEntre(h, x.data) <= 7);
  const mostrar = semana.length ? semana : futuros.slice(0, 5);
  const mesAtual = saidos.filter((x) => { const d = dataLocal(x.ev.saiu_em); return d.getMonth() === h.getMonth() && d.getFullYear() === h.getFullYear(); }).length;
  const qtd = estado.dados ? estado.dados.instituicoes.filter((i) => seguindo()(i.id)).length : 0;

  tela.innerHTML = `
    <div class="topo"><div><div class="subtitulo">${longa(h)}</div><h1>Radar de Balanços</h1></div></div>
    ${destaque}
    <div class="cabeca-secao"><h2>${semana.length ? "Próximos 7 dias" : "Próximos balanços"}</h2><a href="#calendario">Ver calendário</a></div>
    <div class="cartao lista">${mostrar.length ? mostrar.map((x) => linhaEvento(x)).join("") : '<div class="vazio">Nenhum balanço previsto. Confira as instituições que você acompanha.</div>'}</div>
    <div class="numeros">
      <div class="cartao"><b>${qtd}</b><span>instituições acompanhadas</span></div>
      <div class="cartao"><b>${mesAtual}</b><span>balanços saíram este mês</span></div>
    </div>
    ${rodapeAtualizacao()}`;
}

function telaCalendario() {
  const h = hoje();
  if (!estado.mes) estado.mes = new Date(h.getFullYear(), h.getMonth(), 1);
  if (!estado.diaEscolhido) estado.diaEscolhido = isoDe(h);
  const mes = estado.mes;
  const porDia = {};
  for (const x of eventos()) (porDia[x.ev.data] ||= []).push(x);
  const primeiro = new Date(mes.getFullYear(), mes.getMonth(), 1).getDay();
  const total = new Date(mes.getFullYear(), mes.getMonth() + 1, 0).getDate();
  let celulas = SEMANA.map((s) => `<div class="sem">${s}</div>`).join("");
  for (let i = 0; i < primeiro; i++) celulas += "<div></div>";
  for (let n = 1; n <= total; n++) {
    const d = new Date(mes.getFullYear(), mes.getMonth(), n);
    const iso = isoDe(d);
    const doDia = porDia[iso] || [];
    const cor = doDia.length ? (doDia.some((x) => x.ev.fonte === "confirmada") ? "var(--azul)" : "var(--laranja)") : "transparent";
    const classes = [d < h ? "passado" : "", iso === isoDe(h) ? "hoje" : "", iso === estado.diaEscolhido ? "escolhido" : ""].join(" ");
    const rotulo = `${n} de ${MESES[d.getMonth()]}${doDia.length ? `, ${doDia.length} balanço(s)` : ""}`;
    celulas += `<button class="${classes}" data-dia="${iso}" aria-label="${rotulo}"><span class="num">${n}</span><span class="marca" style="background:${cor}"></span></button>`;
  }
  const escolhido = dataLocal(estado.diaEscolhido);
  const doEscolhido = (porDia[estado.diaEscolhido] || []).sort((a, b) => a.inst.nome.localeCompare(b.inst.nome));

  tela.innerHTML = `
    <div class="topo"><h1>Calendário</h1>
      <div style="display:flex;gap:8px">
        <button class="redondo" data-mes="-1" aria-label="Mês anterior"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 6-6 6 6 6"/></svg></button>
        <button class="redondo" data-mes="1" aria-label="Próximo mês"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg></button>
      </div></div>
    <div class="cartao mes"><div class="titulo">${MESES[mes.getMonth()][0].toUpperCase() + MESES[mes.getMonth()].slice(1)} de ${mes.getFullYear()}</div>
      <div class="grade-mes">${celulas}</div>
      <div class="legenda"><div><i style="background:var(--azul)"></i>Data confirmada</div><div><i style="background:var(--laranja)"></i>Prazo legal</div></div>
    </div>
    <h2>${longa(escolhido)}</h2>
    <div class="cartao lista">${doEscolhido.length ? doEscolhido.map((x) => linhaEvento(x, false)).join("") : '<div class="vazio">Nenhum balanço neste dia.</div>'}</div>
    <a class="botao claro" href="agenda.ics">Colocar as datas na agenda do celular</a>
    <p class="nota">Bancos na bolsa informam a data à CVM (azul). Quando não há data informada, o app mostra o prazo máximo da regra (laranja): 45 dias depois do fim do trimestre, e 3 meses depois do fim do ano para o balanço anual.</p>`;

  tela.querySelectorAll("[data-dia]").forEach((b) => b.addEventListener("click", () => { estado.diaEscolhido = b.dataset.dia; desenhar(); }));
  tela.querySelectorAll("[data-mes]").forEach((b) => b.addEventListener("click", () => {
    estado.mes = new Date(mes.getFullYear(), mes.getMonth() + Number(b.dataset.mes), 1);
    desenhar();
  }));
}

const ICONE_DOC = `<div style="width:40px;height:40px;border-radius:12px;background:var(--azul-claro);display:flex;align-items:center;justify-content:center;flex-shrink:0"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1A35A8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg></div>`;

// Só os dois documentos que importam: o release e as demonstrações.
const PRINCIPAIS = ["Release de resultados", "Demonstrações financeiras"];
function listaDocs(ev) {
  const docs = (ev.docs || []).filter((d) => PRINCIPAIS.includes(d.nome))
    .map((d) => ({ nome: d.nome, fonte: `PDF · entregue em ${curta(dataLocal(d.entregue))}`, link: d.link }));
  if (!docs.length && ev.noticia) docs.push({ nome: ev.noticia.titulo, fonte: "Notícia", link: ev.noticia.link });
  return docs;
}
const ICONE_BAIXAR = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2346D8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/></svg>`;
const docsHtml = (docs) => docs.map((d) => `<a class="item" href="${esc(d.link)}" target="_blank" rel="noopener">${ICONE_DOC}
  <div class="meio"><div class="nome" style="white-space:normal">${esc(d.nome)}</div><div class="info">${esc(d.fonte)}</div></div>${ICONE_BAIXAR}</a>`).join("");

// Atalhos no topo escuro: site de RI e CVM.
function atalhos(inst) {
  const globo = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18"/></svg>`;
  const predio = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 21h18M5 21V10M19 21V10M9 21V10M15 21V10M2 10l10-6 10 6"/></svg>`;
  return `<div class="atalhos">
    ${inst.ri ? `<a href="${esc(inst.ri)}" target="_blank" rel="noopener">${globo}Site de RI</a>` : ""}
    <a href="${CVM_BUSCA}" target="_blank" rel="noopener">${predio}Ver na CVM</a></div>`;
}

function capa(inst, extra = "") {
  return `<div class="capa">${voltar("javascript:history.back()")}
      <div style="display:flex;align-items:center;gap:14px"><div class="logo">${esc(inst.sigla)}</div>
        <div style="display:flex;flex-direction:column;gap:4px;min-width:0"><div style="font-size:24px;font-weight:800">${esc(inst.nome)}</div>
        <div style="font-size:14px;color:#C9D2E8">${esc(inst.setor)}</div></div></div>
      ${extra}${atalhos(inst)}
    </div>`;
}

function telaInstituicao(id) {
  const inst = estado.dados.instituicoes.find((i) => String(i.id) === id);
  if (!inst) { tela.innerHTML = `${voltar("#instituicoes")}<div class="erro">Instituição não encontrada.</div>`; return; }
  const h = hoje();
  const evs = inst.eventos.map((ev) => ({ inst, ev, data: dataLocal(ev.data) }));
  const proximo = evs.filter((x) => x.ev.status !== "saiu" && x.data >= h).sort((a, b) => a.data - b.data)[0];
  const saidos = evs.filter((x) => x.ev.status === "saiu").sort((a, b) => (b.ev.ano - a.ev.ano) || b.ev.tri.localeCompare(a.ev.tri));
  const ultimo = saidos[0];
  const anuais = saidos.filter((x) => x.ev.tipo === "DFP" && x !== ultimo);

  let blocoProximo = '<div class="cartao" style="padding:18px"><div class="vazio" style="padding:0">Sem data prevista.</div></div>';
  if (proximo) {
    const d = proximo.data;
    const faltam = diasEntre(h, d);
    blocoProximo = `<div class="cartao" style="padding:18px;display:flex;align-items:center;gap:16px">
      <div style="width:64px;height:72px;border-radius:18px;background:var(--azul-claro);display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0">
        <div style="font-size:11px;font-weight:800;letter-spacing:.5px;color:var(--azul)">${MESES[d.getMonth()].slice(0, 3).toUpperCase()}</div>
        <div style="font-size:28px;font-weight:800;line-height:1.05">${d.getDate()}</div>
        <div style="font-size:11px;font-weight:700;color:var(--suave)">${SEMANA[d.getDay()]}</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;min-width:0">
        <div style="font-size:16px;font-weight:800">${descricao(proximo.ev)}</div>
        <div style="font-size:13px;color:var(--suave);font-weight:600">${faltam === 0 ? "É hoje" : faltam === 1 ? "Amanhã" : `Faltam ${faltam} dias`}</div>
        <div>${selo(proximo.ev)}</div>
      </div></div>`;
  }

  const blocoBalanco = (x, vazio) => {
    const docs = listaDocs(x.ev);
    return `<div class="cartao lista">
      <div class="item"><div class="meio"><div class="nome">${descricao(x.ev)}</div><div class="info">Saiu em ${curta(dataLocal(x.ev.saiu_em))}/${dataLocal(x.ev.saiu_em).getFullYear()}</div></div></div>
      ${docs.length ? docsHtml(docs) : `<div class="vazio" style="padding:14px 0">${vazio}</div>`}</div>`;
  };

  tela.innerHTML = `
    ${capa(inst)}
    <h2>Próximo balanço</h2>
    ${blocoProximo}
    <h2>Último balanço</h2>
    ${ultimo ? blocoBalanco(ultimo, "Os PDFs ainda não chegaram à base da CVM. Veja no site de RI, no topo.") : '<div class="cartao lista"><div class="vazio">Nenhum balanço encontrado.</div></div>'}
    ${anuais.length ? `<h2>Balanços anuais anteriores</h2>${anuais.map((x) => blocoBalanco(x, "Os PDFs deste ano não estão disponíveis na CVM.")).join("")}` : ""}
    <div class="cartao" style="padding:18px;display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;justify-content:space-between;align-items:center"><div style="font-size:15px;font-weight:800">Números dos últimos balanços</div><span class="etiqueta-fase">Em breve</span></div>
      <div style="font-size:13px;color:var(--suave);line-height:1.5">Lucro, carteira, inadimplência e Basileia, trimestre a trimestre, vão aparecer aqui.</div>
    </div>`;
}

function telaEvento(id) {
  const x = eventos({ soSeguidas: false }).find((e) => chave(e) === id);
  if (!x) { tela.innerHTML = `${voltar("#hoje")}<div class="erro">Balanço não encontrado.</div>`; return; }
  const { inst, ev } = x;
  const saiu = ev.status === "saiu";
  const quando = saiu && ev.saiu_em ? dataLocal(ev.saiu_em) : x.data;
  const rotulo = saiu ? `<div class="ponto"></div>SAIU · ${curta(quando)}` : `PREVISTO · ${curta(x.data)}`;
  const linhaFonte = saiu
    ? (ev.pdf || (ev.docs || []).length ? "Entregue à CVM" : "Saiu na imprensa · a CVM confirma em até uma semana")
    : ev.fonte === "confirmada" ? "Data informada pelo banco à CVM" : "Sem data informada · este é o prazo máximo da regra";
  const docs = listaDocs(ev);
  const avisoSemDocs = saiu
    ? "Os PDFs entram aqui quando a CVM atualizar a base (uma vez por semana). Enquanto isso, o release já está no site de RI, no topo."
    : "Quando o balanço sair, o release e as demonstrações financeiras aparecem aqui para baixar.";
  const resumo = `<div style="display:flex;flex-direction:column;gap:6px">
        <div style="display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;letter-spacing:.4px;color:${saiu ? "#A7F3C0" : "#C9D2E8"}">${rotulo}</div>
        <div style="font-size:20px;font-weight:800;line-height:1.3">${saiu ? "Saiu o " + descricao(ev).charAt(0).toLowerCase() + descricao(ev).slice(1) : descricao(ev)}</div>
        <div style="font-size:13px;color:#C9D2E8">${linhaFonte}</div>
      </div>`;

  tela.innerHTML = `
    ${capa(inst, resumo)}
    <h2>Documentos</h2>
    <div class="cartao lista">${docs.length ? docsHtml(docs) : `<div class="vazio" style="padding:14px 0">${avisoSemDocs}</div>`}</div>
    <a class="botao claro" href="#inst/${inst.id}">Ver tudo de ${esc(inst.nome)}</a>
    <div class="cartao" style="padding:18px;display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;justify-content:space-between;align-items:center"><div style="font-size:15px;font-weight:800">Números principais</div><span class="etiqueta-fase">Em breve</span></div>
      <div style="font-size:13px;color:var(--suave);line-height:1.5">Lucro, carteira, inadimplência e Basileia vão aparecer aqui sozinhos, minutos depois de o balanço sair.</div>
    </div>`;
}

function telaInstituicoes() {
  const segue = seguindo();
  const todas = estado.dados ? estado.dados.instituicoes : [];
  const termo = estado.busca.trim().toLowerCase();
  const h = hoje();
  const lista = todas.filter((i) => (estado.filtro === "todas" || segue(i.id)) && (!termo || (i.nome + " " + i.razao_social).toLowerCase().includes(termo)));
  const proximo = (i) => {
    const fut = i.eventos.filter((e) => e.status !== "saiu" && dataLocal(e.data) >= h).sort((a, b) => a.data.localeCompare(b.data))[0];
    if (!fut) return "Sem data prevista";
    return `${fut.fonte === "confirmada" ? "Próximo" : "Prazo"}: ${curta(dataLocal(fut.data))} · ${fut.periodo}`;
  };
  const qtdSegue = todas.filter((i) => segue(i.id)).length;

  tela.innerHTML = `
    <div class="topo"><h1>Instituições</h1></div>
    <label class="busca"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8A90A0" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <input type="search" id="busca" aria-label="Buscar instituição" placeholder="Buscar banco ou financeira" value="${esc(estado.busca)}"></label>
    <div class="filtros">
      <button data-filtro="todas" class="${estado.filtro === "todas" ? "ativo" : ""}">Todas · ${todas.length}</button>
      <button data-filtro="seguindo" class="${estado.filtro === "seguindo" ? "ativo" : ""}">Acompanhando · ${qtdSegue}</button>
    </div>
    <div class="cartao lista">${lista.length ? lista.map((i) => `<div class="item"><a href="#inst/${i.id}" style="display:flex;align-items:center;gap:12px;flex:1;min-width:0;text-decoration:none;color:inherit"><div class="logo">${esc(i.sigla)}</div>
      <div class="meio"><div class="nome">${esc(i.nome)}</div><div class="info">${proximo(i)}</div></div></a>
      <button class="chave" role="switch" aria-checked="${segue(i.id)}" aria-label="Acompanhar ${esc(i.nome)}" data-id="${i.id}"><i></i></button></div>`).join("")
      : '<div class="vazio">Nenhuma instituição encontrada.</div>'}</div>
    <p class="nota">Por enquanto, o app cobre os bancos e financeiras com ações ou registro na CVM. Desligue a chave das que você não quer ver no Hoje e no Calendário.</p>`;

  const campo = tela.querySelector("#busca");
  campo.addEventListener("input", () => { estado.busca = campo.value; const pos = campo.selectionStart; desenhar(); const novo = tela.querySelector("#busca"); novo.focus(); novo.setSelectionRange(pos, pos); });
  tela.querySelectorAll("[data-filtro]").forEach((b) => b.addEventListener("click", () => { estado.filtro = b.dataset.filtro; desenhar(); }));
  tela.querySelectorAll(".chave").forEach((b) => b.addEventListener("click", () => { alternar(Number(b.dataset.id)); desenhar(); }));
}

function telaNumeros() {
  tela.innerHTML = `
    <div class="topo"><h1>Números</h1><span class="etiqueta-fase">Em breve</span></div>
    <div class="cartao" style="padding:20px;display:flex;flex-direction:column;gap:10px">
      <h2>Os números de cada balanço, sozinhos</h2>
      <p style="margin:0;font-size:14px;color:var(--suave);line-height:1.6">Na próxima fase, o robô vai ler cada balanço que sair e montar lucro, carteira de crédito, inadimplência e Basileia, com o histórico de 8 trimestres e a comparação entre as instituições.</p>
    </div>`;
}

function rodapeAtualizacao() {
  if (!estado.dados) return "";
  const d = new Date(estado.dados.atualizado);
  return `<p class="nota">Dados atualizados em ${curta(d)} às ${String(d.getHours()).padStart(2, "0")}h${String(d.getMinutes()).padStart(2, "0")}. Fontes: CVM e imprensa.</p>`;
}

// ---------- navegação ----------
function desenhar() {
  const rota = (location.hash || "#hoje").slice(1);
  const [aba, ...resto] = rota.split("/");
  document.querySelectorAll("nav.abas a").forEach((a) => a.classList.toggle("ativa", a.dataset.aba === aba || (aba === "evento" && a.dataset.aba === "hoje") || (aba === "inst" && a.dataset.aba === "instituicoes")));
  if (estado.erro && !estado.dados) { tela.innerHTML = `<h1>Radar de Balanços</h1><div class="erro">Não consegui carregar os dados. Verifique a internet e abra o app de novo.</div>`; return; }
  if (!estado.dados) { tela.innerHTML = `<h1>Radar de Balanços</h1><p class="nota">Carregando…</p>`; return; }
  ({ hoje: telaHoje, calendario: telaCalendario, instituicoes: telaInstituicoes, numeros: telaNumeros }[aba] || (aba === "evento" ? () => telaEvento(resto.join("/")) : aba === "inst" ? () => telaInstituicao(resto.join("/")) : telaHoje))();
}

window.addEventListener("hashchange", () => { desenhar(); window.scrollTo(0, 0); });

async function carregar() {
  desenhar();
  try {
    const r = await fetch("dados.json", { cache: "no-cache" });
    estado.dados = await r.json();
  } catch (e) {
    estado.erro = e;
  }
  desenhar();
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
carregar();
