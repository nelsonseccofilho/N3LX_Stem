# rc.3 — processamento e regeneração de karaokê

Gerar e gerar novamente apresentam um painel de processamento no lugar da letra: fila, preparar vocais, reconhecer voz/sincronizar palavras e salvar. A etapa vem do servidor; o relógio mostra tempo decorrido. O worker não fornece percentual, portanto a barra é indeterminada. Cancelar permanece acessível e a biblioteca/reprodução continuam utilizáveis.

Na regeneração, a configuração é validada e a exclusividade da operação é obtida antes de retirar `lyrics_timing.json` de uso. O arquivo anterior é movido para uma cópia privada `lyrics_timing.regenerated-*.json`. Se houver cancelamento ou falha, o resultado antigo não volta a aparecer como novo. O usuário pode gerar outra vez. O novo JSON é escrito atomicamente a partir de uma transcrição nova.

O botão **Excluir JSON do karaokê** pede confirmação e remove apenas o resultado automático ativo, mantendo uma cópia privada para recuperação. Letra manual, sincronização manual, áudio, stems e misturas são preservados. Nenhum JSON da biblioteca real foi excluído nesta revisão.

## Evidência focada

- 21 testes Python aprovados, 1 skip por indisponibilidade de symlink no Windows. Cobertura de sucesso/falha/cancelamento, remoção antes do worker, configuração inválida, exclusividade, proteção de caminhos e preservação dos arquivos independentes.
- 10 verificações no Edge com áudio sintético e respostas de geração simuladas: ocultar prévia anterior, solicitar nova geração Large v3, fases do servidor, barra sem percentual, relógio, temas claro/escuro e janela de 800 px, cancelar, mostrar novo resultado e excluir JSON. Sem erros de execução da página.
- Sintaxe JavaScript e `git diff --check` aprovados.

A rota Vulkan/AMD e os argumentos do Whisper não foram alterados. Não houve inferência de modelo nem avaliação de qualidade de música cantada neste ajuste. A rc.3 continua sendo atualização para instalação AMD existente; não é instalação autônoma. Relatórios antigos rc.1/rc.2 são históricos; main já foi integrado por PR #8 e #9 sem exigir GitHub Actions.
