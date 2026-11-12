# Plano de Testes de Avaliação (Eval) do Agente de IA — Organizador de Arquivos

Este documento registra a estratégia, a metodologia e os **prompts de inteligência artificial** utilizados para a concepção e validação do plano de testes de avaliação do agente, atendendo aos requisitos da disciplina de **Deploy e CI/CD** (MBA FIAP).

---

## 1. Motivação e Diferença entre Testes Tradicionais e Evals

- **Testes Unitários e de Integração:** Validam se a infraestrutura do código (funções de sistema de arquivos como listar, mover e ler metadados, roteamento do Streamlit, serialização de JSON) funciona deterministicamente.
- **Testes de Avaliação (Eval):** Como os Modelos de Linguagem (LLMs) são probabilísticos, os Evals avaliam o **comportamento cognitivo, alinhamento de contrato e a segurança do agente**, garantindo:
  1. Que o agente escolhe as ferramentas certas para as tarefas pretendidas (*Tool Selection Accuracy*), validando o formato estruturado JSON do retorno.
  2. Que o agente respeita as diretrizes de persona e escopo do `agent.md` sem acionar tools desnecessárias (*System Prompt Adherence*).
  3. Que o agente encerra a execução com mensagem amigável caso entre em loop ou atinja o teto de iterações (*Resilience & Loop Guardrails / Circuit Breaker*).

---

## 2. Prompts Utilizados para Gerar o Plano de Testes

Seguindo o requisito: *"Utilize a IA para gerar esse plano. Apresente os prompts utilizados."*

### Prompt 1: Elaboração da Estratégia de Evals
```text
Atue como um Engenheiro de IA Sênior especialista em LLMOps e qualidade de software.
Temos um agente Python baseado na OpenAI com Function Calling (ferramentas de manipulação de arquivos: listar_arquivos, obter_metadados_arquivo, criar_pasta, mover_arquivo) e interface Streamlit.
O agente possui um arquivo de sistema 'agent.md' e um loop que repete chamadas de ferramentas até responder ao usuário ou atingir MAX_ITERACOES.
Elabore um plano de testes de avaliação (Evals) automatizados para validar a qualidade, o comportamento e a confiabilidade do agente em uma esteira de CI/CD (GitHub Actions), sem depender de chamadas reais de API (utilizando mocks determinísticos e testes de contrato de prompt).
```

### Prompt 2: Engenharia de Casos de Teste (Pytest)
```text
Com base no plano de avaliação anterior, crie os casos de teste em Pytest para o arquivo tests/eval/test_eval.py.
Os testes devem cobrir:
1. Eval de Intenção e Tool Selection: Quando o usuário solicita organizar arquivos em uma pasta, o agente deve disponibilizar e acionar a ferramenta 'listar_arquivos', garantindo que o retorno JSON contenha a chave estruturada 'arquivos' e seja integrado no histórico.
2. Eval de Aderência à Identidade: Quando o usuário faz uma pergunta de apresentação ('Quem é você e o que você faz?'), o agente deve responder diretamente em texto, sem acionar nenhuma ferramenta desnecessariamente (assert tools == [] com mensagem explicativa rica).
3. Eval de Resiliência a Loops: Se o modelo entrar em um ciclo contínuo de chamadas de ferramentas, o agente deve interromper a execução com segurança ao atingir MAX_ITERACOES (Circuit Breaker) e retornar uma mensagem amigável de erro.
```

---

## 3. Matriz de Cobertura dos Evals Implementados

| Teste | Arquivo | Dimensão de Qualidade | Critério de Sucesso |
| :--- | :--- | :--- | :--- |
| `test_eval_selecao_de_ferramenta_arquivos` | `tests/eval/test_eval.py` | Tool Selection & Contract | Valida contrato de prompt de sistema (`agent.md`), envio da tool `listar_arquivos` e formato estruturado JSON com a chave `'arquivos'`. |
| `test_eval_aderencia_a_identidade_sem_tools` | `tests/eval/test_eval.py` | Prompt Adherence | Responde em linguagem natural sem acionar ferramentas espúrias (`assert tools == [], f"..."`). |
| `test_eval_resiliencia_a_estouro_de_iteracoes` | `tests/eval/test_eval.py` | Safety & Circuit Breaker | Interrompe no teto de `MAX_ITERACOES` sem crash, prevenindo Token Bleeding e retornando mensagem de recuperação. |

---

## 4. Metodologia de Evals em CI/CD: Contratos de Prompt vs. Replay Determinístico (vcrpy)

Em engenharia de LLMOps, a avaliação contínua em esteiras de integração contínua (CI) enfrenta o dilema entre **custo/latência** e **fidelidade estocástica**:

1. **Abordagem Adotada no Pipeline de Demonstração (Prompt Contract Testing):**
   - Utilização de mocks determinísticos que inspecionam o contrato da requisição (`mock.call_args_list`): validação se o prompt de sistema (`agent.md`) foi injetado, se as ferramentas estão disponíveis e se os formatos de retorno JSON são respeitados.
   - **Vantagens:** Execução ultrarrápida (< 5 segundos), custo zero de tokens, hermético e sem dependência de credenciais no GitHub Actions.

2. **Evolução para Ambientes de Produção (Replay Determinístico com `vcrpy` / `pytest-recording`):**
   - Para avaliar decisões reais de modelos estocásticos sem incorrer em custos contínuos a cada commit, a prática recomendada da indústria consiste em gravar requisições e respostas autênticas da OpenAI em cassetes YAML (`vcrpy`).
   - Os cassetes são versionados no repositório. O CI roda offline reproduzindo a tomada de decisão autêntica da IA gravada na fita.
   - Ao alterar os prompts em `agent.md`, os engenheiros executam `pytest --record-mode=rewrite` com uma API key válida para atualizar a suíte de avaliação.
