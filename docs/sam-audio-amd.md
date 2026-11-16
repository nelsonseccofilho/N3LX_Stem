# SAM Audio na RX 6600M: detalhamento local de guitarras

Estado em **20/10/2026**: acesso oficial aprovado e checkpoint treinado baixado,
com SHA256 verificado. O fluxo completo de texto/áudio já executou em um trecho
musical real na RX 6600M. A validação encontrou e corrigiu uma corrupção silenciosa
de dados no DirectML. O aplicativo agora oferece o detalhamento pelo menu da
música, usando um processo isolado. Executar o modelo não comprova separação
confiável entre base, solo, violão e overdubs: as pistas são identificadas como
estimativas. No modo **Completo**, novas extrações fazem o refinamento
automaticamente. Em músicas já prontas, o menu manual mantém aplicação explícita.

## Refinamento automático no modo Completo

O fluxo tem oito etapas: preparar áudio → analisar música → separar instrumentos
→ separar vozes → detalhar bateria → detalhar guitarras → preservar resíduos →
finalizar pistas. As guitarras usam o mesmo worker AMD validado, com solo, violão,
base e uma sobra exata. O resultado completo pode chegar a 18 pistas. Os grupos
originais são mantidos para restauração; não são somados com seus refinamentos.

Esta mudança vale para novas extrações no modo Completo. A biblioteca existente
não é reprocessada. O modo Básico conserva seus seis grupos. Se o SAM não estiver
disponível ou falhar, a música termina com a guitarra agrupada e um aviso. Falhas
parciais não viram pistas ativas. Cancelamento encerra o worker e interrompe a
extração, sem ser convertido em aviso de sucesso.

Validação incremental real: uma cópia de 24 s de `MANTRA_2`, começando pelos seis
grupos existentes, percorreu vozes → bateria AMD → guitarras AMD → resíduos, sem
avisos, e produziu 18 pistas estéreo de 1.058.400 amostras a 44,1 kHz. A soma teve
erro máximo `2,16e-8` contra a referência decodificada na mesma grade. A bateria
levou 16,657 s e o SAM 224,546 s nesse teste. O áudio de origem era 48 kHz; a
comparação usa a referência reamostrada pelo mesmo FFmpeg da extração, para não
comparar vetores com taxas diferentes. A biblioteca real não foi modificada.
Relatório em `.local/automatic-refinement-24s/validation.json`.

O plano de etapas é salvo por extração: registros antigos continuam mostrando as
sete etapas que efetivamente executaram. O progresso identifica o dispositivo
da etapa atual, sem presumir que detalhamento de bateria sempre significa CPU.

A bateria também possui uma rota AMD própria, documentada em
[DrumSep na RX 6600M](drumsep-amd.md). A CPU continua como alternativa explícita
se a tentativa AMD falhar. Modelos não disputam a GPU: os refinamentos executam
em sequência e o worker persistente de Demucs é liberado antes deles.

## Uso no aplicativo

1. Abra uma música pronta que contenha `guitar.wav`.
2. Em **Tocando agora → ⋯ → Detalhar guitarras**, escolha solo, violão e/ou base.
3. Gere as estimativas. A janela pode ser fechada: o processamento continua e
   pode ser consultado novamente pelo mesmo menu.
4. **Aplicar ao mixer** troca a guitarra agrupada pelas estimativas e pela pista
   **Outras guitarras / sobras**. Os controles normais continuam disponíveis.
5. **Voltar às guitarras originais** restaura o layout anterior. A guitarra
   original nunca é sobrescrita. A geração de outro resultado exige restaurá-la.

Cada parte é estimada **sequencialmente**, sobre a sobra da etapa anterior, na
ordem solo → violão → base. Isso evita somar três previsões independentes do mesmo
sinal. Não garante isolamento de papéis musicais nem recupera sessões de gravação
ou overdubs originais. A avaliação perceptiva ainda depende de audição musical.

Músicas inteiras usam janelas de 12 s com sobreposição de 2 s e soma ponderada.
Em falta de memória, a etapa reinicia com janelas de 6 s e depois 3 s. Não existe
fallback neural automático para CPU. T5, codec e difusão usam DirectML; FFT,
resampling, mistura estéreo e movimentação entre etapas usam CPU explicitamente.
As duas saídas do decoder são processadas serialmente para caber na RX 6600M.

O progresso informa etapa, trecho, trechos concluídos e tempo decorrido. Não
estima duração restante. Cancelamento só se conclui após a saída do processo.
SAM manual e a extração normal compartilham a fila de execução pesada para não
disputar a GPU. O SAM automático já executa dentro dessa fila e não cria uma
segunda tarefa que esperaria pela própria extração. Falhas não aplicam resultados
parciais ao mixer.

As novas pistas herdam os controles da guitarra na mixagem atual. Outras
playlists herdam sua própria configuração de guitarra quando ainda não possuem
ajustes específicos para as novas pistas. Ajustes existentes por pista têm
prioridade. Exportações usam as pistas ativas e impedem somar guitarra agrupada
com suas estimativas.

Validação musical real em 20/10/2026:

- `MANTRA_2`, guitarra inteira de 116,727 s: 12 trechos, solo + sobra, **251 s**;
  estéreo, 44,1 kHz, 5.147.675 amostras; erro máximo de reconstrução `2,98e-8`.
- Trecho de 24 s: solo + violão + base + sobra, 9 inferências, **174,188 s**;
  erro máximo `2,91e-8`, preservando taxa, duração e canais.

Os tempos são medições locais, não promessa de velocidade para outras músicas.
Relatórios ficam em `.local/sam-audio/integration/`, fora do Git. Resultados do
aplicativo ficam em `data/jobs/<id>/guitar-details/<run-id>/`; o manifesto
`guitar-detail.json` distingue resultado concluído de resultado aplicado.

## Isolamento e fontes

- Código oficial clonado em `D:\git\sam-audio-amd`, revisão
  `bb4c6999d2677c7402360e426afc01ddfad6dce0`.
- DACVAE oficial: `414c20785fc3a28373073ea8ef7a1316eeeaca6e`.
- Worker de pesquisa: `D:\git\sam-audio-amd\.venv`.
- Teste ONNX separado: `D:\git\sam-audio-amd\.venv-onnx`.
- Ambos reutilizam o Torch/DirectML existente por um `.pth` de leitura. Pacotes
  adicionais são instalados somente nos ambientes do laboratório. As dependências
  do codec exigem Protobuf antigo; o ONNX exige outro, por isso ficam separados.
- Torch 2.4.1, torch-directml 0.2.5.dev240914, Transformers 4.55.4,
  torchdiffeq 0.2.5; ONNX 1.17.0 e ONNX Runtime DirectML 1.24.2.
- As duas verificações `pip check` passaram. Listas dos pacotes locais ficam em
  `amd_lab/requirements-installed.txt` e `amd_lab/requirements-onnx-installed.txt`.

As dependências principais, os modelos da separação Completo e os atalhos são
preservados. Os pesos SAM ficam no laboratório. O aplicativo inicia somente o
worker isolado, sem instalar pacotes ou baixar pesos ao abrir o menu.
`STEMDECK_SAM_SOURCE` e `STEMDECK_SAM_PYTHON` permitem informar outro checkout ou
Python; o padrão é o checkout irmão `sam-audio-amd` e seu `.venv`.

## Primeira fase: compatibilidade com pesos aleatórios

Os testes usam **pesos aleatórios**, não checkpoints treinados. DiT e T5 têm
dimensões reduzidas. O codec mantém o decoder de 1536 canais necessário às suas
camadas internas, com encoder/latentes reduzidos e áudio sintético de 0,12 s.
Portanto estes resultados não medem qualidade musical, memória do SAM completo,
tempo de uma música, nem capacidade de separar base/solo/violão.

| Componente | Resultado |
| --- | --- |
| DiT oficial, FP32 e FP16, com/sem máscara | 4 casos passaram na RX 6600M; erro máximo FP32 até `8,35e-7`, FP16 até `0,00359`; nenhum aviso de fallback |
| T5 reduzido, FP32 e FP16 | 2 casos passaram; erro máximo `8,35e-7` e `0,00577`; após adaptação, nenhum aviso de fallback |
| Integrador midpoint usado pelo SAM | 2 casos passaram em DirectML; erro máximo FP32 `2,39e-7`, FP16 `0,00303` |
| Codec com LSTM explícita | Antes da correção de padding, FP32 falhou (`0,00111`). Após a correção: FP32 passou com erro máximo `1,35e-7`; FP16 passou com `9,88e-5`. Sem avisos de fallback |
| LSTM 512 canais/2 camadas via ONNX | Perfil registrou apenas `DmlExecutionProvider`; erro máximo `1,50e-7` nos testes de saída e estados |
| Regressões matemáticas locais | 38 testes passaram: RoPE, LSTM/estados/pesos, limites de T5, ELU, materialização de weight norm e convoluções unitárias com/sem bias, grupos e entradas com offset |

No teste ONNX de sequência 960, uma chamada levou aproximadamente **2,11 s**;
blocos causais de 32 preservando estados levaram **0,227 s**, incluindo cópias pelo
host. A referência CPU levou **0,159 s**. O ganho de cerca de 9x compara duas
execuções GPU desse teste, não representa ganho do SAM completo sobre CPU.
Essa alternativa ainda **não está ligada ao codec**: é uma prova isolada.

Relatórios JSON e gráficos ONNX aleatórios ficam em `.local/sam-audio/`, ignorados
pelo Git. Os relatórios dessa primeira fase identificam `checkpoint_loaded: false`.
Os relatórios posteriores com pesos treinados identificam `checkpoint_loaded: true`.

## Segunda fase: pesos oficiais e áudio real

Pesos baixados somente das fontes oficiais, com o login local aprovado:

- SAM small: revisão `20b65f56888142eebe7c37448c6f6b3b32600e9b`,
  5.100.547.943 bytes,
  SHA256 `8c44fda9821fd9f2ec8977304e3c0f55290d9eacb6bbf25b4b8fb1f69c2a8c06`.
- T5 base: `google-t5/t5-base`, revisão
  `a9723ea7f1b39c1eae772870f3b547bf6ef7e6c1`, 891.646.390 bytes,
  SHA256 `a90903540cc02cbeb7ff9f823f1a80eb778c7e22426a0e620b01c77a5ec8f5b4`.

`sam_audio_text_loader.py` carrega as classes oficiais sem construir os encoders
opcionais de vídeo, o preditor automático de spans ou os rankers. Confere todos os
564 tensores necessários do checkpoint; 601 tensores opcionais são excluídos.
T5 é carregado separadamente, como no upstream. São 713.526.533 parâmetros no
worker de texto/áudio. Não há substituto neural ou pesos aleatórios na inferência.

O primeiro teste completo usou três segundos de uma pista de guitarra real,
48 kHz, downmix mono, prompt em inglês para guitarra solo, um candidato e o
integrador midpoint padrão (16 passos/32 avaliações). Texto, codec e difusão
foram enviados à GPU por etapas; cópias e organização entre etapas usam CPU.
Sem rankers e sem predição automática de spans. Todos os módulos neurais foram
posicionados na GPU e não houve avisos de fallback; os únicos avisos foram de
depreciação.

### Falha silenciosa encontrada e correção

Na versão local do DirectML, `F.pad(x, (0, 0))` não preservou os dados de um tensor
`[1, 16, 24960]`: o teste isolado mostrou erro máximo de aproximadamente 4,82.
Essa chamada aparece nas convoluções causais unitárias do ramo de watermark do
decoder, apesar de não precisar adicionar amostras. Não havia aviso de fallback
ou exceção: um teste que verifica apenas execução/valores finitos não detecta isso.

Hooks compararam entradas, pesos, bias e saídas das camadas. A entrada da primeira
camada divergente tinha erro próximo de `1,52e-6`, e os pesos/bias eram idênticos.
O contorno preserva o ramo de watermark e a convolução na GPU, executando a
convolução unitária diretamente, sem o padding nulo. Atua somente em instâncias
compatíveis do codec/transformer; não modifica Torch ou o código upstream em disco.

Comparação do codec treinado, mesmo trecho de três segundos e mensagem fixa:

| Medida | Antes | Depois |
| --- | --- | --- |
| Decoder, erro máximo contra CPU | `0,2834` | `3,09e-6` |
| Decoder, RMSE contra CPU | `0,0930` | `3,88e-7` |
| Decoder, SNR numérica contra CPU | `3,75 dB` | `111,35 dB` |
| Encoder, erro máximo contra CPU | `7,63e-5` | `7,63e-5` |
| Encoder, SNR numérica contra CPU | `107,23 dB` | `107,23 dB` |

A adaptação em CPU preservou o decoder com erro máximo de `5,97e-8`.
O T5 treinado também foi comparado: erro máximo CPU/AMD `1,85e-6`, FP32.
Essas métricas verificam fidelidade numérica, não qualidade de separação musical.
Os testes completos anteriores à correção geraram áudio divergente e **não são
resultados aprovados**. Foram preservados como evidência de diagnóstico.

### Repetição completa após a correção

O fluxo completo, FP32, concluiu novamente em **47,98 s**, dos quais 19,30 s foram
carregamento. Etapas com sincronização/cópias incluídas: texto 2,35 s, encoder
4,21 s, difusão 3,28 s, decoder 5,98 s. Não extrapolar esses tempos para uma música
inteira: há custos fixos e consumo de memória dependente da duração.

Uma execução CPU foi usada **somente como referência numérica**, com o mesmo
checkpoint, prompt, seed e parâmetros de integração. Comparação dos WAVs FP32:

| Saída | Erro máximo AMD/CPU | RMSE | SNR numérica |
| --- | --- | --- | --- |
| Target | `4,08e-6` | `1,74e-7` | `105,33 dB` |
| Residual gerado pelo modelo | `1,17e-4` | `3,22e-6` | `92,19 dB` |
| Sobra exata (entrada menos target) | `4,08e-6` | `1,74e-7` | `118,26 dB` |

As saídas estão alinhadas em 144.000 amostras/48 kHz. A reconstrução com a sobra
exata tem erro máximo de `2,99e-8`. O residual gerado teve um pico que excedeu o
limite absoluto estrito de `1e-4`: o relatório da comparação mantém `ok: false`
para esse critério; não foi relaxado depois da medição. Essas métricas não confirmam
ausência de artefatos ou qualidade musical. É necessária audição e comparação
de trechos com base/solo presentes antes de apresentar multitracks como validadas.

Relatórios locais: `real-guitar-3s-fixed/report.json`,
`real-guitar-3s-cpu/report.json`, `real-guitar-3s-comparison.json`,
`trained-codec-3s-fixed/report.json` e `codec-after-padding-fix.json` dentro de
`.local/sam-audio/`. Não são enviados ao Git junto com o áudio do usuário.

## Terceira fase: 12 segundos, limite de memória e estéreo

O teste foi ampliado de 3 para 12 segundos no mesmo arquivo de guitarra da
biblioteca, entre 00:30 e 00:42. A primeira tentativa FP32 concluiu encoder e
difusão, mas falhou no decoder com falta de memória de vídeo ao decodificar
target e residual juntos. O erro foi preservado em `guitar-12s-lead/report.json`.
Não houve migração para CPU.

A decodificação agora processa cada membro do batch separadamente e transfere
cada saída concluída para CPU antes de iniciar a outra. Isso reduz ativações
simultâneas sem cortar a linha do tempo ou reiniciar estados recorrentes dentro
da música. O default do probe passou para FP32, a precisão já comparada com CPU.

As três execuções seguintes concluíram na RX 6600M, com 576.000 amostras/48 kHz,
16 passos midpoint, 32 avaliações e sem avisos de fallback:

| Pedido independente | Tempo total, incluindo carregamento |
| --- | --- |
| Guitarra elétrica solo/melodia | `35,61 s` |
| Guitarras elétricas base/acompanhamento | `35,66 s` |
| Violão dedilhado/batido | `35,85 s` |

São medições de execuções isoladas e curtas, não um benchmark de música inteira.
O modelo é carregado a cada execução; não houve claim de separação em tempo real.

### Transferência para o estéreo de origem

`sam_audio_stereo.py` deriva uma máscara espectral real entre zero e um a partir
do target/residual mono do SAM. A mesma máscara é aplicada a L/R do arquivo de
guitarra original. As estimativas são reamostradas para o sample rate da origem,
e a sobra é calculada como entrada menos target estéreo. O FFT/pós-processamento
usa NumPy/SciPy em CPU; os módulos neurais do SAM continuam em DirectML.

A máscara preserva a relação de fase entre os canais em cada bin; não recria
uma imagem estéreo a partir de um mono duplicado. Os WAVs desse caso têm
529.200 amostras/44,1 kHz/2 canais. Target mais sua sobra reconstrói a origem com
erro máximo entre `1,49e-8` e `2,99e-8`. Não somar as três estimativas independentes.

Os oito testes novos verificam seleção de um componente conhecido, preservação
do pan, canais em fase oposta, canal silencioso, estimativas nulas, alinhamento
ao reamostrar e rejeição de áudio inválido/desalinhado. São testes da transferência
de sinal com componentes sintéticos conhecidos, não uma validação musical do SAM.

### Comparador local e limites dos resultados

O pacote local `Comparacao-Guitarras-Eu-sigo-so.zip`, em `.local/sam-audio/`, contém
um comparador HTML sem serviços externos, WAVs estéreo de referência e estimativas,
as sobras correspondentes, medidas de reconstrução e manifesto SHA256. Alternar
opções mantém o ponto da reprodução para comparação A/B. A biblioteca e a mixagem
do app não foram alteradas. Áudios/artefatos do usuário continuam ignorados no Git.

Os pedidos ainda produzem áudio sobreposto: a correlação das estimativas estéreo
foi `0,919` solo/base, `0,903` solo/violão e `0,756` base/violão neste trecho.
Correlação não determina sozinha a presença de instrumentos nem a qualidade do
isolamento. Não foi estabelecido por audição que esse trecho contenha as três
partes. Não foram criadas pistas rotuladas como overdubs sem evidência musical.

Os links dos arquivos, metadados e a sintaxe JavaScript do comparador foram
verificados. O navegador interno bloqueou o protocolo `file:`; não houve teste
de interação/reprodução no browser nem contorno desse bloqueio. Para ouvir,
extraia o pacote inteiro e abra `Comparar.html` no navegador do computador.

O SAM continua fora do fluxo de extração de produção. Falta conferir musicalmente
as estimativas em um trecho apropriado e validar a segmentação com overlap para
músicas inteiras antes de alterar as pistas do mixer.

## Adaptações feitas

`scripts/sam_audio_amd_compat.py` atua apenas nas instâncias/processos de teste:

- Substitui o broadcast 6-D de RoPE, que abortava o processo DirectML, por operações
  reais 4-D numericamente equivalentes.
- Usa `no_grad` nos probes: `inference_mode` falhou com
  `Cannot set version_counter for inference tensor`. O método público do SAM tem
  um decorator desse tipo e ainda precisará ser tratado no worker completo.
- Evita o fallback CPU de `clamp.Tensor_out` no T5 por mínimo/máximo na GPU,
  substituindo temporariamente apenas o namespace Torch do módulo T5.
- Materializa weight norm antes da transferência do codec e expressa ELU com
  operações reais suportadas.
- Implementa LSTM de inferência unidirecional por seus gates, sem recorrer à
  operação fundida não suportada. A equivalência em CPU do codec adaptado teve
  erro máximo `8,39e-9` no teste aleatório. A divergência grande observada com pesos
  treinados foi localizada no padding nulo, não no cálculo dos gates.
- Evita padding nulo nas convoluções unitárias, preservando pesos e watermark.

Não altera os arquivos dos pacotes instalados nem os arquivos do SAM clonado.
O loader do probe extrai somente a classe de configuração DiT oficial e carrega
suas camadas reais, evitando dependências de vídeo que não participam deste teste.
Não substitui pesos ou simula uma separação musical.

## Reproduzir

A partir da pasta do N3LX_Stem, com os ambientes locais descritos acima:

```powershell
.\.venv-directml\Scripts\python.exe scripts\sam_audio_amd_probe.py --source D:\git\sam-audio-amd --no-inference-mode --compat --report .local\sam-audio\dit-compat.json
D:\git\sam-audio-amd\.venv\Scripts\python.exe scripts\sam_audio_components_probe.py text --compat --report .local\sam-audio\text-compat.json
D:\git\sam-audio-amd\.venv\Scripts\python.exe scripts\sam_audio_components_probe.py ode --report .local\sam-audio\ode.json
D:\git\sam-audio-amd\.venv\Scripts\python.exe scripts\sam_audio_components_probe.py codec --compat --report .local\sam-audio\codec.json
D:\git\sam-audio-amd\.venv-onnx\Scripts\python.exe scripts\sam_audio_onnx_lstm_probe.py --report .local\sam-audio\onnx-lstm.json
.\.venv\Scripts\python.exe -m pytest tests\test_sam_audio_amd.py -q
```

Os modos sem `--compat` reproduzem os problemas; RoPE original pode
abortar o processo nativo, portanto execute somente o worker isolado.

## Pesos oficiais e próximos passos

`scripts/sam_audio_model_access.py` usa o login HF já existente, sem exibir tokens,
aceitar termos em nome do usuário ou procurar espelhos de um checkpoint restrito:

```powershell
D:\git\sam-audio-amd\.venv\Scripts\python.exe scripts\sam_audio_model_access.py
```

O acesso já foi aprovado. O download autorizado pode ser iniciado explicitamente:

```powershell
D:\git\sam-audio-amd\.venv\Scripts\python.exe scripts\sam_audio_model_access.py --download --destination D:\git\sam-audio-amd\models\sam-audio-small
```

O checkpoint oficial consultado tem aproximadamente **5,10 GB** e revisão
`20b65f56888142eebe7c37448c6f6b3b32600e9b`. Tamanho em disco não é uma estimativa de
VRAM. Pesos usam os termos SAM da Meta; não devem ser incorporados ao repositório.

Quando a transferência monolítica fica parada, `sam_audio_download_ranges.py`
retoma blocos autenticados de 16 MiB, confere o `Content-Range` de cada resposta e
o SHA256 oficial do arquivo completo antes de instalar. URLs assinadas/tokens não
são registrados. Não usa espelhos. Os blocos parciais verificados são reutilizados.

Para reproduzir o teste real (saída fora da biblioteca e sem alterar a música):

```powershell
D:\git\sam-audio-amd\.venv\Scripts\python.exe scripts\sam_audio_real_probe.py --input CAMINHO_DA_GUITARRA.wav --start 30 --seconds 3 --dtype float32 --output .local\sam-audio\teste-real
D:\git\sam-audio-amd\.venv\Scripts\python.exe scripts\sam_audio_codec_reference.py --input CAMINHO_DA_GUITARRA.wav --start 30 --seconds 3 --output .local\sam-audio\codec-real
D:\git\sam-audio-amd\.venv\Scripts\python.exe scripts\sam_audio_stereo.py --probe .local\sam-audio\teste-real --output .local\sam-audio\teste-estereo
```

Próximas avaliações de qualidade: ouvir trechos com solos, bases e violões
conhecidos, comparar prompts e medir vazamento entre papéis. Overdubs ainda não
estão validados como pistas independentes. A prioridade continua AMD; CPU é
referência de QA, não migração automática. No mixer entra somente a sobra exata
da partição estéreo; o residual mono do modelo serve para estimar a máscara.

Fontes: [SAM Audio](https://github.com/facebookresearch/sam-audio),
[DACVAE](https://github.com/facebookresearch/dacvae),
[checkpoint oficial](https://huggingface.co/facebook/sam-audio-small).
