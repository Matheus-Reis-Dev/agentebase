import json
import pytest
import agent
from pathlib import Path

def test_somar():
    """Testa a ferramenta matemática básica isoladamente."""
    resultado = agent.somar(2.0, 3.5)
    assert resultado == {"resultado": 5.5}

def test_executar_ferramenta_sucesso():
    """Verifica a conversão de ferramentas nativas para JSON."""
    resultado_json = agent.executar_ferramenta("somar", {"a": 10, "b": 20})
    assert json.loads(resultado_json) == {"resultado": 30.0}

def test_executar_ferramenta_inexistente():
    """Valida o fallback quando o modelo alucina uma ferramenta."""
    resultado_json = agent.executar_ferramenta("ferramenta_fantasma", {})
    resultado = json.loads(resultado_json)
    assert "erro" in resultado
    assert "não existe" in resultado["erro"]

def test_carregar_contexto(tmp_path, monkeypatch):
    """Testa a junção dos arquivos de contexto usando arquivos temporários."""
    # Aponta as constantes do agent.py para um diretório temporário isolado
    arquivo_agent = tmp_path / "agent.md"
    arquivo_memory = tmp_path / "memory.md"
    
    arquivo_agent.write_text("Sou um bot de testes.", encoding="utf-8")
    arquivo_memory.write_text("O usuario se chama Fabiano.", encoding="utf-8")
    
    monkeypatch.setattr(agent, "AGENT_MD", arquivo_agent)
    monkeypatch.setattr(agent, "MEMORY_MD", arquivo_memory)
    
    contexto = agent.carregar_contexto()
    assert "Sou um bot de testes." in contexto
    assert "# Memória" in contexto
    assert "O usuario se chama Fabiano." in contexto

def test_get_cliente_sem_chave(monkeypatch):
    """Garante que a falta de chave cause falha clara na inicialização."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    agent._cliente = None  # Reseta o Singleton
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY não encontrada"):
        agent.get_cliente()
