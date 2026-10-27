# Karaokê com JSON do WhisperGPU — rc.5

A geração usa apenas `stems/vocals.wav`. O worker local NELX-Whisper-GPU executa reconhecimento com whisper.cpp Vulkan e alinhamento ONNX/DirectML; o caminho CTC e algumas operações ONNX usam CPU. Não é feita diarização. O alinhador instalado suporta português; a escolha fica visível no seletor. O JSON integrado é validado e normalizado para o sidecar existente, com tempos reais por palavra, idioma, backend e número de alertas. O resultado segue automático e requer revisão.

A instalação existente precisa conter `NELX-Whisper-GPU` no perfil do usuário ou no caminho definido por `N3LX_WHISPER_GPU_HOME`, incluindo seus ambientes Python e modelo ONNX; o worker Vulkan, FFmpeg e os pesos Whisper devem estar configurados. O pacote não inclui nem baixa esses recursos. Ambiente indisponível, erro de execução, JSON inválido ou falta de evidência Vulkan/DirectML produz falha explícita, sem trocar silenciosamente o modelo ou a GPU. O processo e seus filhos são encerrados no cancelamento antes de liberar a operação.

A geração ocupa a trava de processamento; a interface informa fila, preparação, reconhecimento, alinhamento e salvamento. Ao regenerar, o JSON anterior é arquivado em cópia privada antes da nova tentativa, como na rc.3. A edição manual, stems, playlists e mixagens permanecem independentes.

## Verificação local

- 25 testes Python aprovados e um skip (symlink indisponível neste Windows), incluindo saída JSON sintética, validação de backend, ausência de recursos, cancelamento e proteção do sidecar.
- 10 verificações de navegador com biblioteca sintética e respostas simuladas, incluindo fase de alinhamento, cancelamento, exclusão, temas e janela de 800 px. A primeira tentativa começou antes do servidor de testes estar disponível; outra tentativa encontrou a barra lateral sobre o botão em 800 px; a verificação foi ajustada para fechar o cenário estreito antes de continuar no tamanho desktop.
- Uma execução isolada com a pista vocal de uma música real produziu 129 palavras, português e 24 alertas de revisão. Os relatórios do worker confirmaram Vulkan e DirectML; o conteúdo anterior e o áudio tiveram hashes iguais antes e depois. Tempo total 121,7 segundos na máquina de teste. Não comprova que a letra ou os tempos estejam corretos; a comparação musical permanece pendente.
- Os oito JSONs produzidos anteriormente foram aceitos pelo normalizador, sem executar modelos novamente.

A rc.5 é pré-release para atualização de uma instalação AMD existente. Não há alegação de CI hospedado ou instalação limpa validada.
