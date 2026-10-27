# rc.4 — controles compactos no mixer

O nome da pista permanece acima do PAN. A largura máxima do conjunto PAN passou a 100 px e o controle de volume a 52 px, preservando as alturas de interação e as funções existentes. As faixas e a mixagem de áudio não foram alteradas.

A verificação no Edge usou uma faixa sintética: mediu a ordem e largura dos controles, operou PAN e volume pelo teclado e testou centralização, temas claro/escuro/sistema e janela de 800 px. Não houve erros de execução da página. A primeira tentativa de QA selecionou uma pista oculta do DOM e expirou; a verificação foi corrigida para usar uma pista visível.

O trabalho mantém os limites da rc.3: o pacote Windows depende da instalação AMD existente e a aceitação musical completa continua pendente. Não houve inferência de modelo nesta revisão.
