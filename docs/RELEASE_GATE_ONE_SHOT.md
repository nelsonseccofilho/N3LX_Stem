# Gate unico de release: um comando e um relatorio por revisao

Executar em Git Bash, worktree QA limpo:

    bash scripts/qa/release-gate.sh

Esta bateria somente le a instalacao AMD ja existente. Nao instala
dependencias, nao reseta projeto, nao acessa biblioteca pessoal, nao
para backend estranho e nao reexecuta as suites antigas C32/C33/C34.

Passos, sem repeticoes automaticas:
1. Validador local de Python, JS e sintaxe ja existente.
2. E2E Chromium completo em porta e diretorio novos e isolados.
   Se nao existem dependencias ou permissoes, BLOCKED em vez de instalar.
3. EXE Windows real gerado do SHA candidato, via C35: Play, WAV
   exportado pelo menu do aplicativo, FFprobe, encerramento cooperativo.
4. Resultado unico em ReleaseGate-XXXXXXXX/summary.json e RESULT.md.

O E2E isolado nunca reutiliza outro servidor e recusa apagar scratch
preexistente. Um link temporario node_modules pode ser usado somente
no worktree isolado e removido se for comprovadamente o link criado.

O resultado de C35.2 (6/6 audio escutado) pode ser carregado como
evidencia humana historica SOMENTE quando nao mudou codigo de produto;
nao se trata de nova prova fisica de som.

Lacunas de release permanecem visiveis:
- Real inference AMD/GPU (nao stubs CPU);
- Alinhamento PT/EN de voz cantada e timestamps reais;
- Instalacao em maquina limpa (pacote atual exige AMD preinstalado).

Automation PASS NAO significa RELEASE READY enquanto estas lacunas
nao tiverem evidencias. Todos os testes locais continuam separados do
CI hospedado skipped. A suite antiga de Nvidia/Tauri nao deve ser
executada diretamente no AMD/Electron atual.

## Correcao do bloqueio de caminhos

O repositorio QA pode estar dentro do diretorio N3LX_Stem-Releases;
a pasta ReleaseGate-XXXXXXXX sera criada como **irma** desse worktree,
jamais dentro dele. A validacao bloqueia qualquer saida dentro do codigo,
dentro do runtime pessoal, ou um diretorio que contenha o runtime.
Ninguem apaga ou renomeia diretorios anteriores. Um teste leve de politica
de caminhos e executado antes dos demais gates.

## Retomada direcionada: browser bloqueado por falta de uv no PATH

Em modo isolado, o servidor E2E agora usa o Python/uvicorn AMD ja
instalado (em vez de depender do comando global uv); o modo legado
do serve.sh continua usando uv e nao foi modificado.

Para nao reconstruir o pacote nem rerodar testes Python/JS ja aprovados,
use o relatorio privado do gate anterior, como primeiro argumento:

    bash scripts/qa/release-gate.sh "$HOME/Git/N3LX_Stem-Releases/ReleaseGate-n39q9wlx"

O comando valida o sha completo do relatorio, a integridade dos dois
gates PASS, o teardown/porta do EXE e exige que entre a revisao anterior
e a nova tenham mudado SOMENTE arquivos de orquestracao/testes QA
listados no codigo. Caso contrario, bloqueia a retomada: e necessario
executar o gate completo para produto alterado. A nova saida identifica
os passos reaproveitados como CARRIED, nunca como testes reexecutados.
Um resultado PASS_WITH_CARRIED_EVIDENCE nao significa que as pendencias
reais de AMD GPU, letra PT/EN e instalador estejam resolvidas.

### Node/Playwright sem symlink no Windows

A bateria usa `scripts/qa/e2e-runtime-loader.mjs` para resolver apenas
os imports de Playwright a partir do runtime Node existente. Nao precisa
permissao de criar symlink, nao faz copia de pacotes e nao modifica o
runtime principal. Requer Node 20+; uma falha de resolucao permanece FAIL
e nao e maquiada como sucesso.

## Windows Node 26 — caminho absoluto de ESM loader

O Node interpreta um caminho Windows C:\\\\... passado como loader ESM como
protocolo `c:` (ERR_UNSUPPORTED_ESM_URL_SCHEME). Em modo Git Bash, o
orquestrador passa `loader.resolve().as_uri()` (file:///C:/...) e executa
um teste isolado e rapido de `import('@playwright/test')` antes de abrir
backend ou iniciar os E2E. Se o carregamento falhar, retorna BLOCKED
com diagnostico sem repetir etapas previamente aprovadas.
