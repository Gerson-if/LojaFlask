# Changelog desta correção

## 🆕 Gestão de lojistas reestruturada em hub central + correção no histórico de assinatura

### Problema antes desta mudança
A tela de listagem de lojistas (superadmin) acumulava muitos botões por
linha — suspender conta, abrir um dropdown de assinatura, campo de senha
inline, excluir — tudo espremido na tabela. E ajustar manualmente a data de
vencimento de uma assinatura criava um novo registro no histórico marcado
como "renovação", misturando correções administrativas com pagamentos
reais (distorcendo o total já pago e a receita calculada).

### 🆕 Nova página: gerenciamento completo por lojista
A listagem (`/painel/admin/lojistas`) agora só lista e filtra — cada linha
tem um único botão "Gerenciar", que leva para uma página central nova
(`/painel/admin/lojistas/<id>`) organizada em seções claras:

- **Visão geral**: status da conta, status da assinatura, total pago, data de cadastro.
- **Conta & segurança**: suspender/reativar conta, ver último login,
  desbloquear conta (se travada por tentativas de login), definir nova senha.
- **Loja**: contadores de produtos/pedidos/clientes e link direto para a loja pública.
- **Assinatura**: registrar renovação paga (com valor e observação) e
  ajustar a data de vencimento manualmente, lado a lado — para deixar claro
  que são duas ações com propósitos diferentes — além de suspender a
  assinatura.
- **Histórico**: todas as renovações, ajustes e suspensões daquele lojista,
  com quem registrou cada uma.
- **Zona de perigo**: exclusão do lojista, isolada visualmente do resto.

Também foi adicionada uma navegação "Anterior / Próximo" no topo da página,
para o superadmin revisar vários lojistas em sequência (em ordem alfabética)
sem precisar voltar à listagem a cada um.

### 🔴 Bug corrigido: ajuste de data contava como renovação no histórico
Adicionado um terceiro tipo de evento (`action="adjustment"`) ao histórico
de assinatura, distinto de `"renew"` (renovação paga) e `"suspend"`. Agora,
ao corrigir manualmente a data de vencimento de uma loja, o evento fica
registrado como **ajuste**, não como renovação — não soma em "total pago"
nem em receita/MRR, e aparece no histórico com um rótulo diferente ("Ajuste
de data" em vez de "Renovação"). Antes, esse tipo de correção criava um
registro de renovação com `months`/`amount` vazios, o que distorcia os
totais e ainda chegou a exibir "None mês" na tela em alguns casos.

### 🗄️ Banco de dados desta rodada
Nova migration `a7b8c9d0e1f2`: adiciona `"adjustment"` ao enum `action` de
`subscription_payments`. Registros antigos de ajuste (gravados como
`"renew"` com `months` nulo, antes desta correção) continuam como estavam;
quem quiser reclassificá-los pode rodar manualmente o UPDATE documentado
no arquivo da migration.

---

## 🆕 Landing page, segurança de contas e melhorias de gestão

### 🔴 Bug corrigido: botão "Criar conta" deformado no celular
No menu superior da landing page, o botão "Criar loja grátis" não tinha
`white-space: nowrap`. Em qualquer celular comum (confirmei matematicamente:
o nav precisava de ~460px para caber numa linha, mas a tela tem 360-375px),
o texto quebrava em duas linhas dentro do botão, fazendo-o crescer e ficar
visualmente deformado comparado aos outros elementos do menu. Corrigido com
`white-space: nowrap` em todos os botões do nav, além de um texto mais curto
("Criar conta") que substitui o texto longo abaixo de 560px de largura —
agora cabe confortavelmente até em telas de 320px.

### 🆕 Landing page com termos de uso e política de privacidade
Adicionados como links discretos no rodapé, abrindo um modal leve (sem
JavaScript, via `:target` do CSS) — não chamam atenção do visitante, mas
estão acessíveis.

### 🆕 Segurança de contas
- **Bloqueio temporário após tentativas de login incorretas**: 5 tentativas
  com senha errada bloqueiam a conta por 15 minutos. O superadmin pode
  desbloquear manualmente a qualquer momento (botão na listagem de
  lojistas e na página de detalhe da assinatura).
- **Política de senha mais forte**: mínimo de 8 caracteres com letra e
  número (antes eram só 6 caracteres sem nenhum outro requisito), aplicada
  no cadastro, na troca de senha pelo próprio lojista e na redefinição feita
  pelo superadmin.
- **Confirmação de senha no cadastro** — antes era possível digitar errado
  sem perceber.
- **Nova página "Segurança" para o lojista** (`/painel/seguranca`): antes,
  só o superadmin conseguia trocar a senha de um lojista — o próprio
  lojista não tinha nenhuma forma de trocar a própria senha. Agora ele pode
  trocá-la a qualquer momento (pedindo a senha atual), e ver quando foi o
  último login e a última troca de senha.
- Login bem-sucedido agora registra a data/hora (`last_login_at`), visível
  tanto para o lojista (página de Segurança) quanto para o superadmin
  (listagem e detalhe de cada lojista).

### 🆕 Gestão de lojistas (superadmin) melhorada
- Cards de resumo no topo (contas ativas, pagantes, em teste, vencidos),
  cada um já filtrando a lista ao clicar.
- Filtro por status de conta (ativa/suspensa) e por status de assinatura
  (pago/teste/vencido/sem assinatura), além da busca por nome/e-mail que já
  existia.
- Linhas de lojistas com assinatura vencida agora têm um destaque visual
  (fundo levemente vermelho) para chamar atenção mais rápido.
- Indicador de conta bloqueada por tentativas de login, com botão de
  desbloqueio direto na listagem.
- A lógica de cálculo de status de assinatura — antes duplicada em Jinja na
  própria tabela — passou a usar a mesma função central já usada em todo o
  resto do sistema (`store_access_status`), eliminando uma fonte de
  inconsistência.

### 🆕 Área de assinatura do superadmin (detalhe por lojista) melhorada
- Mostra também o último login do lojista.
- Indicador e ação de desbloqueio de conta bloqueada, direto na tela.
- Corrigido um bug de exibição: ajustes manuais de data (ação "definir
  data de vencimento") apareciam no histórico como "Renovação (None mês)" —
  agora aparecem corretamente como "Data ajustada manualmente", distinto de
  uma renovação paga de fato.

### 🆕 Área de assinatura do lojista ("Minha assinatura") melhorada
- Alerta visual proeminente no topo da página quando o acesso está
  bloqueado, ou quando o trial/assinatura está perto de vencer (≤ 3 dias no
  trial, ≤ 7 dias na assinatura paga) — antes essa informação só aparecia
  discretamente dentro de um badge pequeno.
- Barra de progresso visual mostrando quanto do ciclo atual (trial ou
  mensalidade) já passou.
- Corrigido o mesmo bug de exibição do histórico mencionado acima
  ("Renovação (None mês)" → "Data ajustada").

### 🗄️ Banco de dados desta rodada
Nova migration `f6a7b8c9d0e1`, totalmente aditiva, em `users`:
`failed_login_attempts`, `locked_until`, `last_login_at`,
`password_changed_at`.

---

## 🆕 Carrinho, favicon, financeiro, variações de produto e bloqueio por inadimplência

### 🔴 Bug crítico corrigido: quantidade no carrinho não atualizava
Havia dois listeners de clique escutando o mesmo botão de +/- de quantidade:
um genérico em `document` (usado também na página de produto) e outro
dentro do carrinho. Pela ordem real de propagação de eventos do navegador
(bubbling), o handler do carrinho disparava **antes** do handler global —
ou seja, ele lia a quantidade **antes** dela ser incrementada/decrementada,
e enviava esse valor desatualizado para o servidor. Visualmente o número no
campo mudava (o handler global corrigia a tela depois), mas o carrinho real
nunca recebia o valor certo. Corrigido isolando toda a lógica de
incremento/decremento dentro do próprio handler do carrinho, removendo a
duplicidade.

### 🔴 Bug de layout corrigido: carrinho deslocando para a esquerda
O grid CSS do item do carrinho declarava 4 colunas
(`84px minmax(0,1fr) auto auto`), mas o HTML tinha 5 elementos filhos
(imagem, info, quantidade, subtotal, botão remover). A 5ª coluna ficava
implícita, com largura instável — qualquer mudança no número de dígitos da
quantidade (de "9" para "10", por exemplo) fazia o navegador recalcular o
espaço disponível de forma diferente, deslocando o subtotal e o botão de
remover. Corrigido declarando as 5 colunas explicitamente e fixando a
largura do campo de quantidade, além de remover as setinhas nativas do
campo numérico (outra fonte de variação de largura) e simplificar a
animação de remoção do item (antes usava `transform: translateX`, que
também deslocava o conteúdo).

### 🆕 Favicon personalizado da loja
Todas as páginas públicas da loja (vitrine, produto, carrinho, checkout,
confirmação) agora usam a logo cadastrada pelo lojista como favicon
(`<link rel="icon">`), quando ela existe.

### 🆕 Data de renovação da assinatura agora pode ser corrigida
Antes só era possível "somar" 1/3/12 meses a partir de hoje. Agora o
superadmin também pode definir uma data exata de vencimento na tela de
detalhe de assinatura do lojista — útil para corrigir lançamentos errados ou
fazer acordos com prazo customizado. A correção fica registrada no
histórico, sem contar como uma renovação paga (não entra em MRR/receita).

### 🆕 Dashboard do superadmin sem pedidos, com gráfico de status
A rota e o link de "Pedidos da plataforma" foram removidos — o superadmin
não vê mais o detalhe dos pedidos de cada lojista. No lugar, o dashboard
ganhou um gráfico de rosca (SVG, sem dependência externa) mostrando a
distribuição de lojas por status de assinatura (pagantes / em teste /
vencidas / sem assinatura), ao lado de MRR e receita total recebida.

### 🆕 Bloqueio efetivo de loja inadimplente, sem expor o motivo ao cliente
A proteção de painel (`require_active_subscription`) e de loja pública
(`require_active_storefront`) já existia; foi reforçada com uma página
pública dedicada para quando a loja está bloqueada — usa a identidade
visual da própria loja (logo, cores) e mostra apenas uma mensagem genérica
e amigável ("está indisponível no momento... volte em breve"), sem
qualquer menção a assinatura, pagamento ou inadimplência. O cliente final
nunca sabe o motivo real do bloqueio.

### 🆕 Preço de custo, margem de lucro e seção financeira
- Novo campo opcional "Preço de custo" no cadastro de produto, com cálculo
  de margem (R$ e %) em tempo real ao digitar, e exibido também na listagem
  de produtos.
- Nova seção **Financeiro** (`/painel/financeiro`) com receita, custo,
  lucro e margem média do período (7/30/90/365 dias), além de um ranking
  dos produtos mais vendidos com a margem de cada um. O custo de cada venda
  é registrado no momento da compra (`unit_cost` em cada item do pedido) —
  produtos vendidos antes dessa funcionalidade existir usam o custo atual
  cadastrado no produto como aproximação, sinalizada na tela.

### 🆕 Variações de produto (tamanho/cor) com estoque próprio
- O cadastro de produto agora permite adicionar quantas variações
  (tamanho + cor) o lojista quiser, cada uma com seu próprio estoque e,
  opcionalmente, seu próprio preço (se vazio, usa o preço do produto).
- **Produtos sem nenhuma variação continuam funcionando exatamente como
  antes** — nenhuma mudança de comportamento, mesmo formulário, mesmo
  controle de estoque no próprio produto.
- Na loja pública, produtos com variação mostram seletores de tamanho/cor
  (pills); o cliente precisa escolher uma combinação válida e com estoque
  antes de conseguir adicionar ao carrinho. O estoque e preço exibidos
  mudam dinamicamente conforme a seleção.
- O carrinho identifica produto+variação por uma chave composta
  (`"42"` para produto sem variação, `"42:7"` para produto com variação),
  o que manteve 100% de compatibilidade com carrinhos já abertos antes
  desta mudança.
- O checkout debita o estoque da variação certa (não do produto genérico)
  e registra, em cada item do pedido, qual variação foi comprada
  (preservado mesmo que a variação seja depois excluída do catálogo).

### 🗄️ Banco de dados desta rodada
Nova migration `e5f6a7b8c9d0`, totalmente aditiva:
- `products.cost_price` (opcional).
- Tabela `product_variants` (tamanho, cor, estoque, preço opcional).
- `order_items.variant_id`, `variant_label`, `unit_cost` (todos opcionais,
  pedidos antigos continuam válidos com esses campos vazios).

---

## 🆕 Área "Minha assinatura" (lojista) + melhorias no painel do superadmin

### Para o lojista
- Nova página em `/painel/assinatura` (link "Minha assinatura" no menu) mostrando:
  - Status atual com badge (período de teste, assinatura ativa, acesso expirado ou sem assinatura).
  - Data de fim do período de teste e/ou data da próxima renovação.
  - Valor do plano.
  - Histórico completo de pagamentos (data, ação, período coberto, valor, observação).
  - Botão de contato direto no WhatsApp com a equipe (usa o telefone cadastrado de um superadmin ativo).
- O banner de aviso de assinatura (exibido no topo do painel quando o teste está
  acabando ou a assinatura está perto de vencer) agora aponta de fato para essa
  página, em vez de um link `#assinar` sem destino.

### Para o superadmin
- Dashboard (`/painel`) agora mostra, além das métricas que já existiam:
  - **MRR** (receita mensal recorrente, calculada como nº de lojas pagantes × preço do plano).
  - **Receita total recebida** (soma de todas as renovações já registradas).
  - Distribuição de lojas por status de assinatura (pagantes / em teste / vencidas).
  - Lista das renovações mais recentes em toda a plataforma.
- Nova página de detalhe/histórico de assinatura por lojista
  (`/painel/admin/lojistas/<id>/assinatura/historico`, acessível pelo link
  "Ver histórico completo" no menu de assinatura de cada lojista), com:
  - Status atual detalhado e total já pago por aquela loja.
  - Formulário de renovação com **valor customizável** e **observação livre**
    (ex.: forma de pagamento, referência do PIX) — antes só era possível
    renovar com o preço padrão e sem deixar nenhuma anotação.
  - Histórico completo de pagamentos/suspensões daquela loja, com quem
    registrou cada ação.

### Banco de dados
Nova tabela `subscription_payments` (migration `d4e5f6a7b8c9`): registra cada
renovação ou suspensão feita pelo superadmin, preservando o histórico que
antes era perdido (a única informação salva era `stores.paid_until`, que era
simplesmente sobrescrito a cada renovação, sem deixar rastro de quando ou por
quanto a assinatura foi paga).

### Bug corrigido: tela de bloqueio em branco
A tela exibida para lojistas com assinatura vencida
(`subscription/blocked.html`) usava o bloco `public_content` do layout, mas
esse bloco só é renderizado para visitantes **não autenticados**. Como essa
tela só aparece para usuários logados, o resultado real era o painel
completo (com sidebar) e nenhum conteúdo — o lojista bloqueado não via
nenhuma explicação nem botão de ação. Corrigido trocando para o bloco
`content`, usado pelo layout para qualquer usuário autenticado. A tela
passou a aproveitar a sidebar para mostrar também o link "Minha assinatura".

---

## 🔴 Bug crítico: site abria direto em tela de login/cadastro em vez da landing page

**Causa:** o blueprint do painel (`dashboard_bp`) registrava a rota `/` (mesma
URL da landing page), sem nenhum `url_prefix`. O Flask sempre entrega `/`
para a primeira regra cadastrada no mapa de URLs — que era a do painel,
protegida por `@login_required`. Resultado: todo visitante sem login era
redirecionado para a tela de login, e a landing page nunca aparecia.

**Correção:** `app/routes/dashboard.py` agora declara
`Blueprint("dashboard", __name__, url_prefix="/painel")`. Todas as rotas do
painel (produtos, categorias, clientes, pedidos, configurações, área do
super admin) passaram de `/produtos`, `/categorias` etc. para
`/painel/produtos`, `/painel/categorias` etc. Como **todo** link interno do
projeto já usava `url_for(...)` (nunca URL fixa), essa mudança é transparente
— nenhum template ou JS precisou ser ajustado para os links existentes.

A raiz `/` agora pertence exclusivamente à landing page, sem concorrência.

## 🟠 Outros bugs corrigidos

- **Rota "Pedidos da plataforma" inacessível:** `dashboard.admin_orders`
  existia no backend e tinha template pronto, mas não havia nenhum link no
  menu do super admin. Adicionado o item "Pedidos da plataforma" no menu
  lateral.
- **Filtro de status sem efeito em "Pedidos da plataforma":** o template já
  tinha o `<select>` de status e botão "Filtrar", mas a rota
  `admin_orders()` sempre devolvia todos os pedidos, ignorando o filtro.
  Agora aplica `request.args.get("status")` igual à tela equivalente do
  lojista.
- **Busca de clientes incompleta:** o campo de busca dizia "Buscar por nome
  ou telefone", mas só filtrava por nome. Agora também busca por telefone
  (dígitos).
- **E-mail do cliente perdido em texto livre:** no checkout, o e-mail do
  cliente era concatenado dentro do campo de observações do pedido
  (`notes`), por não existir coluna própria em `orders`. Isso misturava
  dado estruturado com texto livre e dificultava qualquer busca/relatório
  futuro. Adicionada a coluna `customer_email` em `orders` (ver migration
  abaixo) e corrigido o checkout para usá-la, além de salvar o e-mail no
  cadastro do cliente (`customers.email`, que já existia mas não era
  preenchido no fluxo de checkout).

## 🧹 Limpeza de código morto

- Removidos `app/trial.py` e `app/templates/trial/blocked.html` — módulo e
  template legados, já substituídos por `app/subscription.py` e
  `templates/subscription/blocked.html`, mas que continuavam no projeto sem
  uso e com comentários desatualizados apontando para eles.
- `app/templates/_trial_banner.html` renomeado para
  `_subscription_banner.html` para refletir o nome real do sistema atual
  (assinatura, não mais "trial" como conceito isolado).
- Comentários desatualizados no código que mencionavam o fluxo antigo de
  trial foram corrigidos para refletir o fluxo atual de assinatura.
- Removidos `server.err.log` e `server.out.log` (logs de uma sessão de
  depuração anterior, sem propósito em um pacote de código-fonte) e todas
  as pastas `__pycache__`.

## 🗄️ Melhorias no banco de dados

Nova migration `c3d4e5f6a7b8_add_order_email_and_status_tracking.py`:

- `orders.customer_email` (string, opcional) — snapshot do e-mail do
  cliente no momento da compra, no mesmo padrão já usado para
  `customer_name`/`customer_phone`/`customer_address`.
- `orders.status_updated_at` (datetime, opcional) — registra quando o
  status do pedido mudou pela última vez. Preenchido automaticamente pela
  tela de detalhe do pedido sempre que o status é alterado.
- Índice em `orders.status` — acelera os filtros por status usados tanto na
  tela de pedidos do lojista quanto na tela de pedidos da plataforma
  (super admin).

Também padronizada a migration `b2c3d4e5f6a7_add_paid_until_to_stores.py`
para usar `batch_alter_table`, alinhando com o padrão das demais migrations
do projeto (necessário para portabilidade total com SQLite).

Exibição do e-mail do cliente adicionada na tela de detalhe do pedido
(`dashboard/order_detail.html`), ao lado de telefone e endereço.

## 📄 Documentação

- `README.md` reescrito: removida uma duplicação de título solta no final
  do arquivo, adicionado mapa de rotas (incluindo a separação `/` vs
  `/painel`), atualizada a lista de tabelas/colunas do banco, adicionada
  seção "Migrations — guia rápido" com o histórico de todas as migrations
  e as boas práticas seguidas no projeto, e adicionada seção "Solução de
  problemas" cobrindo o bug da landing page e outros problemas comuns de
  configuração/deploy.
- Criado `.gitignore` (não existia) cobrindo `.env`, banco SQLite local,
  uploads de lojistas, cache Python e logs.
- Criado este `CHANGELOG.md`.

## ✅ Validação

Todas as alterações foram validadas antes da entrega:

- Todos os arquivos `.py` do projeto compilam sem erro de sintaxe.
- Todos os 26 templates Jinja têm sintaxe válida.
- O app inicia (`create_app()`) sem exceções.
- `GET /` responde 200 com a landing page (não mais redirecionado para
  login/cadastro).
- `GET /painel` sem sessão autenticada responde com redirect (302) para
  login, como esperado — protegido, mas sem conflitar com `/`.
- A cadeia de migrations (`revision`/`down_revision`) é linear, sem
  branches, do schema inicial até a migration mais recente.
