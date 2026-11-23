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
