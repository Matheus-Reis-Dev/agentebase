"""Testes de Interface (UI) com Streamlit AppTest.

Conceito Didático para CI/CD:
O `AppTest` (Streamlit 1.28+) executa o script do app em uma thread em memória sem navegador real,
permitindo simular interações de componentes e validar tanto o estado interno (session_state)
quanto a árvore de widgets visuais renderizados.
"""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
import agent

# Caminho absoluto para app.py para rodar o AppTest de qualquer lugar
APP_PATH = str(Path(__file__).parent.parent.parent / "app.py")


@pytest.fixture
def app_test():
    """Inicializa o AppTest para app.py com default_timeout=10 para prevenir falhas de cold-start no CI."""
    return AppTest.from_file(APP_PATH, default_timeout=10)


def test_app_inicializacao(monkeypatch, app_test):
    """Verifica se o app Streamlit renderiza sem erros visuais e exibe o título correto."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    at = app_test.run()

    # Valida se rodou e não gerou exceções não tratadas nem alertas visuais de erro
    assert not at.exception
    assert len(at.error) == 0, f"Erros visuais encontrados: {[e.value for e in at.error]}"

    # Valida o título do projeto
    assert at.title[0].value == "🤖 Agente base"


def test_app_input_usuario(monkeypatch, app_test):
    """Testa a interação do chat validando mensagens técnicas, tela visual e ausência de erros."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")

    # Mock que replica o contrato real de agent.responder: muta mensagens in-place e retorna texto
    def responder_mock(mensagens):
        mensagens.append({"role": "assistant", "content": "Ola! Como posso ajudar?"})
        return "Ola! Como posso ajudar?"

    monkeypatch.setattr(agent, "responder", responder_mock)

    at = app_test.run()

    # Simula o envio de mensagem pelo usuário no componente chat_input
    at.chat_input[0].set_value("Ola App").run()

    # 1. Valida ausência total de erros visuais na interface
    assert len(at.error) == 0, f"Erros visuais inesperados: {[e.value for e in at.error]}"

    # 2. Valida o histórico técnico de mensagens (consumido pela API LLM) por índice direto
    historico = at.session_state["mensagens"]
    assert len(historico) == 3
    assert historico[1] == {"role": "user", "content": "Ola App"}
    assert historico[2] == {"role": "assistant", "content": "Ola! Como posso ajudar?"}

    # 3. Valida a lista visual de tela (consumida para exibição humana na interface)
    assert at.session_state["tela"] == [
        ("user", "Ola App"),
        ("assistant", "Ola! Como posso ajudar?"),
    ]


def test_app_falha_sem_chave(monkeypatch, app_test):
    """Testa o comportamento visual (st.error) caso agent.get_cliente() lance RuntimeError por falta de chave."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Isola a alteração do singleton via monkeypatch para garantir teardown automático
    monkeypatch.setattr(agent, "_cliente", None)

    at = app_test.run()

    # O AppTest deve renderizar o erro e abortar via st.stop(), exibindo o bloco de erro
    assert len(at.error) > 0
    assert "OPENAI_API_KEY" in at.error[0].value
