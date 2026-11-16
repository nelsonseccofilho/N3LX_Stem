# C27.9 — reinício pelo Git Bash

Comando único, no worktree `c24-unified-qa-code`:

```bash
bash scripts/restart-backend.sh
```

O roteiro Bash executa `check-ready` → `stop` → `verify-free` → `start` → `status`. A integração Windows e o endpoint autenticado são tratados pelo Python existente; o roteiro não chama PowerShell nem arquivos `.ps1`. A verificação inicial compara instância, PID, intérprete, código carregado, diretórios de dados/jobs, saúde, fila e operações em andamento. Uma condição ocupada ou identidade divergente interrompe o roteiro antes da parada. A parada é cooperativa; a porta precisa ficar livre antes do novo início. O início confirma API saudável e hashes do código.

Por padrão usa porta 8159, runtime `C:/Users/Nelson Secco/Git/N3LX_Stem` e dados `C:/Users/Nelson Secco/Git/N3LX_Stem-Releases/c21-biblioteca-completa-qa/data`. Variáveis `N3LX_PORT`, `N3LX_RUNTIME` e `N3LX_DATA` permitem testar somente com outra biblioteca isolada. O Python define os caminhos portáteis, DirectML, ffmpeg/ffprobe, Whisper Vulkan, modelo large-v3, worker e SAM conforme o inicializador oficial, preservando overrides explícitos.

Validação: 12 testes Python aprovados; roteiro Bash exercitado na biblioteca sintética da porta 8160, com PID 28740 → 30876, porta liberada entre eles e saúde/identidade confirmadas. O servidor sintético foi encerrado cooperativamente depois. O PID 17792 da porta 8159 não foi reiniciado nessa validação.

## Geração controlada CPM22

Em 2026-11-16, a instância controlada da porta 8159 já carregava os hashes corrigidos no PID 17792. Uma única chamada `POST /api/jobs/2e2c72eee977/karaoke/generate` (`large-v3`, `pt`, `replace=false`) foi aceita. O processo passou por preparação, reconhecimento, alinhamento e conclusão, sem repetição. O reconhecimento executou `whisper-cli.exe` da compilação Vulkan; o sidecar registra `gpu_verified=true`, `engine=whisperx`, `alignment_backend=cpu`, `pipeline_revision=2`.

O arquivo `lyrics_timing.json` contém 331 palavras com intervalos válidos, ordenados e sem sobreposição. O relatório do worker indicou 50 alertas, mas sua lista detalhada foi descartada com o diretório temporário após a conclusão. O estado segue `machine_unverified`: estes dados comprovam execução do alinhador e estrutura dos tempos, não precisão auditiva. A biblioteca continua com 56 jobs; fila vazia; metadados e stem de vocais da CPM22 inalterados. A API devolve o sidecar com HTTP 200 após a geração.

O QA Playwright/Edge em 1920×1080 encontrou `stemdeck:lyrics:2e2c72eee977 = {dismissed:true}` no armazenamento compartilhado. A interface normal respeita a remoção anterior e mostra “Letra removida desta faixa”. Uma sessão isolada de leitura ocultou somente essa preferência na resposta de rede, sem alterar os dados salvos: exibiu 52 linhas, avançou a reprodução a 00:02 e voltou a exibir as linhas após recarregar. Capturas e resultados estão em `../c279-generation-20261116/`. A exibição normal ainda requer uma decisão explícita sobre a preferência de remoção; a avaliação perceptiva dos vocais permanece pendente.
