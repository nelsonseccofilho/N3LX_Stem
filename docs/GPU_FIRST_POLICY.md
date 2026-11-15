# Contrato GPU First — N3LX_Stem

Status: **proposta de política arquitetural para revisão e integração**.
Escopo: todos os processos do aplicativo, do import ao export, incluindo processamento em segundo plano, modelos de IA e pipelines do Karaokê.
Ambiente principal de referência: Windows + AMD Radeon RX 6600M.

> Este documento define regras de engenharia e critérios de aceite; **não atesta que cada pipeline atual já cumpre GPU First**. O `main` remoto documenta releases anteriores aos ajustes locais C24–C27.4. Auditar o checkout ativo antes de modificar código, evitando sobrescrever mudanças não commitadas.

## Invariantes

1. **GPU First, não GPU Only.** Priorizar GPU para operações pesadas quando houver backend compatível, suporte aos operadores, benefício relevante e qualidade equivalente. Escolher CPU para tarefas leves de interface, I/O, coordenação ou quando o processamento por GPU não trouxer ganho técnico comprovável.
2. **Preferência explícita.** Priorizar a RX 6600M. Selecionar conscientemente DirectML, Vulkan ou outro backend validado; não assumir que `device=gpu` demonstra execução acelerada.
3. **Execução verificável.** Registrar para cada etapa pesada: algoritmo, backend solicitado, dispositivo efetivo, fallback ocorrido e razão, versão do ambiente e resultado. Não declarar sucesso GPU só com base em configuração.
4. **CPU justificada e visível.** Permitir CPU por incompatibilidade operacional, precisão/estabilidade, ausência de backend GPU ou custo desproporcional. Fallbacks automáticos devem ser registrados; nunca ocultar uma troca de dispositivo. Cancelamento não deve ser confundido com fallback.
5. **Preservação do resultado.** Não degradar separação, qualidade musical, texto/timestamps, integridade de stems, mistura, formatos de exportação ou persistência para obter aceleração.
6. **Isolamento.** Avaliar novas combinações de PyTorch/DirectML/ONNX em ambientes isolados. Não atualizar o ambiente produtivo do WhisperX ou Demucs só para testar uma hipótese.
7. **Segurança e privacidade.** Logs de dispositivo/falha não devem incluir letras transcritas, conteúdo musical, credenciais ou caminhos desnecessários; o diagnóstico de workers precisa sobreviver a falhas sem interferir no encerramento de processos.

## Inventário inicial — classificar, não reescrever

Estado baseado na documentação do `main` e em diagnósticos locais comunicados em 15/11/2026. Verificar o código e a execução do checkout ativo antes de promover qualquer item a "validado".

| Processo | Rota documentada/observada | Classificação inicial | Próximo passo permitido |
| --- | --- | --- | --- |
| Demucs, separação principal | DirectML para camadas reais; certas operações complexas/FFT em CPU | Misto, com exceção CPU documentada | Reusar evidência existente; medir novamente apenas se o backend mudar |
| DrumSep | DirectML prioritário; fallback CPU sinalizado | GPU First documentado | Confirmar sinalização do dispositivo; não repetir extrações previamente aceitas |
| Voz principal/apoio | ONNX Runtime CPU no pacote documentado | Exceção candidata a otimização | Investigar DirectML em ambiente isolado antes de migrar |
| SAM Audio | Ambiente AMD opcional | GPU prevista, verificação por configuração | Validar somente se este módulo for alterado |
| Acordes LV-Chordia | CPU experimental, pacote opcional | Exceção candidata a otimização | Estudar compatibilidade antes de alterar |
| Karaokê: reconhecimento | whisper.cpp Vulkan, Large v3 | GPU solicitada; confirmar dispositivo efetivo por execução | Reutilizar log de Vulkan já válido ou teste focal se houver mudança |
| Karaokê: alinhamento | No checkout local C24–C27.4, WhisperX moderno com torch/torchaudio `+cpu` | Exceção atual, ainda sem justificativa final | Investigar GPU sem alterar ambiente estável |
| BPM, beat grid, seções, tonalidade e demais análises | Backend variável/não totalmente auditado | Não verificado | Inventariar por inspeção e logs, sem executar a biblioteca inteira |
| Mixagem, efeitos, resampling e exportação | Dependem da operação e bibliotecas | Não verificado | Identificar apenas trechos realmente custosos antes de buscar aceleração |
| UI, coordenação, armazenamento e operações leves | CPU por natureza da tarefa | Não se aplica a exigência de GPU | Não criar testes GPU artificiais |

## Protocolo de validação finita

**Regra: um ciclo focado por alteração técnica, sem reabrir o QA inteiro.**

### Porta 1 — Auditoria estática (sem rodar áudio)
- Identificar os pontos de seleção de dispositivo e fallback dos módulos prioritários.
- Registrar `GPU confirmada`, `CPU justificada`, `a investigar` ou `não aplicável`, citando arquivo/log.
- Não instalar, trocar versão, reprocessar música nem alterar modelos nesta porta.
- **Saída:** matriz de cobertura e lista curta de exceções priorizadas.

### Porta 2 — Mudança isolada (somente onde houver justificativa)
- Abrir **uma** hipótese de otimização por módulo; preservar ambiente atual e realizar backup.
- Rodar teste sintético/curto apenas do módulo alterado, verificando dispositivo real, tempo, falhas e integridade.
- Comparar resultado com baseline existente; para mudanças que alteram áudio/timestamps, comparar saída e realizar **uma** escuta/inspeção humana focal.
- Se inviável ou regressivo: documentar exceção CPU, encerrar a hipótese e manter comportamento anterior — **não** iniciar tentativas ilimitadas.

### Porta 3 — Aceite focal
- Executar testes automatizados diretamente relacionados ao arquivo/serviço alterado e `git diff --check`.
- Uma verificação funcional do comportamento afetado quando a UI ou o pipeline mudar.
- Não repetir importação, extração completa, Karaokê de música inteira, exportação ou regressão global se não foram alterados.
- **Saída:** resultado `PASS`, `EXCEÇÃO DOCUMENTADA` ou `BLOQUEADO`, com evidência.

### Regra de parada
- Uma passagem de cada porta por hipótese. Se a Porta 2 falhar, corrigir no próprio módulo e repetir somente o teste que falhou; após persistência do problema, registrar como bloqueio e voltar ao backend conhecido, sem abrir novos ciclos automaticamente.
- Nada de mover critérios de aceite depois de testes aprovados.
- QA completo fica reservado para **release/empacotamento** ou mudança transversal comprovada, não para cada ajuste de dispositivo.
- Não considerar execução em CPU um defeito por si só; o defeito é uso injustificado, fallback oculto ou perda de desempenho/qualidade evitável.

## Falha de Karaokê de 15/11/2026

Job `2e2c72eee977`: o log do backend registrou `WhisperGPU/WhisperX worker exited with code 2`. O código **não identifica a causa**. O diagnóstico dos pacotes locais mostrou `torch 2.8.0+cpu`, `torchaudio 2.8.0+cpu`, `whisperx 3.8.6`, sem demonstrar relação causal com esse erro. A correção da mensagem visual C27.4C foi testada em âmbito focal; o worker continua pendente de diagnóstico interno.

Prioridade imediata separada da auditoria global: preservar falhas técnicas do worker de maneira segura e limitada, corrigir a causa confirmada e só então avaliar aceleração do alinhador. Não reinstalar ferramentas ou repetir processamento longo antes de obter evidência.

## Checklist para fechamento

- [ ] Inventário de dispositivo por etapa conferido no checkout ativo.
- [ ] Exceções CPU classificadas e justificadas.
- [ ] Fallbacks de processamento pesado identificáveis no log/diagnóstico.
- [ ] Cada mudança executou apenas seu QA focal; escuta comparativa somente se a saída musical foi afetada.
- [ ] Nenhuma alteração da biblioteca, jobs, stems ou ambientes de produção por auditoria.
- [ ] Política integrada após revisão ao fluxo/documentação canônicos, sem conflito com alterações locais.
