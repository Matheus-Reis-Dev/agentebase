"""Ponto de entrada raiz do conftest para o Pytest em agentebase.

Reexporta todas as fixtures e utilitários de tests/conftest.py para garantir descoberta universal.
"""

from tests.conftest import (  # noqa: F401
    mock_openai,
    mock_llm_eval,
    criar_mock_resposta_texto,
    criar_mock_resposta_tool_call,
    criar_mock_resposta_multiplas_tools,
    criar_resposta_mock,
    criar_tool_call_mock,
    mock_factory,
    app_test,
)
