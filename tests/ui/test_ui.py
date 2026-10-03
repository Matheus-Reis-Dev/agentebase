import pytest
from streamlit.testing.v1 import AppTest
from pathlib import Path

# Caminho absoluto para app.py para rodar o AppTest de qualquer lugar
APP_PATH = str(Path(__file__).parent.parent.parent / "app.py")

def test_app_inicializacao(monkeypatch):
    """Verifica se o app Streamlit renderiza sem erros graves."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    at = AppTest.from_file(APP_PATH)
    at.run()
    
    # Valida se rodou e não gerou Exceções na tela
    assert not at.exception
    
    # Valida o título do projeto
    assert at.title[0].value == "🤖 Agente base"

def test_app_input_usuario(monkeypatch):
    """Testa a interação simulando um input de usuário via chat."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    at = AppTest.from_file(APP_PATH)
    at.run()
    
    # Pega o componente chat_input e simula envio de "Olá App"
    at.chat_input[0].set_value("Olá App").run()
    
    # Valida que o session_state ('mensagens') guardou o input do usuário
    historico = at.session_state["mensagens"]
    assert any(msg["role"] == "user" and msg["content"] == "Olá App" for msg in historico)

def test_app_falha_sem_chave(monkeypatch):
    """Testa o comportamento visual (st.error) caso caia no except KeyError do agent."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    import agent
    agent._cliente = None # Reseta o Singleton globalmente antes do run()
    
    at = AppTest.from_file(APP_PATH)
    at.run()
    
    # O AppTest deve renderizar o erro, chamando st.stop() ou similar
    # Deve haver um bloco 'error' renderizado na tela
    assert len(at.error) > 0
    assert "OPENAI_API_KEY não encontrada" in at.error[0].value
