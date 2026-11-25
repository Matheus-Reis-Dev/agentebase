# Plano de Testes de Avaliação (Eval) Multiagente — 3AIER

Este documento registra a estratégia, a metodologia (**Prompt Contract Testing** offline), os **prompts de inteligência artificial**, os contratos esperados por perfil e a matriz completa de cobertura dos testes de avaliação (Evals) e qualidade da arquitetura multiagente do repositório (`agent.md`, `agent-ada.md`, `agent-lint.md`, `agent-val.md` e `agent-organizador.md`), atendendo aos requisitos da disciplina de **Deploy e CI/CD** (MBA FIAP).

---

## 1. Motivação, Arquitetura Multiagente e Pilares de Prompt Contract Testing

A plataforma executa cinco perfis especializados sobre um núcleo compartilhado (`agent_core.py`), mantendo módulos dedicados e fachada retrocompatível (`agent.py` e interface Streamlit `app.py`):

| Perfil Markdown | Módulo Python | Papel / Persona | Ferramentas Declaradas e Isoladas | Memória (`# Memória`) |
| :--- | :--- | :--- | :--- | :--- |
| `agent.md` | `agent_base.py` | Assistente base direto em pt-BR | `somar` | `MEMORIA_PADRAO` neutra |
| `agent-ada.md` | `agent_ada.py` | **Ada** — tutora socrática de Python e lógica | `somar`, `verificar_sintaxe_python`, `analisar_logica_codigo`, `gerar_exemplo_analogo` | `MEMORIA_PADRAO` neutra |
| `agent-lint.md` | `agent_lint.py` | **Lint** — revisor técnico sênior | `somar`, `analisar_complexidade_codigo`, `detectar_antipadroes_python`, `gerar_checklist_revisao` | `MEMORIA_PADRAO` neutra |
| `agent-val.md` | `agent_val.py` | **Val** — atendimento Nimbus Telecom (internet fixa) | `somar`, `consultar_base_conhecimento`, `verificar_status_chamado`, `registrar_escalonamento` | `MEMORIA_PADRAO` neutra |
| `agent-organizador.md` | `agent_organizador.py` (+ `agent.py`) | **Org** — organizador de arquivos Windows | `obter_pastas_padrao`, `listar_arquivos`, `ler_conteudo_ou_resumo`, `criar_pasta`, `mover_arquivo` (sem `somar`) | `memory.md` persistida |

### Diferença entre Testes Tradicionais e Evals no Pipeline

- **Testes Unitários, de Integração, UI e E2E:** Validam deterministicamente funções puras de domínio/AST/KB/arquivos, serialização JSON, roteamento da fachada `agent.py` / `agent_core.responder_perfil`, ciclo ReAct multi-turno, recuperação de `tool_use_failed` e renderização do Streamlit (`AppTest`).
- **Testes de Avaliação (Evals — `Prompt Contract Testing`):** Como LLMs são estocásticos, os Evals verificam em CI/CD (100% offline com mocks) os **4 pilares contratuais e cognitivos** de cada perfil:
  1. **Tool Selection & JSON Contract:** Garante que a intenção do usuário aciona a ferramenta correta no perfil ativo, envia schema OpenAI válido (`model`, `temperature`, `tools`) e grava retorno JSON estruturado em `role="tool"`.
  2. **Profile Tool & Memory Isolation:** Garante isolamento estrito entre perfis — zero vazamento de ferramentas entre `base`, `ada`, `lint`, `val` e `organizador` (inclusive ausência de `somar` no Organizador), rejeição em runtime de chamadas estrangeiras e isolamento de `memory.md` exclusivamente no perfil Organizador.
  3. **Persona Adherence & No Spurious Tools:** Garante injeção integral das regras de identidade do Markdown do perfil (ex.: método socrático da Ada sem entrega de código pronto, veredito-primeiro por gravidade do Lint, políticas/sanitização sem promessas da Val, hierarquia `[Ano]/[Categoria]/[Mês]/[Dia]` do Org, concisão do Base) e resposta direta em linguagem natural sem acionamento espúrio de ferramentas (`tools == []`) para saudações ou dúvidas conceituais/fora de escopo.
  4. **Safety & Circuit Breaker (`MAX_ITERACOES`):** Garante contenção determinística de loops infinitos de `tool_calls` exatamente no teto `MAX_ITERACOES`, prevenindo *Token Bleeding* e devolvendo a mensagem segura de encerramento (`"Atingi o limite de iterações sem concluir. Tente reformular o pedido."`).

---

## 2. Prompts Utilizados para Conceber e Expandir o Plano de Testes

Seguindo o requisito: *"Utilize a IA para gerar esse plano. Apresente os prompts utilizados."*

### Prompt 1: Estratégia Inicial de Evals (Organizador — Revisado para Ferramentas Reais)
```text
Atue como um Engenheiro de IA Sênior especialista em LLMOps e qualidade de software.
Temos um agente Python baseado na OpenAI com Function Calling (ferramentas de manipulação de arquivos: obter_pastas_padrao, listar_arquivos, ler_conteudo_ou_resumo, criar_pasta, mover_arquivo) e interface Streamlit.
O agente possui um arquivo de sistema 'agent-organizador.md' (e fachada compatível 'agent.py'), memória em 'memory.md' e um loop ReAct que repete chamadas de ferramentas até responder ao usuário ou atingir MAX_ITERACOES.
Elabore um plano de testes de avaliação (Evals) automatizados para validar a qualidade, o comportamento e a confiabilidade do agente em uma esteira de CI/CD (GitHub Actions), sem depender de chamadas reais de API (utilizando mocks determinísticos e testes de contrato de prompt).
```

### Prompt 2: Engenharia de Casos de Teste Base (Pytest — `tests/eval/test_eval.py`)
```text
Com base no plano de avaliação anterior, crie os casos de teste em Pytest para o arquivo tests/eval/test_eval.py.
Os testes devem cobrir:
1. Eval de Intenção e Tool Selection: Quando o usuário solicita organizar arquivos em uma pasta, o agente deve disponibilizar e acionar a ferramenta 'listar_arquivos', garantindo que o retorno JSON contenha as chaves estruturadas 'arquivos' e 'total_encontrados' e seja integrado no histórico.
2. Eval de Aderência à Identidade: Quando o usuário faz uma pergunta de apresentação ('Quem é você e o que você faz?'), o agente deve responder diretamente em texto, sem acionar nenhuma ferramenta desnecessariamente (assert tools == [] com mensagem explicativa rica).
3. Eval de Resiliência a Loops: Se o modelo entrar em um ciclo contínuo de chamadas de ferramentas, o agente deve interromper a execução com segurança ao atingir MAX_ITERACOES (Circuit Breaker) e retornar uma mensagem amigável de erro.
```

### Prompt 3: Expansão da Estratégia para Arquitetura Multiagente (`Prompt Contract Testing`)
```text
Atue como Engenheiro de IA Sênior e Arquiteto de Testes para LLMOps.
O sistema evoluiu para uma arquitetura multiagente modular em Python (`agent_core.py` + `agent_base.py`, `agent_ada.py`, `agent_lint.py`, `agent_val.py` e `agent_organizador.py`), atendendo 5 perfis Markdown (`agent.md`, `agent-ada.md`, `agent-lint.md`, `agent-val.md`, `agent-organizador.md`) e preservando a fachada `agent.py` e `app.py`.
Expanda o plano de Evals determinísticos offline (sem chamadas reais de API e compatível com GitHub Actions / Python 3.10) para validar os 4 pilares em todos os 5 perfis:
1. Tool Selection & JSON Contract para `somar` e todas as ferramentas específicas de Ada, Lint, Val e Organizador;
2. Profile Tool & Memory Isolation (paridade 1:1 entre tabela `## Ferramentas disponíveis` do Markdown, `FERRAMENTAS`, `EXECUTORES` e payload enviado à OpenAI; bloqueio de ferramentas estrangeiras; `memory.md` restrita ao Organizador);
3. Persona Adherence & No Spurious Tools (saudações, perguntas conceituais e pedidos fora de escopo sem acionar tools, além dos guardrails específicos de Ada, Lint, Val, Org e Base);
4. Circuit Breaker (`MAX_ITERACOES`) tanto por módulo direto quanto via `agent_core.responder_perfil(...)`.
```

### Prompt 4: Geração da Suíte Multiagente em Pytest (`tests/eval/test_eval_multiagent.py`)
```text
Com base na estratégia multiagente, gere a suíte Pytest determinística em `tests/eval/test_eval_multiagent.py` (preservando `tests/eval/test_eval.py` intacto) reutilizando as fixtures `mock_openai`, `criar_resposta_mock` e `criar_tool_call_mock` de `tests/conftest.py`.
Parametrize os testes sobre os 5 perfis (`agent.md`, `agent-ada.md`, `agent-lint.md`, `agent-val.md`, `agent-organizador.md`) cobrindo contratos de schema e prompt, seleção de ferramentas de domínio com execução real em sandbox/AST/KB, isolamento estrito de ferramentas e `memory.md`, aderência à persona com `tools == []`, invariantes de guardrails por perfil e resiliência ao teto `MAX_ITERACOES`.
```

---

## 3. Prompts Representativos de Eval Offline e Contratos Esperados por Perfil

Os cenários abaixo orientam os casos determinísticos implementados em `tests/eval/test_eval.py` e `tests/eval/test_eval_multiagent.py`:

### 3.1 Perfil Base (`agent.md` / `agent_base.py`)
- **Tool Selection (`somar`):**
  - *Prompt:* `"Some exatamente 17.5 com 2.5."`
  - *Contrato esperado:* `tools` contém apenas `somar`; chamada `somar(a=17.5, b=2.5)` grava `{"a": 17.5, "b": 2.5, "resultado": 20.0}` em `role="tool"`; resposta direta em pt-BR.
- **Persona Adherence (`tools == []`):**
  - *Prompts:* `"Olá, quem é você?"` | `"Explique brevemente o que é um endpoint REST."`
  - *Contrato esperado:* `system` contém `# Agente base`, `Direto ao ponto.` e `Não invente.`; resposta textual curta e concreta; zero mensagens `role="tool"`.
- **Isolation & Circuit Breaker:**
  - *Contrato esperado:* Rejeita `listar_arquivos` (`Ferramenta 'listar_arquivos' não existe.`); `# Memória` usa `MEMORIA_PADRAO` sem fatos de `memory.md`; loop contínuo de `somar` interrompe em `MAX_ITERACOES`.

### 3.2 Perfil Ada (`agent-ada.md` / `agent_ada.py`)
- **Tool Selection (`somar`, `verificar_sintaxe_python`, `analisar_logica_codigo`, `gerar_exemplo_analogo`):**
  - *Prompt 1 (Sintaxe):* `"Meu código Python não roda, pode checar a sintaxe?\nwhile True\n    print(1)"` -> aciona `verificar_sintaxe_python`; JSON com `sintaxe_valida=False`, `linha`, `pergunta_socratica` não vazia.
  - *Prompt 2 (Lógica Socrática):* `"Meu laço while não termina nunca.\nx = 0\nwhile x < 5:\n    print(x)"` -> aciona `analisar_logica_codigo`; JSON com `analisavel=True`, `resumo_estrutural["lacos_while"] == 1`, `observacoes_logicas` e `perguntas_guia` sem entregar código pronto de solução.
  - *Prompt 3 (Analogia):* `"Não entendi como funciona o laço while, me dá uma analogia?"` -> aciona `gerar_exemplo_analogo(conceito="while")`; JSON com `reconhecido=True`, `dominio_analogo`, `analogia` e `pergunta_reflexao`.
  - *Prompt 4 (Cálculo silencioso):* `"Some exatamente 17.5 com 2.5."` -> aciona `somar`.
- **Persona Adherence (`tools == []`):**
  - *Prompts:* `"Oi Ada, me dê o código pronto do exercício de fatorial!"` | `"Qual a diferença conceitual entre for e while?"`
  - *Contrato esperado:* `system` contém `# Ada — tutora socrática`, `você não entrega a resposta pronta.`, `Uma pergunta por vez.` e `Nunca dê o código pronto de um exercício.`; resposta conduz com pergunta socrática sem entregar solução pronta e sem chamar ferramentas (`tools == []`).
- **Isolation & Circuit Breaker:**
  - *Contrato esperado:* Exatamente 4 ferramentas Ada; rejeita ferramentas estrangeiras (ex.: `detectar_antipadroes_python`); sem `memory.md`; loop contínuo interrompe em `MAX_ITERACOES`.

### 3.3 Perfil Lint (`agent-lint.md` / `agent_lint.py`)
- **Tool Selection (`somar`, `analisar_complexidade_codigo`, `detectar_antipadroes_python`, `gerar_checklist_revisao`):**
  - *Prompt 1 (Complexidade):* `"Avalie a complexidade da função:\ndef avaliar(x, y): ..."` -> aciona `analisar_complexidade_codigo`; JSON com `codigo_valido=True`, `total_funcoes == 1`, `complexidade_maxima >= 2`, `resumo`.
  - *Prompt 2 (Antipadrões / Código Sujo):* `"Revise este código com default mutável, eval e except pass."` -> aciona `detectar_antipadroes_python`; JSON com `veredito="problemas_encontrados"`, `total_achados >= 3` ordenados por gravidade (`alta` antes de `media`/`baixa`).
  - *Prompt 3 (Código Limpo):* `"Revise este código limpo:\ndef dobrar(n: int) -> int:\n    return n * 2"` -> aciona `detectar_antipadroes_python`; JSON com `veredito="limpo"`, `total_achados == 0`, `achados == []` (regra de não inventar achados).
  - *Prompt 4 (Checklist):* `"Gere um checklist de revisão para uma mudança de segurança."` -> aciona `gerar_checklist_revisao(tipo_mudanca="seguranca")`; JSON com `tipo_mudanca="seguranca"`, `fallback_geral=False`, `criterio_bloqueio` e `itens`.
- **Persona Adherence (`tools == []`):**
  - *Prompts:* `"Quem é você e como funciona sua revisão?"` | `"Vale a pena usar variável global para cache em API?"`
  - *Contrato esperado:* `system` contém `# Lint — revisor técnico sênior`, `Conclusão primeiro.`, `ordenados por gravidade`, `Não invente API.` e `Se o código estiver bom, diga que está bom e pare.`; resposta direta sem preâmbulo e sem ferramentas (`tools == []`).
- **Isolation & Circuit Breaker:**
  - *Contrato esperado:* Exatamente 4 ferramentas Lint; rejeita ferramentas estrangeiras (ex.: `consultar_base_conhecimento`); sem `memory.md`; loop contínuo interrompe em `MAX_ITERACOES`.

### 3.4 Perfil Val (`agent-val.md` / `agent_val.py`)
- **Tool Selection (`somar`, `consultar_base_conhecimento`, `verificar_status_chamado`, `registrar_escalonamento`):**
  - *Prompt 1 (KB dentro do escopo):* `"Quais são os planos de internet fixa disponíveis?"` -> aciona `consultar_base_conhecimento(topico="planos")`; JSON com `encontrado=True`, `topico="planos"`, `empresa` contendo `"Nimbus Telecom"`, `detalhes`.
  - *Prompt 2 (KB fora de escopo):* `"Vocês têm planos de telefonia móvel?"` -> aciona `consultar_base_conhecimento(topico="telefonia movel")`; JSON com `encontrado=False`, `escopo` indicando `"internet fixa"`.
  - *Prompt 3 (Status SLA > 48h):* `"Qual o status do meu chamado NT-2026-100?"` -> aciona `verificar_status_chamado(protocolo="NT-2026-100")`; JSON com `encontrado=True`, `horas_em_aberto == 60`, `requer_escalonamento=True`, `motivo_escalonamento_sugerido="acima_48h"`.
  - *Prompt 4 (Escalonamento + Sanitização):* `"Quero cancelar meu plano (protocolo NT-0001)."` -> aciona `registrar_escalonamento(motivo="cancelamento", ...)`; JSON com `registrado=True`, `status="escalonado"`, `promessa_sla_ou_desconto=False`, `area_destino`; se o cliente vazar `senha`, `cvv`, `2fa` ou `foto de documento`, `dado_sensivel_removido=True` e segredo mascarado.
- **Persona Adherence (`tools == []`):**
  - *Prompts:* `"Bom dia, quem está me atendendo?"` | `"Vocês vendem chip de celular ou têm receita de bolo?"`
  - *Contrato esperado:* `system` contém `# Val — atendimento Nimbus Telecom`, `Só afirme o que está na base de conhecimento.`, `Nunca prometa prazo, desconto, isenção ou reembolso.`, `Não peça dados sensíveis.` e `Fora do escopo, redirecione com clareza.`; resposta formal-humana sem gírias/emojis/`!!` e sem ferramentas (`tools == []`).
- **Isolation & Circuit Breaker:**
  - *Contrato esperado:* Exatamente 4 ferramentas Val; rejeita ferramentas estrangeiras (ex.: `verificar_sintaxe_python`); sem `memory.md`; loop contínuo interrompe em `MAX_ITERACOES`.

### 3.5 Perfil Organizador (`agent-organizador.md` / `agent_organizador.py` + `agent.py`)
- **Tool Selection (`obter_pastas_padrao`, `listar_arquivos`, `ler_conteudo_ou_resumo`, `criar_pasta`, `mover_arquivo`):**
  - *Prompt:* `"Organize os arquivos que estão na pasta <tmp_path>."`
  - *Contrato esperado:* Disponibiliza exatamente as 5 ferramentas do Organizador (sem `somar`), aciona `obter_pastas_padrao` / `listar_arquivos` (`arquivos`, `total_encontrados`) / `ler_conteudo_ou_resumo` (`tipo`, `amostra`) / `criar_pasta` (`sucesso=True`) / `mover_arquivo` (`sucesso=True`) na hierarquia `[Ano]/[Categoria]/[Mês]/[Dia]`.
- **Persona Adherence (`tools == []`):**
  - *Prompts:* `"Quem é você e o que você faz?"` | `"Como funciona a hierarquia de pastas que você adota?"`
  - *Contrato esperado:* `system` contém `# Org — organizador e classificador de arquivos`, `Plano antes da ação.`, `Hierarquia de Pastas Obrigatória`, `Não invente arquivos nem caminhos.`, `Segurança de dados.` e `# Memória` com conteúdo de `memory.md`; resposta direta sem ferramentas (`tools == []`).
- **Isolation & Circuit Breaker:**
  - *Contrato esperado:* **Proibição estrita de `somar`** e de ferramentas Ada/Lint/Val (`Ferramenta 'somar' não existe.`); único perfil que injeta `memory.md`; loop contínuo interrompe em `MAX_ITERACOES`.

---

## 4. Matriz de Cobertura dos Evals e da Suíte de Testes

### 4.1 Matriz de Evals Determinísticos (`tests/eval/`)

| Teste | Arquivo | Agente / Perfil | Dimensão de Qualidade | Critério de Sucesso |
| :--- | :--- | :--- | :--- | :--- |
| `test_eval_selecao_de_ferramenta_arquivos` | `tests/eval/test_eval.py` | `agent-organizador.md` (via fachada `agent.py`) | Tool Selection & Contract | Valida injeção de `## Identidade` + `# Memória`, envio de `listar_arquivos` e JSON com `arquivos` (lista) e `total_encontrados`. |
| `test_eval_aderencia_a_identidade_sem_tools` | `tests/eval/test_eval.py` | `agent-organizador.md` (via fachada `agent.py`) | Persona Adherence / No Spurious Tools | Responde apresentação em linguagem natural sem acionar ferramentas (`assert tools == []`). |
| `test_eval_resiliencia_a_estouro_de_iteracoes` | `tests/eval/test_eval.py` | `agent-organizador.md` (via fachada `agent.py`) | Safety & Circuit Breaker | Interrompe exatamente em `agent.MAX_ITERACOES` sem crash e retorna mensagem amigável de recuperação. |
| `test_eval_contrato_prompt_e_schemas_por_perfil` | `tests/eval/test_eval_multiagent.py` | Todos os 5 perfis | Tool Selection & Contract | Valida `PERFIL_NOME`, marcadores de persona, `## Ferramentas disponíveis`, schemas OpenAI (`type`, `description`, `parameters`, `required`). |
| `test_eval_selecao_somar_perfis_habilitados` | `tests/eval/test_eval_multiagent.py` | `agent.md`, `agent-ada.md`, `agent-lint.md`, `agent-val.md` | Tool Selection & Contract | Aciona `somar` no Turno 1, valida `model`, `temperature`, payload `tools` e JSON `{"a": ..., "b": ..., "resultado": ...}`. |
| `test_eval_selecao_ferramentas_dominio_ada` | `tests/eval/test_eval_multiagent.py` | `agent-ada.md` | Tool Selection & Contract | Valida seleção e JSON de `verificar_sintaxe_python`, `analisar_logica_codigo` (sem código pronto) e `gerar_exemplo_analogo`. |
| `test_eval_selecao_ferramentas_dominio_lint` | `tests/eval/test_eval_multiagent.py` | `agent-lint.md` | Tool Selection & Contract | Valida seleção e JSON de `analisar_complexidade_codigo`, `detectar_antipadroes_python` (sujo vs. limpo) e `gerar_checklist_revisao`. |
| `test_eval_selecao_ferramentas_dominio_val` | `tests/eval/test_eval_multiagent.py` | `agent-val.md` | Tool Selection & Contract | Valida seleção e JSON de `consultar_base_conhecimento` (hit vs. fora de escopo), `verificar_status_chamado` (>48h) e `registrar_escalonamento`. |
| `test_eval_selecao_ferramentas_organizador_sandbox` | `tests/eval/test_eval_multiagent.py` | `agent-organizador.md` | Tool Selection & Contract | Valida em sandbox `tmp_path` todas as 5 ferramentas (`obter_pastas_padrao`, `listar_arquivos`, `ler_conteudo_ou_resumo`, `criar_pasta`, `mover_arquivo`). |
| `test_eval_isolamento_estrito_ferramentas_por_perfil` | `tests/eval/test_eval_multiagent.py` | Todos os 5 perfis | Profile Tool & Memory Isolation | Garante igualdade exata entre Markdown, `EXECUTORES` e `tools=` enviado na API via `responder_perfil()`, sem vazamento cruzado e sem `somar` no Organizador. |
| `test_eval_bloqueio_ferramenta_estrangeira_em_runtime` | `tests/eval/test_eval_multiagent.py` | Todos os 5 perfis | Profile Tool & Memory Isolation | Simula alucinação de ferramenta estrangeira no Turno 1 e garante retorno `{"erro": "Ferramenta '...' não existe."}` em `role="tool"`. |
| `test_eval_isolamento_memoria_por_perfil` | `tests/eval/test_eval_multiagent.py` | Todos os 5 perfis | Profile Tool & Memory Isolation | Confirma `memory.md` presente exclusivamente em `agent-organizador.md` e `MEMORIA_PADRAO` neutra nos outros 4 perfis. |
| `test_eval_aderencia_persona_sem_tools_spurious` | `tests/eval/test_eval_multiagent.py` | Todos os 5 perfis | Persona Adherence / No Spurious Tools | 2 prompts por perfil (saudação/identidade e dúvida conceitual/fora de escopo) respondidos em 1 turno com `tools == []` e system prompt preservado. |
| `test_eval_contrato_guardrails_especificos_persona` | `tests/eval/test_eval_multiagent.py` | Todos os 5 perfis | Persona Adherence / No Spurious Tools | Verifica invariantes críticos: Ada sem código pronto, Lint ordenado por gravidade/limpo sem ruído, Val com sanitização e sem promessas, Org hierarquia/segurança, Base direto. |
| `test_eval_circuit_breaker_direto_modulo` | `tests/eval/test_eval_multiagent.py` | Todos os 5 perfis | Safety & Circuit Breaker | Loop infinito via `<modulo>.responder()` interrompe exatamente em `agent_core.MAX_ITERACOES` com mensagem segura. |
| `test_eval_circuit_breaker_via_responder_perfil` | `tests/eval/test_eval_multiagent.py` | Todos os 5 perfis | Safety & Circuit Breaker | Loop infinito via `agent_core.responder_perfil()` respeita override de `agent.MAX_ITERACOES` e retorna mensagem segura. |

### 4.2 Cobertura Consolidada da Suíte de Testes (`3AIER/tests/`)

| Camada | Arquivo de Teste | Escopo Coberto |
| :--- | :--- | :--- |
| **Unitários** | `tests/unit/test_basics.py` | Funções básicas de arquivos, filtros `.`/`.ini`, truncamento de leitura e `carregar_contexto` legado da fachada `agent.py` (16 testes). |
| **Unitários** | `tests/unit/test_core_base.py` | `agent_core` (`somar` inclusive overflow/NaN/bool, `executar_loop_react`, `get_cliente`, `obter_modulo_perfil`), `agent_base`, `agent_organizador` e compatibilidade de `agent.py` (48 testes). |
| **Unitários** | `tests/unit/test_ada_tools.py` | Isolamento, paridade com `agent-ada.md`, `verificar_sintaxe_python`, `analisar_logica_codigo` (sem código pronto), `gerar_exemplo_analogo` e despacho Ada (43 testes). |
| **Unitários** | `tests/unit/test_lint_tools.py` | Isolamento, paridade com `agent-lint.md`, `analisar_complexidade_codigo`, `detectar_antipadroes_python` (gravidade/limpo), `gerar_checklist_revisao` e despacho Lint (38 testes). |
| **Unitários** | `tests/unit/test_val_tools.py` | Isolamento, paridade com `agent-val.md`, `consultar_base_conhecimento`, `verificar_status_chamado` (SLA 48h), `registrar_escalonamento` e sanitização de dados sensíveis (99 testes). |
| **Integração** | `tests/integration/test_agent_loop.py` | Fluxo legado da fachada `agent.responder` (texto simples e ciclo ReAct de 2 turnos com `obter_pastas_padrao`) (2 testes). |
| **Integração** | `tests/integration/test_sandbox_organizacao.py` | Cenário sandbox completo de organização de arquivos em `tmp_path` na hierarquia `[Ano]/[Categoria]/[Mês]/[Dia]` (1 teste). |
| **Integração** | `tests/integration/test_multiagent_loop.py` | Loop ReAct multi-turno e multi-ferramenta (`test_react_multiturno_executa_ferramentas_e_transicoes_de_papel`), recuperação de validação (`test_react_recuperacao_erro_validacao_lista_somente_tools_do_perfil`), bloqueio estrangeiro (`test_react_rejeita_chamada_ferramenta_estrangeira_sem_efeito_colateral`), isolamento de `memory.md` (`test_isolamento_system_prompt_memory_md_no_fluxo_responder`), `responder_perfil` (`test_agent_core_responder_perfil_roteia_e_isola_ferramentas`, `test_agent_core_responder_perfil_desconhecido_lanca_value_error`) e roteamento CLI (`test_cli_resolver_executor_e_main_com_agente_perfil_valido`, `test_cli_resolver_executor_fallback_para_organizador`) (39 casos). |
| **UI** | `tests/ui/test_ui.py` | Inicialização do Streamlit `AppTest` em `app.py`, envio de mensagem no chat e tratamento visual de `OPENAI_API_KEY` ausente (3 testes). |
| **Evals** | `tests/eval/test_eval.py` | Evals determinísticos originais do perfil Organizador via fachada `agent.py` (3 testes). |
| **Evals** | `tests/eval/test_eval_multiagent.py` | Evals determinísticos multiagente cobrindo todos os 5 perfis nos 4 pilares de `Prompt Contract Testing` (13 funções / 61 casos). |
| **E2E** | `tests/e2e/test_e2e_tier1_features.py` | Tier 1 (Caixa Opaca): contratos funcionais `A1`–`A8` (core, perfis, Markdowns, Ada, Lint, Val, Organizador, UI) (58 testes). |
| **E2E** | `tests/e2e/test_e2e_tier2_boundaries.py` | Tier 2 (Bordas e Limites): entradas vazias/inválidas, erros de sintaxe, SLA >48h, JSON malformado, `MAX_ITERACOES`, arquivos ocultos, UI sem chave (48 testes). |
| **E2E** | `tests/e2e/test_e2e_tier3_combinations.py` | Tier 3 (Combinações): `somar` + ferramenta de domínio no mesmo loop, `tool_use_failed` por perfil, propagação `agent._cliente`/hiperparâmetros, UI + seletor, lote multi-tool (17 testes). |
| **E2E** | `tests/e2e/test_e2e_tier4_scenarios.py` | Tier 4 (Jornadas Ponta a Ponta): cenários multi-turno completos para Ada, Lint, Val, Organizador, Base e Streamlit UI (6 testes). |
| **E2E** | `tests/e2e/test_e2e_tier5_adversarial.py` | Tier 5 (Hardening Adversarial Caixa-Branca): cobertura de ramos PDF/DOCX/XLSX/CLI/UI/AST/match-case e regressões de bugs confirmados (`mover_arquivo` anti-sobrescrita/auto-inclusão/caminhos vazios/ponto/parent traversal `..`/espaços laterais/ancestral arquivo/symlink quebrado, FinOps `limite_caracteres`, rollback CLI `main()`, `mutacao_global` composto/`except`/`import`/`match-case`/shadowing em `lambda` e compreensões inclusive alvos `Subscript`/`Attribute`, fronteira de palavra KB/plurais e tokens Unicode NFC/NFD, aspas com espaços, credenciais com qualificadores de domínio e `fotos`/`identidades` na Val, isolamento de escopo/alvos/orelse/métodos de mutação/`del`/`except as`/`match-case` em `while` na Ada) (56 funções / 148 casos). |

**Totais Consolidados da Suíte (`pytest --collect-only -q tests/`):**
- **Unitários:** `244` testes (`16 + 48 + 43 + 38 + 99`)
- **Integração:** `42` testes (`2 + 1 + 39`)
- **UI:** `3` testes (`3`)
- **Evals:** `64` testes (`3 + 61`)
- **E2E (Tiers 1–5):** `277` testes (`58 + 48 + 17 + 6 + 148`)
- **Total Geral Coletado:** **`630` testes** (`100%` offline, `100%` de cobertura nos 8 módulos de produção: `agent.py`, `agent_core.py`, `agent_base.py`, `agent_ada.py`, `agent_lint.py`, `agent_val.py`, `agent_organizador.py`, `app.py`).

---

## 5. Metodologia em CI/CD, Comandos de Execução e Replay Determinístico (`vcrpy`)

Em engenharia de LLMOps, a avaliação contínua em esteiras de integração contínua (CI) enfrenta o dilema entre **custo/latência** e **fidelidade estocástica**:

1. **Abordagem Adotada no Pipeline (Prompt Contract Testing 100% Offline):**
   - Utilização de mocks determinísticos (`tests/conftest.py`: `mock_openai`, `criar_resposta_mock`, `criar_tool_call_mock`) que inspecionam o contrato da requisição enviada à OpenAI (`call_args_list`), validando a injeção do prompt de sistema do perfil ativo, a lista estritamente isolada de `tools`, a execução real das funções locais em sandbox/AST/KB e os retornos JSON em `role="tool"`.
   - **Vantagens:** Execução rápida e determinística, custo zero de tokens, 100% hermética e sem dependência de `OPENAI_API_KEY` real no GitHub Actions.

2. **Comandos de Validação Verbatim do Workflow `.github/workflows/deploy-azure.yml`:**
   O workflow de CI/CD executa em **Python 3.10** (`ubuntu-latest`) exatamente os comandos abaixo, bloqueando o deploy no Azure App Service em caso de falha:

   ```bash
   # 1. Lint crítico (para o build se houver erros graves de sintaxe ou variáveis indefinidas)
   flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

   # 2. Alertas de estilo (complexidade ciclomática <= 15 e comprimento máximo de linha <= 127)
   flake8 . --count --exit-zero --max-complexity=15 --max-line-length=127 --statistics

   # 3. Execução 100% offline de toda a suíte (Unitários, Integração, UI, Evals e E2E) com cobertura
   pytest tests/ --cov=./ --cov-report=xml
   ```

3. **Evolução para Ambientes de Produção (Replay Determinístico com `vcrpy` / `pytest-recording`):**
   - Para avaliar decisões reais de modelos estocásticos sem incorrer em custos contínuos a cada commit, a prática recomendada consiste em gravar requisições e respostas autênticas da OpenAI em cassetes YAML (`vcrpy`).
   - Os cassetes são versionados no repositório e o CI continua rodando offline reproduzindo as respostas gravadas.
   - Ao alterar os prompts em `agent.md`, `agent-ada.md`, `agent-lint.md`, `agent-val.md` ou `agent-organizador.md`, os engenheiros executam `pytest --record-mode=rewrite` com uma chave válida para atualizar os cassetes da suíte.
