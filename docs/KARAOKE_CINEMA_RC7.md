# Karaokê e modo cinema — rc.7

A forma de onda e a letra permanecem visíveis na tela principal. Idioma, modelo, gerar, regenerar, excluir JSON e ferramentas de edição e sincronização ficam em **Ajustes do karaokê**. O diálogo aceita Escape e devolve o foco ao botão de abertura. Se uma sincronização iniciada no diálogo continuar após fechá-lo, seu resultado ainda é acompanhado e salvo quando concluir.

**Modo cinema** usa a API de tela cheia, sempre com cores escuras locais ao painel: a preferência Claro/Escuro/Sistema continua intacta. Mostra a forma de onda e, quando há tempos, até três linhas (anterior, ativa e próxima), com destaque por palavra existente. É possível sair pelo botão ou Escape. Sem letra sincronizada, apresenta uma mensagem em vez de inventar tempos. Busca na forma de onda e reprodução seguem o transporte existente.

## Verificação

- Edge com biblioteca sintética: diálogo, seleção de idioma, Escape e foco, editor, modo cinema, três linhas ao buscar, aparência escura a partir do tema claro, saída e preservação do tema, janela de 800 px, ausência de tempos e sincronização simulada concluída após fechar o diálogo. Sem áudio pessoal nem inferência.
- Cinco arquivos de testes JavaScript focados aprovados. A primeira rodada identificou um teste antigo que esperava o painel anterior; essa expectativa foi atualizada para o diálogo e repetida junto aos testes restantes.
- No primeiro teste empacotado, Escape não fechou a tela cheia no Electron; foi adicionado tratamento explícito antes da revalidação.
- A verificação da interface é sintética e não mede a qualidade de reconhecimento, alinhamento ou sincronização musical.

O processamento de karaokê e seus limites de idioma/AMD não foram alterados. A rc.7 continua sendo uma pré-release que exige a instalação AMD e os modelos existentes.
