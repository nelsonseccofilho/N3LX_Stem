# N3LX_Stem: instalação e alterações

> Há um [pacote Windows de atualização rc.2](https://github.com/nelsonseccofilho/N3LX_Stem/releases/tag/v0.21.0-rc.2), que usa uma instalação AMD existente. Consulte o [README](../README.md#atualizar-uma-instalação-existente) para baixar e abrir o executável. A instalação limpa em outro computador continua pendente de validação.

## Ambientes

- Aplicação: Python 3.12, dependências em `uv.lock`, Torch 2.6.
- Worker AMD: `.venv-directml`, Torch 2.4.1, DirectML 0.2.5.dev240914, dependências em `scripts/requirements-directml.txt`.
- FFT e operações complexas ficam na CPU; as camadas reais da rede HTDemucs usam DirectML. Esta adaptação foi validada com RX 6600M, sem prometer suporte a toda GPU AMD.
- `Start-N3LX_Stem.cmd` usa caminhos relativos, biblioteca em `data`, servidor restrito ao endereço local e log/PID em `data/logs`. Não reinstala dependências a cada abertura.
- Janela desktop: Electron 44.3.0 em `desktop-app`, Node.js 22.12+ para instalar, perfil local em `data/desktop`. Não depende do N3LX_Voice nem do navegador padrão. O atalho do menu Iniciar abre diretamente esta janela e o aplicativo prepara o servidor quando necessário.
- Para outro adaptador já compatível, execute `scripts/Start-N3LX_Stem.ps1 -Adapter 'nome do adaptador'`. Para outra porta, use `-Port 8001`.

`Setup-N3LX_Stem.cmd` instala a aplicação pelo lock e o worker pelos pins, verifica FFmpeg/FFprobe e baixa os modelos especializados. `-VerifyOnly` verifica os ambientes existentes sem instalar. `-SkipDependencies` mantém os ambientes existentes e permite preparar os modelos. A instalação limpa ainda precisa de validação em outra máquina; a verificação local reutilizou os ambientes funcionais existentes.

O nome interno do pacote, variáveis `STEMDECK_*`, chaves do navegador e o campo `name` de `/api/health` continuam compatíveis. A API também informa `product: N3LX_Stem`. Os scripts antigos Start-StemDeck-AMD/Stop-StemDeck são atalhos compatíveis para os novos scripts públicos. A pasta local não precisa ser renomeada.

## Modelos

| Etapa | Modelo | Dispositivo validado |
| --- | --- | --- |
| Seis grupos | Demucs `htdemucs_6s` | RX 6600M / DirectML |
| Voz principal e apoio | `UVR_MDXNET_KARA_2.onnx` | CPU / ONNX |
| Seis peças da bateria | `MDX23C-DrumSep-aufr33-jarredou.ckpt` | DirectML quando configurado; CPU como alternativa sinalizada |
| Transcrição do karaokê | Whisper Large v3 / Medium, via whisper.cpp | Vulkan; teste curto do Large v3 na RX 6600M |

DrumSep é dos autores aufr33 e jarredou; a configuração e os pesos vêm do catálogo público de audio-separator. Consulte os termos e a ficha do modelo na origem antes de outros usos. Os pesos não estão incluídos neste repositório e a licença do aplicativo não altera os termos deles. A rota de bateria tenta o worker DirectML quando configurado e pode recorrer à CPU com aviso; veja [drumsep-amd.md](drumsep-amd.md).

## Fluxo e integridade

O modo Completo é capturado ao entrar na fila, força os seis grupos base e executa as passagens especializadas. A interface mostra a etapa extra em andamento, sem um percentual final artificial. Cancelamento interrompe os workers; falhas opcionais preservam o grupo original. Pistas detalhadas são alinhadas ao grupo pai; resíduos usam WAV float para evitar clipping. A exportação usa somente as pistas ativas e mantém nomes legíveis. Bateria e resíduos percussivos não recebem transposição tonal. O resíduo tonal da separação pode ser transposto.

O layout `studio.json` também permite carregar pistas renderizadas externamente e indicar nomes e percussão. A renderização de uma sessão REAPER continua sendo uma preparação externa específica de cada projeto; o aplicativo não interpreta automaticamente plugins ou arquivos RPP.

## Validação local

Teste musical de 12 segundos: 15 pistas, estéreo, 44.1 kHz, 529200 quadros, sem avisos, DirectML na etapa principal. Soma das pistas com erro máximo 0.0 contra a referência decodificada nesse teste, ZIP com 15 entradas e integridade aprovada. Isso demonstra alinhamento e preservação, não isolamento perfeito. Áudio e dados da sessão permanecem privados no computador.

Testes: `python -m pytest tests/test_directml_local.py tests/test_studio_local.py tests/test_complete_multitrack_local.py tests/test_processing_progress.py tests/test_ui_store.py`; frontend: `node tests/js/studio-lanes.test.mjs`. Testes gerais herdados também podem ser executados, mas não equivalem a validação de hardware.

## Distribuição

A [pré-release rc.2](https://github.com/nelsonseccofilho/N3LX_Stem/releases/tag/v0.21.0-rc.2) contém o executável Electron e o código da aplicação em um ZIP de atualização. O pacote exige os ambientes AMD, FFmpeg, ferramentas e pesos já instalados. Extraia-o em uma pasta nova, encerre a instância anterior e selecione a instalação existente na primeira abertura. O pacote preserva a biblioteca externa e usa seu próprio perfil de interface. Não é feita substituição automática de um checkout com alterações locais.

O fluxo por código-fonte continua disponível. Shell Tauri, Docker e empacotamento herdados permanecem para referência, sem validação dos novos recursos nesses formatos. Atualizações binárias automáticas continuam desativadas para preservar o runtime AMD. O procedimento atual usa [validação local reproduzível](LOCAL_RELEASE_VALIDATION.md); o workflow N3LX hospedado é opcional e manual. A evidência de testes locais não é apresentada como execução bem-sucedida do CI hospedado.


## Progresso e continuidade

O plano de etapas é salvo por extração; trabalhos novos e históricos podem ter planos diferentes. A fila e a API do trabalho expõem `processing` com etapa atual, total, estados, timestamps e fração medida quando disponível. Os contadores vêm dos iteradores dos modelos: Demucs considera modelos e shifts, Karaoke considera as duas passagens MDX, DrumSep conta seus batches. O percentual representa o processamento do modelo; leitura e gravação das pistas podem continuar sem percentual. Falhas opcionais mantêm aviso na etapa e preservam o grupo original.

A janela e o navegador compartilham preferências próprias do aplicativo em `data/ui-store.json`, incluindo organização, lixeira e mixagens. Credenciais e perfis do navegador não são copiados. Para migrar explicitamente a organização de uma sessão antiga do navegador, abra nela `http://127.0.0.1:8000/?migrate-ui=1` uma vez e reabra o aplicativo. O parâmetro desaparece ao terminar; preferências anteriores do servidor recebem uma cópia de segurança. Somente chaves permitidas do N3LX_Stem são lidas e o destino é o servidor local.

A extração de teste de 12 segundos foi concluída após a mudança, com os sete estados, contadores intermediários nos três modelos, DirectML sem fallback, 15 pistas alinhadas, erro máximo de reconstrução 0.0 e ZIP íntegro. Isso não é um benchmark de tempo nem prova de isolamento perfeito dos instrumentos.

## Interface atual

A rc.2 oferece temas Claro/Escuro/Sistema, PAN por pista, Restaurar na lixeira, confirmação de exclusão e controles para excluir/regenerar karaokê. Large v3 é o modelo padrão de transcrição; Medium é uma escolha explícita. Os detalhes e limites dessa revisão estão em [UX_UI_RC2_QA.md](UX_UI_RC2_QA.md).
