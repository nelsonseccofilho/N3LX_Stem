# Recuperar a bateria de "07 Rastro e sinais" — N3LX_Stem 0.21.0-rc.4

Este é um **hotfix temporário e específico para a instalação Windows** identificada no traceback real de 31/10/2026:

- Job original: `4e06a0bc7d91`
- Erro: `ValueError: Detailed stem would clip in PCM24`
- Instalação: `D:\git\N3LX_Stem-Releases\0.21.0-rc.4\N3LX_Stem-Windows-Update-0.21.0-rc.4`
- Backend observado: `127.0.0.1:8140`

A correção definitiva já está em `main` (PR #16). Este script coloca
**somente** a mesma mudança no backend Python do pacote rc4 já instalado,
sem recompilar o executável Windows e sem mexer na área de dados.

## Etapas

Baixe `scripts/windows/Install-DrumFloat-Rastro-rc4.ps1` da versão integrada ao
GitHub e salve em arquivo local (não copie comandos de fontes desconhecidas).

1. Com o app ainda disponível, execute
   `& $script -Mode Patch`. O comando valida o arquivo original, cria
   backup externo e altera apenas `_aligned_copy`; não inicia extrações.
2. **Feche e reabra normalmente** o N3LX_Stem para carregar o backend Python
   atualizado. Não é necessário reinstalar, limpar cache ou tocar na Biblioteca.
3. Com o app aberto na porta 8140 e o perfil **Completo** selecionado,
   execute `& $script -Mode Reextract`. Este comando consulta o job original
   e, somente quando a fonte é um upload local retido, chama
   `POST /api/jobs/4e06a0bc7d91/resplit`. A API cria um ID e uma
   `source_url` diferentes, mantendo a música original.
4. Depois de a nova extração terminar, execute
   `& $script -Mode Verify`. Sucesso é
   `FINAL_RESULT: RASTRO_DRUMS_RECOVERED_6_OF_6`.

**Regra importante:** se a origem for URL ou o upload original não estiver
retido, a ação segura falha com explicação; jamais força uma reimportação
que substitua o registro anterior. Para esse caso, será necessário usar o
arquivo original ou criar uma nova importação preservando a anterior.

## Segurança

- O script não executa `git reset`, `checkout`, remoção de arquivos de
  música, regravação de stems nem exclusão de playlists.
- Não altera `D:\git\stemdeck`.
- Faz backup da cópia de `complete_multitrack.py` antes de alterar e realiza
  rollback em caso de falha.
- Confere se a porta 8140 pertence **à instalação corrigida** e se o processo
  Python foi iniciado depois da atualização, antes de permitir a reextração.
- Guarda o ID de submissão para não repetir involuntariamente a mesma tarefa.
- Não tenta consertar a GPU, reinstalar Demucs ou baixar modelos.
- O hotfix **não** instala a nova exportação de três resíduos; ela está em
  `main` mas requer novo build completo de backend e interface.

## Status

A presença de um commit/PR não equivale à execução local do hotfix. A recuperação
da música só está confirmada após o resultado `6/6` na nova extração.
