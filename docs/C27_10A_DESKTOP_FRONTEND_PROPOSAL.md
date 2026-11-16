# C27.10A — auditoria e proposta para o front-end Desktop

Estado: proposta; nenhuma dependência, componente ou regra de layout foi alterada neste ciclo.

## Contrato de produto

O N3LX_Stem é um aplicativo Desktop-first responsivo para notebooks e monitores. A referência visual e de QA é **1920×1080**; **1440×900** é intermediária; **1366×786** é o menor viewport oficialmente suportado. As dimensões são da área útil da aplicação em pixels CSS. Redimensionamento e escala do sistema podem produzir áreas menores: os controles devem continuar acessíveis por reorganização, recolhimento ou rolagem interna apropriada. Não criar breakpoints ou modos específicos para smartphones. Preservar a aparência atual em 1920×1080 e as interações de áudio, mixer, timeline e karaokê.

## Inventário verificado

| Área | Estado atual | Consequência para a evolução |
|---|---|---|
| Entrega | `static/index.html` carrega cinco CSS diretamente; `package.json` só declara Playwright para testes, sem build de produção ou dependências de UI | Qualquer CSS compilado exige uma etapa explícita de build e validação de empacotamento Desktop; não introduzir isso silenciosamente |
| Estilos | `static/css/variables.css` já define cores, tipografia, raios, largura das colunas e movimento; `themes.css` sobrescreve light/dark | Usar esses tokens como fonte inicial do Design System; preservar nomes usados por JS e CSS legado |
| Acoplamento | `daw.css` tem 8.405 linhas, 42 blocos `@media` e 131 usos de `!important`; `index.html` tem 15 atributos `style` | Extrair por domínio e reduzir especificidade de forma gradual, com comparação visual em cada fatia; distinguir valores estáticos de valores de áudio/posição calculados em tempo real |
| Responsividade | `daw.css` já contém regras de largura e altura, inclusive regras abaixo de 700/600/480 px; `responsive.css` contém regras de telefone, mas não é carregado pela página principal | Não carregar nem ampliar `responsive.css`; auditar primeiro as regras realmente ativas. Regras antigas abaixo do mínimo podem permanecer até uma remoção comprovadamente segura, sem serem base para novos desenhos |
| Comportamento | ES modules locais em `static/js`; `footerFit.js` mede o espaço real e ajusta grupos conforme sidebar e janela | Conservar adaptações baseadas no espaço disponível quando a largura do viewport sozinha não representa o espaço do componente |
| Testes | C27.8 cobriu Studio/Karaoke em 1920×1080; há testes pontuais em outras larguras, sem matriz oficial completa nas três resoluções | A matriz Desktop é uma nova obrigação de QA, não um PASS herdado do C27.8 |

## Arquitetura proposta

1. Registrar tokens semânticos do produto (superfície, texto, borda, ação, foco, perigo, estados, espaçamento, tipografia, raios, sombras, movimento e dimensões de layout), com equivalência light/dark e mapeamento dos aliases legados. Documentar uso e contraste de cada token. Manter os valores em CSS; JS consulta tokens ou escreve apenas valores dinâmicos (medidores, cores de stems, posições e progresso).
2. Definir primitivas visuais pequenas e neutras em CSS local: botão, campo, aba, diálogo, aviso e rolagem. Comportamento e acessibilidade permanecem nos módulos JS existentes. Escopar regras por componente para que uma migração não afete mixer ou transporte por cascata.
3. Dividir `daw.css` por domínios depois de identificar dono e ordem de cascata de cada seletor. Evitar uma troca global de classes. Para cada domínio, remover somente regras comprovadamente substituídas e medir tamanho, especificidade, estado de foco, tema e geometria.
4. Projetar primeiro em 1366×786, expandir a 1440×900 e comparar com a referência 1920×1080. Usar `min-width:0`, flex/grid que encolhem, `minmax()`, limites de altura para diálogos e rolagem em painéis delimitados. Não esconder funcionalidade essencial em largura mínima. Recolhimento exige controle descobrível e acessível por teclado.

### Tailwind CSS v4 e daisyUI

Tailwind v4 pode gerar CSS estático pelo CLI sem framework JavaScript; `@theme` permite relacionar utilitários aos tokens do produto. O piloto deve compilar uma folha **isolada**, sem Preflight global e com fontes de classes explícitas, porque o reset e a varredura geral podem alterar a interface atual. A adoção depende de ganho mensurável em manutenção e tamanho final, e de funcionamento no pacote Desktop. Não migrar automaticamente todo o CSS para utilitários. [CLI oficial](https://tailwindcss.com/docs/installation/tailwind-cli), [tokens `@theme`](https://tailwindcss.com/docs/theme), [Preflight opcional](https://tailwindcss.com/docs/preflight), [fontes explícitas](https://tailwindcss.com/docs/detecting-classes-in-source-files).

daisyUI 5 é compatível com Tailwind v4, mas suas classes e temas globais precisam de comparação com os tokens e controles atuais. Avaliar apenas em amostra separada de botão, campo e diálogo; manter os temas do N3LX_Stem como autoridade. Só incorporar um componente se equivalência visual, contraste, foco, teclado e CSS gerado forem satisfatórios. [Instalação oficial](https://daisyui.com/docs/install/), [configuração de temas](https://daisyui.com/docs/config/). React e shadcn/ui não têm justificativa técnica no inventário atual: módulos locais já controlam a interface, e a proposta não exige mudança de renderizador.

## Primeiro piloto reversível — ajustes do karaokê

Escopo **futuro**, ainda não implementado: o diálogo `#karaokeSettings`, suas abas e botões comuns. É uma área delimitada por `<dialog>`, com testes C27.8 de navegação e salvamento; não altera o motor de áudio, mixer, waveform ou timeline.

1. Capturar estados de referência do diálogo fechado/aberto, abas, foco, teclado, tema claro/escuro e conteúdo com rolagem nas três resoluções. Registrar dimensões, screenshot, overflow e ordem de foco.
2. Escrever uma ficha do Design System para `Dialog`, `Tabs`, `Button` e `Field`, mapeando cada estado aos tokens existentes. Separar CSS estático de valores dinâmicos antes de mudar HTML/JS.
3. Em uma alteração isolada, acrescentar CSS escopado e migrar apenas as classes do diálogo. Se o experimento Tailwind for aprovado, gerar uma folha independente sem Preflight e importá-la só após comparação de cascata. A avaliação daisyUI fica fora da folha de produção até cumprir os mesmos critérios.
4. Reverter removendo o CSS piloto e as classes adicionadas; o markup e os módulos comportamentais originais continuam disponíveis. Nenhuma migração de dados, dependência de runtime ou alteração de contrato da API.

**Critérios para aceitar o piloto:** sem diferenças visuais inesperadas na referência 1920×1080; sem sobreposição ou overflow horizontal em 1440×900 e 1366×786; diálogo cabe ou rola internamente; nenhum controle essencial desaparece; abertura/fechamento, abas, salvamento explícito, Escape, Tab/Shift+Tab, foco visível e leitura de estados continuam operando; contrastes aprovados nos dois temas; nenhuma regressão nos testes existentes de Karaoke e Studio. Testar também janela redimensionada e escalas de 125% e 150% pelo viewport efetivo. Registrar PASS só para casos executados.

## Próximo passo antes de implementar

Criar a matriz de capturas e métricas de referência nas três resoluções, com o backend e a biblioteca preservados. Em seguida, revisar a ficha dos quatro componentes e o diff exato do piloto. Não instalar Tailwind/daisyUI, não alterar layout e não fazer nova geração de karaokê nesta fase de auditoria.
