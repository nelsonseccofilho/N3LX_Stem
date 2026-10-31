# Rastro e sinais: backend de desenvolvimento ativo (31/10/2026)

O diagnóstico do PowerShell confirmou que a porta `127.0.0.1:8140` **não é servida pelo backend empacotado 0.21.0-rc.4**. O processo Python responsável foi iniciado pela venv:

`D:\git\stemdeck\.venv\Scripts\python.exe`

O patch rc4 anterior foi aplicado corretamente apenas na pasta de release, mas o servidor ativo continuou o processo anterior (PID 16892, iniciado às 01:55).

## Correção segura

O script `scripts/windows/Repair-Active-Drum-Float-Rastro.ps1` atua no arquivo do checkout ativo (`D:\git\stemdeck\app\pipeline\complete_multitrack.py`) e faz três etapas explícitas.

1. **Patch:** valida a árvore do processo da porta 8140 e o módulo Python importado pela venv, identifica exatamente a condição antiga `PCM_24` / `Detailed stem would clip in PCM24`, preserva o original em `%LOCALAPPDATA%\N3LX_Stem\Rastro-Backup`, muda apenas a função `_aligned_copy` para `FLOAT`, valida sintaxe com `ast.parse` e faz rollback em caso de falha.
2. **Reinicie o Uvicorn do projeto** pelo método habitual de desenvolvimento. Não basta fechar um `.exe` não relacionado; o PID do servidor antigo precisa mudar. O script **não encerra nem reinicia processos automaticamente**, para não perder o ambiente e variáveis de inicialização.
3. **Reextract:** verifica novamente a origem do servidor, se o processo foi iniciado depois da atualização do arquivo, perfil `complete`, job original concluído, origem `local:`, bateria 0/6 e ausência de reextrações anteriores. Chama a API existente `POST /api/jobs/4e06a0bc7d91/resplit` para criar um **novo job**, sem alterar o anterior.
4. **Verify:** lê o novo job e confirma o estado `done` com `6/6` peças da bateria.

## Uso

Baixar a versão do script do GitHub e executar:

```powershell
& "$env:TEMP\N3LX_Active_Rastro.ps1" -Mode Patch
# Reiniciar o backend Uvicorn do projeto D:\git\stemdeck.
& "$env:TEMP\N3LX_Active_Rastro.ps1" -Mode Reextract
# Após conclusão:
& "$env:TEMP\N3LX_Active_Rastro.ps1" -Mode Verify
```

**Limitações:** `/resplit` reutiliza arquivos locais retidos; para música originalmente importada de URL, não força a importação pelo mesmo link (isso poderia substituir o item antigo na Biblioteca). Nesse caso, a extração precisa de um caminho separado e seguro. O patch não altera Git (exceto o arquivo Python local), não remove arquivos, nem reextrai outras músicas.

**Critério de encerramento:** saída real `FINAL_RESULT: RASTRO_DRUMS_RECOVERED_6_OF_6` da máquina Windows. PR integrado, arquivo corrigido ou script baixado **não comprovam** esse resultado.
