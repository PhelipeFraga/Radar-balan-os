# Radar de Balanços · regras para o Claude

App de celular do Phelipe que mostra quando cada instituição financeira divulga o balanço, avisa quando sai, traz os PDFs e os números principais. Roda de graça no GitHub (robô + GitHub Pages), sem gastar o plano do Claude. Responda sempre em português, direto.

- App: https://phelipefraga.github.io/Radar-balan-os/
- Repositório (público): https://github.com/PhelipeFraga/Radar-balan-os
- Histórico de decisões e fases: nota `02-Projetos/Radar de Balanços.md` no Segundo Cérebro (`Desktop\Segundo-Cerebro`).

## Regras que nunca mudam
- **Só dados públicos** (CVM, B3, Banco Central, notícias). Nada de dado do banco onde o Phelipe trabalha, de carteira ou de clientes. O repositório é público.
- **Nunca colocar o e-mail pessoal do Phelipe** no código, nos commits ou nos segredos. Commits usam o e-mail anônimo do GitHub.
- Não guardar PDFs no repositório (estoura o limite gratuito); o app aponta para o link da CVM.
- Não usar a busca de documentos da CVM com captcha.
- Fintechs com sede no exterior (`coletor/sec.py`) ficam desligadas até o Phelipe cadastrar o segredo `SEC_CONTATO`.

## Como trabalhar
- **Enviar ao `main` = publicar.** Testar no computador antes; só levar ao `main` depois que o Phelipe aprovar o que viu.
- Tela ou fluxo novo: mostrar a proposta (Design no claude.ai) e esperar aprovação antes de programar. "Faz" = executar e entregar.
- Refino: mudança mínima, preservando o visual aprovado (Design: https://claude.ai/artifact/9AgBq6EGMkP4m8xsSoRJjv).
- Testar em tela de celular (375 e 360 px); nada pode vazar para o lado nem ficar cortado.
- **A cada mudança no app:** subir a `VERSAO` em `docs/sw.js` (ex.: `radar-v6` → `radar-v7`) e manter a lista `ARQUIVOS` completa.
- Mensagem de commit em português, dizendo o que mudou para o usuário.
- O Claude coordena o projeto; usar mais agentes só com autorização do Phelipe.

## Arquivos
- `docs/`: o app (é a pasta que o GitHub Pages publica). `index.html`, `app.js`, `sw.js`, `manifest.webmanifest`, ícones. `dados.json` e `agenda.ics` são **gerados pelo robô**: não editar à mão.
- `coletor/`: robô em Python.
  - `coletar.py`: monta tudo (`montar()`): instituições da CVM, calendários (PDF no modelo padrão da CVM), PDFs de resultado, prazos legais, aviso "saiu" pelas notícias.
  - `ifdata.py`: números do Banco Central (IF.data, conglomerado prudencial).
  - `sec.py`: fintechs no exterior (desligado).
  - `cache/`: cache do robô, versionado.
- `.github/workflows/atualizar.yml`: robô roda 5x por dia (6h, 10h, 14h, 18h e 20h30 de Brasília) e quando o código do coletor muda; faz commit "dados: atualização automática" só se algo mudou.
- `.venv/`: ambiente Python local (fora do Git).
- Procure sempre pelo **nome da função** (`def nome(`), não pelo número da linha.

## Dados e limitações conhecidas
- Prazos legais: ITR 45 dias após o trimestre; DFP 3 meses após o fim do ano. Instituições fechadas não divulgam data: o app mostra o prazo legal.
- IF.data sai 2 a 3 meses após o trimestre; lucro vem somado no semestre (o robô calcula o trimestre). Estágio 3 e Over 90 só desde 2025 (Res. 4.966).
- A base aberta da CVM só atualiza aos domingos; por isso o "saiu" usa notícias.
