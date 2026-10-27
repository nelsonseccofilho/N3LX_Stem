# DrumSep na AMD Radeon RX 6600M

Estado em 20/10/2026: o checkpoint já instalado
`MDX23C-DrumSep-aufr33-jarredou.ckpt` executou uma música inteira em DirectML.
Não houve instalação de outro modelo nem alteração de pacotes de terceiros.

A biblioteca audio-separator evita MDXC em DirectML por limitações do alocador
observadas em seu ambiente de testes ([documentação oficial](https://github.com/nomadkaraoke/python-audio-separator#readme)).
Isso justificava a antiga rota CPU; não prova que a RX 6600M falha da mesma forma.
O N3LX_Stem agora usa um worker isolado e carrega a arquitetura instalada com os
mesmos pesos, estritamente. Não força globalmente a política de outro pacote.

## Execução

O modo Completo segue: preparar e analisar → stems principais → vozes →
guitarras (SAM) → bateria → resíduos → finalização. Os refinamentos recebem
seus respectivos stems principais; a ordem não altera a entrada dos modelos.
Jobs anteriores preservam o plano e a ordem registrados no histórico.
A base, o SAM e a bateria priorizam a GPU AMD neste ambiente. A divisão de
voz principal/backing ainda usa o ONNX Runtime CPU instalado.

- Python/Torch/DirectML já usados pelo Demucs: `STEMDECK_DIRECTML_PYTHON`.
- Adaptador: `STEMDECK_DIRECTML_ADAPTER` (neste PC, `RX 6600M`).
- Camadas neurais e parâmetros em `privateuseone`; STFT/ISTFT e acumulação de áudio
  ficam explicitamente em CPU, pois o DirectML não processa os tensores complexos.
- Grade preservada: 44,1 kHz estéreo, `dim_t=256`, batch 1, overlap 4, ordem
  `kick/snare/toms/hh/ride/crash`. Cada saída é acumulada em CPU e o resultado
  temporário da GPU é liberado antes do próximo trecho.
- No modo Completo, a preferência DirectML tenta essa rota primeiro. Se o worker
  falhar ou expirar, ele é encerrado, arquivos parciais são retirados e a bateria
  é refeita com o worker CPU anterior. Há aviso e identificação real do dispositivo.
- Cancelamento não aciona CPU: ele interrompe a extração. Se ambas as rotas
  falharem, a bateria agrupada fica preservada com aviso.
- `drum-detail.json` registra qual rota terminou. Progresso usa trechos concluídos,
  sem transformar a duração de um teste em promessa de tempo restante.

## Evidências locais

Trecho real de bateria forte, 130.560 amostras: quatro inferências consecutivas
com os mesmos pesos e entrada, comparadas diretamente à CPU. Erro máximo
`1,94e-7`, SNR `133,57 dB`. Sem avisos de fallback neural do DirectML.

Música inteira `MANTRA_2`: **116,727 s**, 44,1 kHz, estéreo, 5.147.675 amostras.
O worker AMD concluiu **161 trechos em 53,75 s**, sem OOM. As seis pistas ficaram
finitas e alinhadas. Comparadas às pistas CPU já exportadas dessa mesma música,
o erro máximo ficou entre `3,05e-5` e `3,06e-5`, compatível com a quantização PCM16
da exportação anterior. A comparação neural direta acima usa floats e não tem
essa quantização. Não se afirma ganho de velocidade contra outra música ou outro
hardware.

Relatórios ignorados pelo Git:
`.local/sam-audio/drum-gpu-strong.json`,
`.local/sam-audio/drum-full-amd/drum-device.json` e
`.local/sam-audio/drum-full-amd/cpu-comparison.json`.

O refinamento posterior escreve os seis instrumentos em PCM24 alinhado e calcula
uma sobra float a partir da bateria agrupada. A soma preserva o grupo original;
isso não é uma medida de qualidade perceptiva do isolamento de cada peça.
