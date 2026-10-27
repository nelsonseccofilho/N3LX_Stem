# Karaokê: escolha de idioma — rc.6

O usuário escolhe Português ou Inglês antes de gerar. O idioma é enviado explicitamente e registrado no JSON; valores não suportados são rejeitados antes de arquivar um resultado existente. A escolha do idioma não altera o idioma da interface.

Português continua usando WhisperGPU, Vulkan e o alinhador ONNX DirectML instalado. O CTC e algumas operações ONNX usam CPU. Inglês usa whisper.cpp Vulkan e tempos por palavra, sem aplicar o alinhador específico de português. A interface informa a diferença, e não exibe uma etapa de alinhamento avançado durante a geração em inglês. A rota inglesa confirma o backend Vulkan no log; não há troca silenciosa para CPU ou para outro modelo. Pesos, FFmpeg e worker devem estar disponíveis localmente; não há download automático. A letra e os tempos exigem revisão musical.

## Verificação

- Execução inglesa isolada com a amostra pública de fala jfk.wav: Large v3, 22 palavras, idioma en, backend Vulkan confirmado, tempos por palavra e conclusão em 11,4 s. Isso não é teste de música cantada.
- O fluxo português foi validado na rc.5 com voz real; esta mudança preserva esse fluxo. A primeira rodada de testes teve 27 aprovações, 1 skip por symlink e 1 falha de cancelamento imediato; a condição de início foi corrigida e o teste afetado passou na repetição direcionada. Um teste adicional confirmou que a API encaminha `en` e preserva cópia do JSON anterior.
- Navegador com áudio sintético: escolha PT/EN, envio do idioma, etapas corretas, cancelamento e disponibilidade de modelos sem troca automática. A primeira tentativa de interface usou uma simulação que manteve o sinal de cancelamento de uma execução anterior; a simulação foi corrigida e o teste passou.

A pré-release requer uma instalação AMD existente e, para o alinhamento português, o NELX-Whisper-GPU. Qualidade musical e instalação limpa em outro computador permanecem pendentes.
