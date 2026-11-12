"""MÓDULO DE AVALIAÇÃO DE COMPORTAMENTO DO AGENTE (LLM EVALS).

CONTEXTO PEDAGÓGICO E METODOLÓGICO (CI/CD para IA Generativa):
Diferença fundamental entre as suítes de teste do projeto:
- tests/unit/        -> Valida funções determinísticas e puras (I/O, strings, helpers).
- tests/integration/ -> Valida a comunicação entre módulos e o loop ReAct do agente.
- tests/eval/        -> Avalia os pilares cognitivos e guardrails do Agente:
    1. Tool Selection Contract: Valida se a intenção do usuário dispara a ferramenta
       adequada (listar_arquivos) e preserva o contrato estruturado de JSON.
    2. Persona & Prompt Adherence: Valida que saudações e dúvidas teóricas não acionam
       ferramentas do sistema de arquivos indevidamente (assert tools == []).
    3. Loop Guardrails & Circuit Breakers: Valida que ciclos contínuos de ferramentas
       são contidos pelo teto de MAX_ITERACOES sem travamento (crash) da aplicação.

NOTA DE ENGENHARIA DE LLMOps (Mocks vs. Gravação Replay):
Em esteiras de CI/CD rápidas (< 5 segundos) e herméticas, executamos Testes de Contrato de
Prompt sem custo de API. Em esteiras de produção avançadas, recomenda-se complementar com
gravação de chamadas reais via cassetes determinísticos (pytest-recording / vcrpy) ou
avaliações automáticas com Golden Datasets (DeepEval / promptfoo).
"""

import json
from unittest.mock import MagicMock
import pytest
import agent


@pytest.fixture
def mock_llm_eval(monkeypatch):
    """Injeta um mock do cliente OpenAI garantindo isolamento hermético entre testes.

    MECÂNICA DIDÁTICA DO PYTEST:
    1. 'agent._cliente' atua como um Singleton global em memória.
    2. Atribuições diretas manuais ('agent._cliente = mock') vazariam o estado mockado
       para testes subsequentes, violando a independência dos testes.
    3. O 'monkeypatch.setattr' substitui o objeto exclusivamente durante a execução
       deste teste e restaura o estado original automaticamente no teardown da fixture.
    """
    mock_cliente = MagicMock()
    monkeypatch.setattr(agent, "_cliente", mock_cliente)
    return mock_cliente


def test_eval_selecao_de_ferramenta_arquivos(mock_llm_eval, tmp_path):
    """EVAL 1: Intenção de organizar arquivos deve disparar tool_call 'listar_arquivos'.

    Critérios Avaliados:
    - Contrato de Prompt: O agente transmite a persona de 'agent.md' e disponibiliza 'listar_arquivos'.
    - Formato Estruturado: O retorno da ferramenta deve conter a chave JSON 'arquivos' (lista).
    """
    # [Arrange]
    # Simula resposta do Turno 1: LLM decide chamar a ferramenta 'listar_arquivos'
    call_mock = MagicMock()
    call_mock.id = "call_eval_1"
    call_mock.function.name = "listar_arquivos"
    call_mock.function.arguments = json.dumps({"diretorio": str(tmp_path)})

    mock_resposta_ferramenta = MagicMock()
    mock_resposta_ferramenta.choices[0].message.content = None
    mock_resposta_ferramenta.choices[0].message.tool_calls = [call_mock]
    mock_resposta_ferramenta.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "tool_calls": [{
            "id": "call_eval_1",
            "function": {"name": "listar_arquivos", "arguments": json.dumps({"diretorio": str(tmp_path)})}
        }]
    }

    # Simula resposta do Turno 2: LLM recebe o resultado e sintetiza a resposta final
    mock_resposta_final = MagicMock()
    mock_resposta_final.choices[0].message.tool_calls = None
    mock_resposta_final.choices[0].message.content = (
        "Analisei os arquivos no diretório e proponho a hierarquia por ano e tema."
    )

    # side_effect gerencia a sequência de turnos do padrão ReAct
    mock_llm_eval.chat.completions.create.side_effect = [mock_resposta_ferramenta, mock_resposta_final]

    historico = [
        {"role": "system", "content": agent.carregar_contexto()},
        {"role": "user", "content": f"Organize os arquivos que estão na pasta {tmp_path}."}
    ]

    # [Act]
    resposta = agent.responder(historico)

    # [Assert: Validação do Contrato de Prompt e Parâmetros da OpenAI]
    assert mock_llm_eval.chat.completions.create.call_count == 2, (
        "EVAL FALHOU: O ciclo ReAct completo deve realizar 2 chamadas à API (1 tool_call + 1 resposta final)."
    )

    # Inspeciona a requisição enviada no Turno 1
    args_t1, kwargs_t1 = mock_llm_eval.chat.completions.create.call_args_list[0]
    assert kwargs_t1["model"] == agent.MODELO
    assert kwargs_t1["temperature"] == agent.TEMPERATURA

    # Valida que o prompt de sistema contém a identidade obrigatória do Organizador de Arquivos
    mensagens_enviadas = kwargs_t1["messages"]
    system_prompt = next((m["content"] for m in mensagens_enviadas if m.get("role") == "system"), "")
    assert "Organizador de Arquivos" in system_prompt, (
        "EVAL FALHOU: O system prompt enviado à OpenAI não contém a identidade definida em agent.md."
    )
    assert any(t["function"]["name"] == "listar_arquivos" for t in kwargs_t1["tools"]), (
        "EVAL FALHOU: A ferramenta 'listar_arquivos' não foi disponibilizada no payload da chamada."
    )

    # [Assert: Validação Estruturada do Retorno da Ferramenta]
    tool_messages = [m for m in historico if m.get("role") == "tool"]
    assert len(tool_messages) >= 1, "EVAL FALHOU: O agente deveria ter registrado a mensagem da ferramenta no histórico."

    # Parseamento formal do JSON retornado pela ferramenta executada
    conteudo_tool = json.loads(tool_messages[0]["content"])
    assert "arquivos" in conteudo_tool, (
        f"EVAL FALHOU: Retorno da ferramenta não contém 'arquivos'. Dados: {conteudo_tool}"
    )
    assert "total_encontrados" in conteudo_tool, (
        f"EVAL FALHOU: Retorno da ferramenta não contém 'total_encontrados'. Dados: {conteudo_tool}"
    )
    assert isinstance(conteudo_tool["arquivos"], list), (
        f"EVAL FALHOU: O campo 'arquivos' deve ser uma lista, obtido: {type(conteudo_tool['arquivos'])}"
    )

    # Valida integridade do encerramento
    assert len(resposta.strip()) > 0, "EVAL FALHOU: A resposta final do assistente não deve ser vazia."
    assert historico[-1]["role"] == "assistant"
    assert historico[-1]["content"] == resposta


def test_eval_aderencia_a_identidade_sem_tools(mock_llm_eval):
    """EVAL 2: Pergunta sobre identidade deve ser respondida diretamente em texto.

    Critério: Não deve acionar ferramentas de sistema de arquivos para saudações ou dúvidas conceituais.
    """
    # [Arrange]
    mock_resposta = MagicMock()
    mock_resposta.choices[0].message.tool_calls = None
    mock_resposta.choices[0].message.content = "Eu sou um assistente especializado em organizar e gerenciar arquivos."
    mock_llm_eval.chat.completions.create.return_value = mock_resposta

    historico = [
        {"role": "system", "content": agent.carregar_contexto()},
        {"role": "user", "content": "Quem é você e o que você faz?"}
    ]

    # [Act]
    resposta = agent.responder(historico)

    # [Assert: Validação do Contrato de Prompt e Ausência de Ferramentas]
    _, kwargs = mock_llm_eval.chat.completions.create.call_args
    mensagens_enviadas = kwargs["messages"]
    system_prompt = next((m["content"] for m in mensagens_enviadas if m.get("role") == "system"), "")
    assert "Organizador de Arquivos" in system_prompt, (
        "EVAL FALHOU: Prompt de sistema não continha a persona de Organizador de Arquivos."
    )

    assert len(resposta.strip()) > 0, "EVAL FALHOU: Resposta vazia para pergunta de apresentação."

    # Asserção rica com mensagem explicativa detalhada
    tools = [m for m in historico if m.get("role") == "tool"]
    assert tools == [], (
        "EVAL FALHOU: Nenhuma ferramenta deveria ser chamada para perguntas de apresentação/identidade. "
        f"Ferramentas acionadas indevidamente: {tools}"
    )


def test_eval_resiliencia_a_estouro_de_iteracoes(mock_llm_eval, monkeypatch):
    """EVAL 3: Resiliência Operacional e Circuit Breaker contra Loops Infinitos de Ferramentas.

    MOTIVAÇÃO PEDAGÓGICA (SRE / FinOps):
    Modelos de IA estocásticos podem entrar em ciclos viciosos de ferramentas se não
    compreenderem uma resposta intermediária. O Circuit Breaker (MAX_ITERACOES) evita o
    esgotamento financeiro de tokens (Token Bleeding) e travamento de threads.
    """
    # [Arrange]
    # Isola os executores para não realizar chamadas reais de sistema de arquivos no loop
    monkeypatch.setitem(agent.EXECUTORES, "obter_pastas_padrao", lambda **kwargs: json.dumps({"status": "mock_loop"}))

    mock_loop = MagicMock()
    mock_loop.choices[0].message.content = None
    call_infinito = MagicMock()
    call_infinito.id = "loop_call"
    call_infinito.function.name = "obter_pastas_padrao"
    call_infinito.function.arguments = "{}"
    mock_loop.choices[0].message.tool_calls = [call_infinito]
    mock_loop.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "tool_calls": [{"id": "loop_call", "function": {"name": "obter_pastas_padrao", "arguments": "{}"}}]
    }

    mock_llm_eval.chat.completions.create.return_value = mock_loop

    historico = [
        {"role": "system", "content": agent.carregar_contexto()},
        {"role": "user", "content": "Rode em loop eterno."}
    ]

    # [Act]
    resposta = agent.responder(historico)

    # [Assert]
    assert mock_llm_eval.chat.completions.create.call_count == agent.MAX_ITERACOES, (
        f"EVAL FALHOU: O loop deveria ter parado exatamente em MAX_ITERACOES ({agent.MAX_ITERACOES}). "
        f"Chamadas realizadas: {mock_llm_eval.chat.completions.create.call_count}"
    )
    assert "limite de iterações sem concluir" in resposta.lower() and "reformular" in resposta.lower(), (
        f"EVAL FALHOU: Mensagem de encerramento amigável ausente ou truncada. Resposta: {resposta}"
    )
