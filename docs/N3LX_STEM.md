# N3LX_Stem: instalação e alterações

## Ambientes

- Aplicação: Python 3.12, dependências em `uv.lock`, Torch 2.6.
- Worker AMD: `.venv-directml`, Torch 2.4.1, DirectML 0.2.5.dev240914, dependências em `scripts/requirements-directml.txt`.
- FFT e operações complexas ficam na CPU; as camadas reais da rede HTDemucs usam DirectML. Esta adaptação foi validada com RX 6600M, sem prometer suporte a toda GPU AMD.
- `Start-N3LX_Stem.cmd` usa caminhos relativos, biblioteca em `data`, servidor restrito ao endereço local e log/PID em `data/logs`. Não reinstala dependências a cada abertura.
- Para outro adaptador já compatível, execute `scripts/Start-N3LX_Stem.ps1 -Adapter 'nome do adaptador'`. Para outra porta, use `-Port 8001`.

`Setup-N3LX_Stem.cmd` instala a aplicação pelo lock e o worker pelos pins, verifica FFmpeg/FFprobe e baixa os modelos especializados. `-VerifyOnly` verifica os ambientes existentes sem instalar. `-SkipDependencies` mantém os ambientes existentes e permite preparar os modelos. A instalação limpa ainda precisa de validação em outra máquina; a verificação local reutilizou os ambientes funcionais existentes.

O nome interno do pacote, variáveis `STEMDECK_*`, chaves do navegador e o campo `name` de `/api/health` continuam compatíveis. A API também informa `product: N3LX_Stem`. Os scripts antigos Start-StemDeck-AMD/Stop-StemDeck são atalhos compatíveis para os novos scripts públicos. A pasta local não precisa ser renomeada.

## Modelos

| Etapa | Modelo | Dispositivo validado |
| --- | --- | --- |
| Seis grupos | Demucs `htdemucs_6s` | RX 6600M / DirectML |
| Voz principal e apoio | `UVR_MDXNET_KARA_2.onnx` | CPU / ONNX |
| Seis peças da bateria | `MDX23C-DrumSep-aufr33-jarredou.ckpt` | CPU / PyTorch |

DrumSep é dos autores aufr33 e jarredou; a configuração e os pesos vêm do catálogo público de audio-separator. Consulte os termos e a ficha do modelo na origem antes de outros usos. Os pesos não estão incluídos neste repositório e a licença do aplicativo não altera os termos deles. A bateria detalhada não usa DirectML nesta instalação.

## Fluxo e integridade

O modo Completo é capturado ao entrar na fila, força os seis grupos base e executa as passagens especializadas. A interface mostra a etapa extra em andamento, sem um percentual final artificial. Cancelamento interrompe os workers; falhas opcionais preservam o grupo original. Pistas detalhadas são alinhadas ao grupo pai; resíduos usam WAV float para evitar clipping. A exportação usa somente as pistas ativas e mantém nomes legíveis. Bateria e resíduos de mistura/bateria não recebem transposição tonal.

O layout `studio.json` também permite carregar pistas renderizadas externamente e indicar nomes e percussão. A renderização de uma sessão REAPER continua sendo uma preparação externa específica de cada projeto; o aplicativo não interpreta automaticamente plugins ou arquivos RPP.

## Validação local

Teste musical de 12 segundos: 15 pistas, estéreo, 44.1 kHz, 529200 quadros, sem avisos, DirectML na etapa principal. Soma das pistas com erro máximo 0.0 contra a referência decodificada nesse teste, ZIP com 15 entradas e integridade aprovada. Isso demonstra alinhamento e preservação, não isolamento perfeito. Áudio e dados da sessão permanecem privados no computador.

Testes: `python -m pytest tests/test_directml_local.py tests/test_studio_local.py tests/test_complete_multitrack_local.py`; frontend: `node tests/js/studio-lanes.test.mjs`. Testes gerais herdados também podem ser executados, mas não equivalem a validação de hardware.

## Distribuição

Esta versão é distribuída como código-fonte para o fluxo Windows acima. Scripts, shells nativos, Docker e empacotamento herdados permanecem para referência e evolução, sem validação dos novos recursos nesses formatos. Os workflows herdados só executam no repositório original; o workflow N3LX executa verificações focadas sem publicar binários ou containers. Atualizações binárias automáticas foram desativadas para não substituir o worker AMD por uma distribuição incompatível. Para atualizar o código, revise as alterações locais antes de usar Git.
