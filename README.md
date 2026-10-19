# N3LX_Stem

Separação local de músicas em até **15 pistas alinhadas**, com bateria detalhada, voz principal e backing vocals. Derivado de [StemDeck](https://github.com/stemdeckapp/stemdeck), com adaptações para Windows e AMD Radeon RX 6600M via DirectML.

## Usar no Windows

1. Instale **Python 3.12 de 64 bits**, com o inicializador `py`, **Node.js 22.12 ou superior** (com npm), **Git** e **FFmpeg/FFprobe** disponíveis no PATH. Mantenha o driver AMD atualizado.
2. Clone este repositório em uma pasta com permissão de escrita:

   ```powershell
   git clone https://github.com/nelsonseccofilho/N3LX_Stem.git
   cd N3LX_Stem
   .\Setup-N3LX_Stem.cmd
   ```

3. Abra **Start-N3LX_Stem.cmd**, carregue seu áudio e clique em **Extrair stems**. Depois exporte as pistas em ZIP. Para encerrar o servidor e seus processos, use **Stop-N3LX_Stem.cmd**.

O atalho abre uma janela própria do **N3LX_Stem**, sem abas ou barra de endereço. O aplicativo usa Electron, instalado separadamente dos modelos e do worker AMD. O endereço do serviço local continua sendo `http://127.0.0.1:8000`. A primeira instalação baixa dependências e modelos e pode demorar. O Demucs baixa seu modelo na primeira extração. A distribuição é por código-fonte e scripts; o runtime Electron é baixado na instalação. Para atualizar apenas a janela em uma instalação existente, execute `Setup-N3LX_Stem.cmd -DesktopOnly`.

## Padrão completo

- Baixo, guitarras agrupadas, piano estimado e outros instrumentos.
- Bumbo, caixa, tons, chimbal, ride e crash.
- Voz principal e backing vocals.
- Três resíduos de reconstrução, preservando o áudio restante.

O inicializador usa **Completo + Best** como padrão de uma instalação nova. Preferências já salvas continuam sendo respeitadas; altere em Configurações → Geral. A separação principal usa DirectML; os modelos especializados de voz e bateria usam CPU. Se uma etapa adicional falhar, o grupo original permanece disponível e um aviso é mostrado.

As pistas efetivas aparecem no mixer e na área de pistas prontas. O ZIP completo evita duplicar os grupos de voz e bateria que já foram subdivididos. O aplicativo mantém fila, biblioteca persistente, controles de mixagem e configurações do projeto original.

## Setlist e playlists

Abra **Setlist** na lateral para criar ou duplicar playlists e adicionar músicas já extraídas da Biblioteca. Reordene com as setas, selecione uma música e ajuste volumes, mudo, solo e transposição no mixer original. Esses ajustes ficam salvos por música dentro de cada playlist, separados da mixagem da Biblioteca. Para repetir uma configuração em toda a playlist, use **Aplicar esta mixagem a todas desta playlist**.

Use os controles originais de **contagem** e **metrônomo**; suas opções também ficam salvas por playlist. O **Play normal** inicia na música selecionada e avança automaticamente ao terminar. Pausar mantém a sequência; Parar interrompe o avanço. O loop mantém a música atual repetindo até ser desligado. Para voltar à mixagem normal da Biblioteca, use **Sair do modo playlist**.

A próxima música começa depois de carregar áudio, mixagem e mapa de batidas. A troca é automática, com um possível intervalo curto; não é reprodução sem lacunas. Se uma faixa falhar, a sequência para e informa o problema. Contagem e metrônomo dependem de um mapa de batidas disponível.

## Acompanhar a extração

O painel mostra **7 etapas** no modo Completo: preparar áudio, analisar música, separar instrumentos, separar vozes, detalhar bateria, preservar resíduos e finalizar pistas. Os três modelos informam percentuais medidos pelos trechos processados, incluindo todas as passagens configuradas. As demais partes mostram atividade e tempo decorrido, sem percentual ou previsão inventados. A contagem de etapas concluídas não é uma estimativa do tempo restante.

Fechar a janela mantém o processamento local. Você pode reabrir o aplicativo para acompanhar a fila; use **Stop-N3LX_Stem.cmd** para encerrar o serviço e os workers.

## Limites

As 15 pistas incluem **12 grupos musicais e 3 resíduos**, não 15 instrumentos isolados com perfeição. Estes modelos não isolam guitarra base, solo e violão entre si, nem todos os teclados. Piano é uma estimativa e pode conter vazamento ou ficar quase silencioso. Os efeitos, automações e duplicações L/R de uma sessão do REAPER não são aplicados automaticamente a outras músicas.

## Documentação e verificação

- [Instalação AMD, arquitetura, modelos e validação](docs/N3LX_STEM.md)
- [Créditos e documentação original](README-UPSTREAM.md)
- [Modelos e seus termos](docs/models.md)
- [Avisos de terceiros](THIRD_PARTY_NOTICES.txt)

Validado localmente no Windows com RX 6600M: separação automática de áudio real, até 15 WAVs alinhados e exportação ZIP íntegra. Os testes automatizados usam sinais sintéticos; músicas, modelos, credenciais, biblioteca e projetos pessoais não fazem parte deste repositório.

## Origem e licença

Base: StemDeck, revisão `5f9405ca68ac31b31ae07ac416141d4d1f7b5f3a`. A licença [Apache-2.0](LICENSE), os avisos e os créditos dos autores originais estão preservados. As modificações N3LX incluem DirectML isolado, separação completa automática, pistas detalhadas na interface, resíduos, exportação e scripts Windows. O nome interno do pacote Python e as chaves de armazenamento `stemdeck` permanecem por compatibilidade.

Os modelos e ferramentas externos têm seus próprios termos. Os pesos são baixados dos provedores, não redistribuídos neste Git. Use áudios que você tenha direito de processar.
