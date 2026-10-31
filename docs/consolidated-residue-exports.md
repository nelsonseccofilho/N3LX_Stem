# Exportação consolidada de resíduos (3 WAVs)

A opção **Exportar 3 resíduos**, dentro do menu Exportar de uma música em **modo
Completo**, gera um único ZIP com exatamente três WAVs alinhados:

| Arquivo | Conteúdo |
| --- | --- |
| `residuos_vozes.wav` | `residual_vocals`, **somente quando** esse resíduo tiver sido publicado |
| `residuos_musica.wav` | `residual_mix` (resíduo global) somado a `residual_guitar`, caso a guitarra detalhada esteja aplicada |
| `residuos_bateria.wav` | `drum_recovery + residual_drums_refined` quando **ambos** estiverem publicados; caso contrário, `residual_drums` |

Os nomes dos arquivos recebem o prefixo do título da música, quando disponível.

## Regras importantes

- **Sem duplicação de bateria:** `residual_drums` é o resíduo original que a
  recuperação refinada decompõe. Nunca somar `residual_drums` com
  `drum_recovery` ou `residual_drums_refined`.
- **O resíduo global não é uma separação de instrumentos:** `residual_mix`
  representa a diferença entre o áudio original e os seis stems básicos. Pode
  conter vazamentos de bateria ou de voz. Ele é destinado à categoria Música
  como contêiner abrangente de sobras, **não** como garantia de isolamento
  perfeito de instrumentos. Para isso seria necessário executar um novo modelo.
- **Vozes:** uma separação comum não cria automaticamente `residual_vocals`.
  Quando um dos três grupos não possui resíduos publicados, o WAV correspondente
  é **silencioso** e mantém a duração, o número de canais e o sample rate.
  Não criamos nem inferimos uma voz residual inexistente.
- **Sem clipping:** WAV IEEE FLOAT conserva amostras finitas com picos acima
  de 0 dBFS, inclusive a soma de dois resíduos. Em editores que convertem para
  PCM, ajuste o ganho antes da conversão para evitar clipping.
- **Arquivos originais intactos:** esta opção só lê WAVs publicados e cria um
  ZIP temporário, descartado após download. Não altera os stems existentes,
  o manifesto `studio.json`, mixagens, playlists ou a Biblioteca.
- **Apenas modo completo:** exige uma extração `done` com manifesto
  `studio.json` publicado. Se não houver resíduos publicados, retorna erro
  explicativo em vez de gerar três arquivos sem conteúdo por engano.

Os três WAVs representam apenas **resíduos**. Os stems principais (voz, bateria,
baixo, guitarra, piano etc.) continuam no fluxo normal de exportação.
