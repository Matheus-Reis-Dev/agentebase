import pytest
from unittest.mock import MagicMock
import agent

@pytest.fixture
def mock_openai(monkeypatch):
    """Cria um mock robusto do cliente da OpenAI para não gastar API Key."""
    mock_cliente = MagicMock()
    # injeta o mock na variável Singleton
    monkeypatch.setattr(agent, "_cliente", mock_cliente)
    return mock_cliente

def test_responder_texto_simples(mock_openai):
    """Testa o caso em que o LLM responde apenas com texto (sem usar ferramentas)."""
    # Configura o comportamento do mock
    mock_resposta = MagicMock()
    mock_resposta.choices[0].message.tool_calls = None
    mock_resposta.choices[0].message.content = "Olá, eu sou um assistente!"
    
    mock_openai.chat.completions.create.return_value = mock_resposta
    
    mensagens = [{"role": "user", "content": "Oi"}]
    resultado = agent.responder(mensagens)
    
    assert resultado == "Olá, eu sou um assistente!"
    assert len(mensagens) == 2  # Adicionou a resposta do assistente ao histórico
    assert mensagens[-1]["role"] == "assistant"

def test_responder_com_ferramenta(mock_openai):
    """Testa o loop do agente: pede ferramenta -> executa -> responde resultado."""
    
    # 1ª Interação: LLM pede para chamar 'somar'
    mock_resposta_1 = MagicMock()
    mock_resposta_1.choices[0].message.content = None
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "somar"
    mock_tool_call.function.arguments = '{"a": 2, "b": 3}'
    mock_resposta_1.choices[0].message.tool_calls = [mock_tool_call]
    mock_resposta_1.choices[0].message.model_dump.return_value = {
        "role": "assistant", "tool_calls": [{"id": "call_123", "function": {"name": "somar", "arguments": '{"a": 2, "b": 3}'}}]
    }
    
    # 2ª Interação: LLM dá a resposta final lendo o resultado da ferramenta
    mock_resposta_2 = MagicMock()
    mock_resposta_2.choices[0].message.tool_calls = None
    mock_resposta_2.choices[0].message.content = "O resultado é 5."
    
    # side_effect permite retornar valores diferentes nas chamadas subsequentes
    mock_openai.chat.completions.create.side_effect = [mock_resposta_1, mock_resposta_2]
    
    mensagens = [{"role": "user", "content": "Some 2 com 3"}]
    resultado = agent.responder(mensagens)
    
    assert resultado == "O resultado é 5."
    
    # Valida se o histórico (mensagens) cresceu corretamente:
    # 1. User (Original)
    # 2. Assistant (Tool Call)
    # 3. Tool (Resultado = 5.0)
    # 4. Assistant (Resposta Final)
    assert len(mensagens) == 4
    assert mensagens[1]["role"] == "assistant"
    assert mensagens[2]["role"] == "tool"
    assert "5" in mensagens[2]["content"]
    assert mensagens[3]["role"] == "assistant"
