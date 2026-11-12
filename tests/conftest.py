"""Fixtures globais e utilitários compartilhados para a suíte de testes do agente.

Centraliza mocks e fábricas (Helper Factories) para o cliente OpenAI e o Streamlit AppTest,
garantindo testes herméticos, determinísticos e de alta manutenibilidade (DRY).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from streamlit.testing.v1 import AppTest
import agent

# Caminho absoluto para app.py acessível por qualquer teste
APP_PATH = str(Path(__file__).parent.parent / "app.py")


# ==============================================================================
# FIXTURES DE ISOLAMENTO DO CLIENTE OPENAI
# ==============================================================================

@pytest.fixture
def mock_openai(monkeypatch):
    """Fixture centralizada para mockar o cliente OpenAI, prevenindo chamadas reais e custos de API.

    Garante isolamento hermético com restauração automática de estado via monkeypatch.
    """
    mock_cliente = MagicMock()
    monkeypatch.setattr(agent, "_cliente", mock_cliente)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key-para-testes-ci")
    return mock_cliente


@pytest.fixture
def mock_llm_eval(mock_openai):
    """Alias retrocompatível da fixture de mock para testes em test_eval.py."""
    return mock_openai


# ==============================================================================
# HELPER FACTORIES PARA GERAÇÃO DE MOCKS OPENAI
# ==============================================================================

def criar_mock_resposta_texto(conteudo: str) -> MagicMock:
    """Cria mock de resposta da OpenAI contendo apenas mensagem de texto (sem tool calls)."""
    mock_resposta = MagicMock()
    mock_resposta.choices[0].message.tool_calls = None
    mock_resposta.choices[0].message.content = conteudo
    mock_resposta.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "content": conteudo,
    }
    return mock_resposta


def criar_mock_resposta_tool_call(
    nome: str,
    argumentos: dict | str = "{}",
    call_id: str = "call_123"
) -> MagicMock:
    """Cria mock de resposta da OpenAI solicitando a execução de uma ferramenta (Tool Call)."""
    args_str = json.dumps(argumentos) if isinstance(argumentos, dict) else argumentos

    mock_tool_call = MagicMock()
    mock_tool_call.id = call_id
    mock_tool_call.function.name = nome
    mock_tool_call.function.arguments = args_str

    mock_resposta = MagicMock()
    mock_resposta.choices[0].message.content = None
    mock_resposta.choices[0].message.tool_calls = [mock_tool_call]
    mock_resposta.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": nome, "arguments": args_str},
            }
        ],
    }
    return mock_resposta


def criar_mock_resposta_multiplas_tools(chamadas_info: list[dict]) -> MagicMock:
    """Cria mock de resposta com múltiplas chamadas de ferramentas simultâneas."""
    mock_tool_calls = []
    dump_tool_calls = []

    for idx, info in enumerate(chamadas_info):
        call_id = info.get("id", f"call_{idx + 1}")
        nome = info["nome"]
        args = info.get("argumentos", {})
        args_str = json.dumps(args) if isinstance(args, dict) else args

        tc = MagicMock()
        tc.id = call_id
        tc.function.name = nome
        tc.function.arguments = args_str
        mock_tool_calls.append(tc)

        dump_tool_calls.append({
            "id": call_id,
            "type": "function",
            "function": {"name": nome, "arguments": args_str},
        })

    mock_resposta = MagicMock()
    mock_resposta.choices[0].message.content = None
    mock_resposta.choices[0].message.tool_calls = mock_tool_calls
    mock_resposta.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "tool_calls": dump_tool_calls,
    }
    return mock_resposta


@pytest.fixture
def criar_resposta_mock():
    """Fábrica de respostas simuladas da OpenAI para testes de integração, loop e evals.

    Elimina boilerplate e sincroniza automaticamente os atributos do mock com o model_dump().
    """
    def _factory(content: str | None = None, tool_calls: list | None = None):
        mock_resposta = MagicMock()
        mensagem = mock_resposta.choices[0].message
        mensagem.content = content
        mensagem.tool_calls = tool_calls
        if tool_calls:
            mensagem.model_dump.return_value = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        else:
            mensagem.model_dump.return_value = {
                "role": "assistant",
                "content": content,
            }
        return mock_resposta

    return _factory


@pytest.fixture
def criar_tool_call_mock():
    """Fábrica auxiliar para criar objetos simulados de tool_call com id, nome e argumentos."""
    def _factory(call_id: str, name: str, arguments: str = "{}"):
        tc = MagicMock()
        tc.id = call_id
        tc.function.name = name
        tc.function.arguments = arguments
        return tc

    return _factory


@pytest.fixture
def mock_factory():
    """Disponibiliza as funções helper de mock via injeção de dependência."""
    return {
        "texto": criar_mock_resposta_texto,
        "tool_call": criar_mock_resposta_tool_call,
        "multiplas_tools": criar_mock_resposta_multiplas_tools,
    }


# ==============================================================================
# FIXTURE PARA STREAMLIT APPTEST
# ==============================================================================

@pytest.fixture
def app_test():
    """Inicializa o AppTest para app.py com default_timeout=10 para prevenir falhas de cold-start no CI."""
    return AppTest.from_file(APP_PATH, default_timeout=10)
