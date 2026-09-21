# Cora — mascote do Concurse

Uma capivara original: caramelo, focinho creme comprido, narinas em par, duas mechas e jaqueta violeta com C branco. Esta é a primeira versão do desenho vetorial e de seu repertório de movimento. Não é uma cópia da mascote do Duolingo.

## Abrir

Abra `index.html` com duplo clique no navegador. A prévia funciona completamente offline: HTML, CSS, desenho SVG e JavaScript estão incorporados em um único arquivo, sem fontes, bibliotecas, serviços ou imagens remotas. Não depende de Node, Python ou servidor para rodar.

## Arquivos

- `cora.svg`: vetor estático, fundo transparente, 420 × 480 unidades.
- `cora-idle.svg`: respiração, piscadas, pequena inclinação da cabeça e movimento de mão.
- `cora-correct.svg`: antecipação, salto, braços, inclinação da cabeça, sombra e pequenos brilhos.
- `cora-celebrate.svg`: dois saltos, braços levantados, orelhas e confetes.
- `cora-expressions.svg`: folha com as seis expressões vetoriais.
- `index.html`: laboratório offline com movimentos, expressões, pausa e repetição.
- `build_assets.py`: fonte editável do rig, formas, cores, timings e laboratório. Execute com Python 3 para regenerar os arquivos acima; não precisa ser distribuído junto do aplicativo.

## Estados e duração

A folha conceitual `cora-character-sheet-v1.png` foi criada com o ImageGen integrado; o prompt inicial e seu refinamento estão em `cora-character-sheet-v1.prompt.txt`. Os SVGs são uma adaptação vetorial simplificada, com partes editáveis para animação.

### Adaptador React

`CoraMascot.tsx` recebe `state`, `basePath`, `replayKey`, `size` e `alt`. Copie os quatro SVGs para uma pasta pública empacotada com o aplicativo, por exemplo `public/mascots/cora/`, e importe o componente no projeto React:

```tsx
<CoraMascot state="correct" replayKey={numeroDaResposta} size={240} />
```

Incremente `replayKey` para repetir uma reação igual. `basePath` pode apontar para outro diretório local. A preferência de movimento reduzido usa a pose estática. O adaptador é decorativo por padrão (`alt=""`); forneça uma descrição apenas quando a mascote comunicar algo que o texto da tela não apresenta. Os controles de expressão e pausa pertencem ao laboratório ou à integração SVG inline.

### Movimentos

| Movimento | Duração | Comportamento |
|---|---|---|
| `idle` | 4,8 s | Respiração e piscadas em ciclo; olhar em 9,6 s. |
| `correct` | 1,6 s | Uma execução, volta à pose de repouso. |
| `celebrate` | 2,6 s | Uma execução, confetes desaparecem no fim. |

Expressões: `neutral`, `happy`, `thinking`, `surprised`, `determined`, `proud`. Acerto e comemoração começam felizes. Trocar a expressão durante um movimento não reinicia a animação nem altera seus braços ou saltos.

## Uso no aplicativo

O SVG pode ser incluído inline em React/HTML ou carregado como imagem em uma superfície que suporte animações SVG/CSS. Atributos do elemento raiz controlam o estado:

```html
<svg class="cora" data-motion="idle" data-expression="neutral" data-paused="false">…</svg>
```

Na prévia, uma API pequena já está disponível:

```js
Cora.play('correct');
Cora.setExpression('proud');
Cora.pause();
Cora.resume();
Cora.replay();
Cora.getState();
```

Em uma integração inline, reinicie um movimento removendo o atributo de movimento por um frame antes de recolocá-lo. O laboratório faz isso e acompanha o término pelo evento `animationend`. O nome `Cora` acima pertence somente ao laboratório; para usar no produto, extraia o controlador ou transforme-o em componente.

Os grupos com `data-part` identificam cabeça, orelhas, focinho, olhos, braços, tronco, pernas, jaqueta, insígnia e efeitos. A expressão é um grupo separado dos movimentos corporais. Nada depende de bitmaps.

## Acessibilidade e limites

- `prefers-reduced-motion` desativa o movimento sem esconder a expressão. Nessa preferência, os controles de pausa/repetição ficam desativados. Somente no laboratório, a opção **Permitir animações nesta prévia** permite assistir por escolha explícita; começa desmarcada, não é salva e não muda a configuração do dispositivo. Os SVGs independentes continuam respeitando a preferência por padrão.
- Botões reais, indicação de estado, teclado, foco visível e mensagens de estado acessíveis.
- Acerto e comemoração são ações curtas; somente a espera continua até ser pausada.
- Os SVGs animados têm CSS interno: visualizadores estáticos e alguns importadores vetoriais mostram apenas uma pose. Abra em navegador atual para ver os movimentos.
- Ao usar várias instâncias inline, torne únicos os IDs de título/descrição para preservar os rótulos acessíveis. As classes de animação já usam o prefixo `cora` nos keyframes.
- Este pacote contém o desenho e protótipo animado. Não altera a aplicação nem gera builds Windows/Android, e ainda não é um arquivo Lottie ou Rive.
