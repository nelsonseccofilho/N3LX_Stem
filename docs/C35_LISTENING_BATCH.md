# C35.2 — Bateria unica de validacao auditiva no Windows

## Objetivo

Reunir os cenarios manuais de audio numa unica abertura do executavel
empacotado, sem refazer C32-C35.1. A bateria anterior de transporte,
exportacao WAV/FFprobe e teardown passou no C35.1. O arquivo C35.2 nao
promove evidencias automatizadas a comprovacao de som realmente ouvido.

## Execucao

Use o worktree isolado desta branch (Git Bash):

    bash scripts/qa/c35-listening-batch.sh

O script verifica o pacote ja aprovado e seu manifesto SHA256, sem gerar
outro executavel, cria biblioteca sintetica e perfil exclusivos e uma porta
livre. Mostra seis testes na mesma tela (Play/Pause/Stop, Mute/Solo, pan,
saida padrao do Windows e qualidade), abre o EXE uma unica vez e aguarda
o usuario fechar a janela normalmente.

Apos a janela fechar, uma unica sequencia de seis respostas s/n/p gera
listening-qa.json no relatorio C35-ListeningBatch-XXXXXXXX. O status nao
e inferido automaticamente de uma barra de progresso:
- PASS se todos os seis itens foram confirmados pelo usuario;
- PARTIAL_OPTIONAL_NOT_TESTED se apenas pan/troca de dispositivo nao
  foram exercitados e os quatro controles obrigatorios foram aprovados;
- PENDING_REQUIRED_CHECK se faltar teste basico;
- FAIL em qualquer problema relatado.

O script executa teardown do backend apenas quando a janela ja foi
confirmada fechada normalmente. Nas interrupcoes, verifica a porta e
se recusa a parar um processo com janela possivelmente ativa. Nenhum
kill, reset, manipulacao de biblioteca pessoal ou limpeza de playlists.

## O que nao e repetido

- C32/C33 renderer e endpoints
- C34 build e redimensionamentos nativos
- C35.1 exportacao WAV e teste tecnico de audio

A qualidade em hardware, escolha da saida real e mudanca da saida
padrao exigem percepcao e relato humanos. Os testes usam somente
tons curtos sinteticos, nunca arquivos particulares.

## Proximas ondas

Apos a evidencia C35.2, consolidar os resultados em PR e definir o
proximo ciclo que possuir lacuna real de aceite (e nao apenas repetir
rotinas aprovadas). Manter logs e capturas na pasta QA local.
