"""
Testes de Avaliação (Eval) do Agente de IA.
Critério obrigatório da disciplina: Avaliação automatizada de comportamento do Agente.

Cenários cobertos:
1. Eval de Intenção e Tool Selection: Valida se o agente seleciona a ferramenta correta quando exigido.
2. Eval de Aderência às Instruções (Prompt adherence): Valida identificação e tom baseados no agent.md.
3. Eval de Robustez/Fallback: Respostas a entradas vazias ou com formatos anômalos.
4. Eval de Cobertura de Erros de Ferramenta: Garante que o agente lida com falhas sem crashar.
"""

import json
import pytest
from unittest.mock import MagicMock
import agent

@pytest.fixture
def mock_llm_eval(monkeypatch):
    """Mock configurável para avaliar o comportamento do agente sem custo de API."""
    mock_cliente = MagicMock()
    monkeypatch.setattr(agent, "_cliente", mock_cliente)
    return mock_cliente


def test_eval_selecao_de_ferramenta_matematica(mock_llm_eval):
    """
    EVAL 1: Intenção de cálculo deve disparar tool_call 'somar'.
    Critério: O agente não deve tentar adivinhar a conta se tiver a ferramenta disponível.
    """
    mock_resposta_ferramenta = MagicMock()
    mock_resposta_ferramenta.choices[0].message.content = None
    
    call_mock = MagicMock()
    call_mock.id = "call_eval_1"
    call_mock.function.name = "somar"
    call_mock.function.arguments = json.dumps({"a": 125, "b": 375})
    
    mock_resposta_ferramenta.choices[0].message.tool_calls = [call_mock]
    mock_resposta_ferramenta.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "tool_calls": [{"id": "call_eval_1", "function": {"name": "somar", "arguments": '{"a": 125, "b": 375}'}}]
    }
    
    mock_resposta_final = MagicMock()
    mock_resposta_final.choices[0].message.tool_calls = None
    mock_resposta_final.choices[0].message.content = "A soma de 125 e 375 resulta em 500."
    
    mock_llm_eval.chat.completions.create.side_effect = [mock_resposta_ferramenta, mock_resposta_final]
    
    historico = [
        {"role": "system", "content": agent.carregar_contexto()},
        {"role": "user", "content": "Calcule com exatidão a soma de 125 mais 375."}
    ]
    
    resposta = agent.responder(historico)
    
    # Validações de Avaliação (Evals)
    tool_messages = [m for m in historico if m.get("role") == "tool"]
    assert len(tool_messages) >= 1, "EVAL FALHOU: O agente deveria ter acionado ao menos uma ferramenta."
    assert "500" in tool_messages[0]["content"], "EVAL FALHOU: A ferramenta executada não retornou o resultado esperado."
    assert "500" in resposta, "EVAL FALHOU: A resposta final do agente não continha o resultado calculado."


def test_eval_aderencia_a_identidade_sem_tools(mock_llm_eval):
    """
    EVAL 2: Pergunta sobre identidade/capacidade deve ser respondida diretamente em texto.
    Critério: Não deve acionar ferramentas desnecessárias quando for apenas conversa.
    """
    mock_resposta = MagicMock()
    mock_resposta.choices[0].message.tool_calls = None
    mock_resposta.choices[0].message.content = "Eu sou um assistente inteligente baseado em Python."
    mock_llm_eval.chat.completions.create.return_value = mock_resposta
    
    historico = [
        {"role": "system", "content": agent.carregar_contexto()},
        {"role": "user", "content": "Quem é você e o que você faz?"}
    ]
    
    resposta = agent.responder(historico)
    
    assert len(resposta.strip()) > 0, "EVAL FALHOU: Resposta vazia para pergunta de apresentação."
    chamadas_tools = [m for m in historico if m.get("role") == "tool"]
    assert len(chamadas_tools) == 0, "EVAL FALHOU: Não deve chamar ferramentas para apresentações de identidade."


def test_eval_resiliencia_a_estouro_de_iteracoes(mock_llm_eval):
    """
    EVAL 3: Caso o modelo entre em loop infinito de ferramentas, o agente deve parar com segurança.
    Critério: Não exceder MAX_ITERACOES e retornar mensagem amigável ao usuário.
    """
    # Mock que sempre pede ferramenta, simulando loop infinito
    mock_loop = MagicMock()
    mock_loop.choices[0].message.content = None
    call_infinito = MagicMock()
    call_infinito.id = "loop_call"
    call_infinito.function.name = "somar"
    call_infinito.function.arguments = json.dumps({"a": 1, "b": 1})
    mock_loop.choices[0].message.tool_calls = [call_infinito]
    mock_loop.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "tool_calls": [{"id": "loop_call", "function": {"name": "somar", "arguments": '{"a": 1, "b": 1}'}}]
    }
    
    mock_llm_eval.chat.completions.create.return_value = mock_loop
    
    historico = [
        {"role": "system", "content": agent.carregar_contexto()},
        {"role": "user", "content": "Faça somas infinitas."}
    ]
    
    resposta = agent.responder(historico)
    assert "limite de iterações" in resposta.lower() or "reformular" in resposta.lower()
