# Plano de Testes de Avaliação (Eval) do Agente de IA

Este documento registra a estratégia, a metodologia e os **prompts de inteligência artificial** utilizados para a concepção e validação do plano de testes de avaliação do agente, atendendo aos requisitos da disciplina de **Deploy e CI/CD**.

---

## 1. Motivação e Diferença entre Testes Tradicionais e Evals

- **Testes Unitários e de Integração:** Validam se a infraestrutura do código (funções de soma, roteamento do Streamlit, serialização de JSON) funciona deterministicamente.
- **Testes de Avaliação (Eval):** Como os Modelos de Linguagem (LLMs) são probabilísticos, os Evals avaliam o **comportamento cognitivo e a segurança do agente**, garantindo:
  1. Que o agente escolhe as ferramentas certas para as tarefas pretendidas (*Tool Selection Accuracy*).
  2. Que o agente respeita as diretrizes de persona e escopo do `agent.md` sem acionar tools desnecessárias (*System Prompt Adherence*).
  3. Que o agente encerra a execução com mensagem amigável caso entre em loop ou atinja o teto de iterações (*Resilience & Loop Guardrails*).

---

## 2. Prompts Utilizados para Gerar o Plano de Testes

Seguindo o requisito: *"Utilize a IA para gerar esse plano. Apresente os prompts utilizados."*

### Prompt 1: Elaboração da Estratégia de Evals
```text
Atue como um Engenheiro de IA Sênior especialista em LLMOps e qualidade de software.
Temos um agente Python baseado na OpenAI com Function Calling (ferramenta somar) e interface Streamlit.
O agente possui um arquivo de sistema 'agent.md' e um loop que repete chamadas de ferramentas até responder ao usuário ou atingir MAX_ITERACOES.
Elabore um plano de testes de avaliação (Evals) automatizados para validar a qualidade, o comportamento e a confiabilidade do agente em uma esteira de CI/CD (GitHub Actions), sem depender de chamadas reais de API (utilizando mocks determinísticos).
```

### Prompt 2: Engenharia de Casos de Teste (Pytest)
```text
Com base no plano de avaliação anterior, crie os casos de teste em Pytest para o arquivo tests/eval/test_eval.py.
Os testes devem cobrir:
1. Eval de Intenção e Tool Selection: Quando o usuário solicita uma soma exata, o LLM deve emitir a chamada de ferramenta 'somar' e o agente deve incorporar o resultado na resposta final.
2. Eval de Aderência à Identidade: Quando o usuário faz uma pergunta de apresentação ('Quem é você?'), o agente deve responder diretamente em texto, sem acionar nenhuma ferramenta desnecessariamente.
3. Eval de Resiliência a Loops: Se o modelo entrar em um ciclo contínuo de chamadas de ferramentas, o agente deve interromper a execução ao atingir MAX_ITERACOES e retornar uma mensagem amigável de erro.
```

---

## 3. Matriz de Cobertura dos Evals Implementados

| Teste | Arquivo | O que valida | Critério de Sucesso |
| :--- | :--- | :--- | :--- |
| `test_eval_selecao_de_ferramenta_matematica` | `tests/eval/test_eval.py` | Tool Selection | Dispara a tool `somar`, extrai o retorno e inclui o cálculo na resposta. |
| `test_eval_aderencia_a_identidade_sem_tools` | `tests/eval/test_eval.py` | Prompt Adherence | Responde em linguagem natural sem chamar ferramentas espúrias. |
| `test_eval_resiliencia_a_estouro_de_iteracoes` | `tests/eval/test_eval.py` | Safety & Loops | Interrompe no teto de iterações sem quebrar a execução (`crash`). |

Todos os 8 testes (Unitários + Evals) rodam em menos de 5 segundos no pipeline de CI/CD.
