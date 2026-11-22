# C28 — piloto do Design System e Tailwind CSS v4

Status: piloto isolado, baseado na main `10a1682` (PR #27). Não é release.

## Escopo e resultado

O diálogo `#karaokeSettings` recebe uma folha de estilos própria, compilada com
Tailwind CSS **4.3.5**. Campos agora seguem os temas claro/escuro; abas mantêm o
foco ao navegar com setas, Home e End. O clique em Buscar letra mantém o fluxo
existente de preenchimento. IDs, API, renderizador e persistência são preservados.

Sem daisyUI, React, shadcn ou dependências de UI em runtime. Tailwind/CLI são
dependências de desenvolvimento com versões exatas no lockfile. A aplicação
consome o CSS compilado versionado, sem precisar de Node na instalação.

## Auditoria do repositório e preservação

- Main limpa em `7b905c0`, seis commits atrás: atualizada por fast-forward para
  `10a1682`, após confirmar o merge remoto e a porta 8159 livre.
- O PID antigo não estava mais ouvindo. Não havia cliente persistente a fechar;
  nenhum processo foi encerrado à força. Backend iniciado uma vez pelo controlador.
- 57 jobs na API e 57 diretórios com `metadata.json`; há 58 diretórios no total.
- Manifesto de 1.969 arquivos da biblioteca (tamanho/mtime), hashes e cópias dos
  JSONs, diffs e inventário dos worktrees guardados em backup privado fora do Git.
- 11 worktrees anteriores inventariados; quatro fontes de releases e os três
  checkouts auxiliares existentes preservados. Três registros apontam para locais
  indisponíveis: dois no perfil antigo e um em D:. Não executar prune sem conferir
  os volumes e o histórico. O novo worktree C28 é independente.
- 22 auxiliares não rastreados dos checkouts C24/C27 foram arquivados após
  comparar SHA-256 com uma segunda cópia. Nada foi apagado; esses dois checkouts
  ficaram limpos. O piloto Tailwind antigo continua intacto e foi substituído
  apenas como área ativa de desenvolvimento.
- Nenhuma geração de karaokê, separação, download de modelos ou alteração de áudio.

## Arquitetura e componentes

`styles/karaoke-settings.css` é a fonte. `static/css/karaoke-settings.css` é o
resultado minificado: **2.370 bytes**. Todos os seletores começam com
`#karaokeSettings.sd-dialog`, verificado no CSSOM do navegador.

Importamos somente `tailwindcss/utilities.css` com `source(none)`. `@theme inline`
mapeia utilitários usados por `@apply` aos aliases locais. Não importamos Preflight
nem o tema global e não há varredura geral de classes. Não há seletores globais
na saída. Referências oficiais: [CLI](https://tailwindcss.com/docs/installation/tailwind-cli),
[Preflight opcional](https://tailwindcss.com/docs/preflight),
[`@theme inline`](https://tailwindcss.com/docs/theme).

| Primitiva | Contrato | Tokens / estados |
|---|---|---|
| Dialog | Modal nativo, largura máxima 680 px, teto 85dvh/760 px e rolagem interna | `--sd-surface`, `--sd-text`, `--sd-border`, raio, padding, sombra; Escape e retorno de foco existentes |
| Tabs | Três colunas; estado via `aria-selected`; roving tabindex | superfície do controle, texto secundário/ativo, borda e foco; setas/Home/End mantêm foco nas abas |
| Button | IDs e handlers existentes; mínimo 34 px | fonte, raio, hover, disabled e foco comuns; ações específicas mantêm as cores legadas |
| Field | Inputs, select e textarea seguem o tema | superfície do controle, texto, borda `--muted-2`, placeholder e foco; input hidden excluído |

Aliases locais usam `--bg-2`, `--panel`, `--panel-2`, `--fg`, `--fg-2`,
`--border-strong`, `--muted-2`, `--accent`, `--radius-xs`, `--font-sans` e
`--shadow-panel`. A autoridade dos temas continua em variables.css/themes.css.
Espaçamento de 4 px, dimensões do diálogo e controles ficam declarados na fonte.

Os estilos legados continuam disponíveis como fallback. O ganho inicial é uma
fatia de manutenção delimitada e tokens explícitos; este piloto **acrescenta**
2,4 KB e não representa redução de daw.css ou migração geral.

## QA executado no Windows / Edge headless

| Verificação | Resultado |
|---|---|
| Python: lifecycle, reinício e regressões de karaokê | 87 passed, 1 skipped (symlink); um aviso de depreciação FastAPI/httpx |
| JavaScript | 54 arquivos de teste aprovados; runner portátil preserva falhas de qualquer arquivo |
| Diálogo | 1920×1080, 1440×900, 1366×786 × dark/light: 18 estados de abas, sem overflow horizontal |
| Teclado | Setas/Home/End, Tab/Shift+Tab, Escape, retorno de foco e outline visível aprovados |
| Contraste amostrado | Texto visível de título, notas, abas e campos ≥4,5:1; foco da aba ≥3:1 nos dois temas |
| Escala efetiva | Viewports 1092×628 e 910×524, equivalentes a 125%/150% do mínimo: fechar diálogo acessível |
| Fluxos com backend real e dados sintéticos | 3/3 resoluções: reprodução/parada, mute/solo, alinhamento de lanes, busca simulada, prévia, salvar/cancelar, recarga e tempos manuais |
| Cabeçalho com biblioteca real protegida contra gravação | 3 resoluções, cold/reload/forced/warm, sem salto de altura/overflow, reprodução e geometria de controles |
| Cinema com biblioteca real protegida contra gravação | 3 resoluções: fullscreen, seek, término, transposição ±2, reset e foco; em 1920 também pausas/instrumental, avanço e congelamento do relógio |
| Build / dependências | CSS reproduzível byte a byte, sintaxe JS, diff --check, npm audit sem vulnerabilidades reportadas |

Comparação com o CSS original e os mesmos dados sintéticos: largura do diálogo
inalterada em 680 px e altura cerca de 3,2 px menor nas três abas, após regularizar
espaçamento e campos. Menor contraste textual amostrado: 5,94:1 no escuro e
6,01:1 no claro. Capturas de referência, piloto e foco foram preservadas localmente.

Os testes de contraste são amostras de estados visíveis, não uma auditoria WCAG
completa. Escala efetiva não substitui inspeção de todas as configurações de DPI
do Windows. Não certificamos alinhamento acústico por escuta, geração PT/EN,
novo executável, pacote instalado ou CI hospedado. O teste Cinema usa uma faixa
local específica e não é um teste genérico para qualquer biblioteca.

## Reproduzir (Git Bash)

No worktree, com Node e Edge já disponíveis:

```bash
npm ci
npm run build:css
npm run test:js

# Runtime existente; somente a biblioteca temporária é usada na porta 8161.
runtime="$HOME/Git/N3LX_Stem"
py="$runtime/.venv/Scripts/python.exe"
qa="$(mktemp -d)"
"$py" -B scripts/backend_control.py verify-free --port 8161 --runtime "$runtime" --data "$qa"
"$py" -B tests/e2e/seed.py "$qa/jobs"
"$py" -B scripts/backend_control.py start --port 8161 --runtime "$runtime" --data "$qa"
C28_PHASE=baseline C28_EVIDENCE=test-results/c28-baseline npm run test:c28
C28_EVIDENCE=test-results/c28-pilot npm run test:c28
npx playwright test -c tests/c28-workflows.config.mjs
"$py" -B scripts/backend_control.py stop --port 8161 --runtime "$runtime" --data "$qa"
```

O teste C28 recusa uma biblioteca que não contenha exatamente os dois IDs de
seed.py. Busca LRCLIB é simulada e geração/retiming são bloqueados. A suíte de
fluxos grava apenas os dados sintéticos. A pasta temporária é mantida para
inspeção; não há limpeza recursiva automática. O backend pessoal 8159 não é
reiniciado pelos testes do diálogo.

O build Windows existente copia arquivos `static/` rastreados por Git; o CSS
compilado está nesse caminho. Não é necessário executar npm na instalação.
Não foi gerado pacote Desktop neste ciclo.

## Reversão e próximos ciclos

Remover o link CSS e a classe `sd-dialog` de index.html restaura os estilos
anteriores, mantendo a correção de teclado independente. Reverter o commit do
piloto remove também fonte, artefato e dependências. Não há migração de dados.

Próxima fatia: revisar o piloto visualmente no aplicativo Desktop instalado;
depois extrair apenas as regras legadas comprovadamente substituídas e medir o
saldo de CSS. Migrar outro diálogo somente após essa revisão. Mixer, timeline,
motor de áudio e layout geral permanecem fora do piloto. Integração por PR;
nenhum merge, tag ou release automático.
