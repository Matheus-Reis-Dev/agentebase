"""Fixtures e utilitarios compartilhados para a suite E2E (Tiers 1-4).

Mantem execucao 100% offline via mock de `agent._cliente` e importacao
dinamica dos modulos de perfil para compatibilidade com coleta em paralelo.
"""

from __future__ import annotations

import importlib
from pathlib import Path
import re
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.conftest import (
    APP_PATH,
    criar_mock_resposta_multiplas_tools,
    criar_mock_resposta_texto,
    criar_mock_resposta_tool_call,
)

RAIZ_PROJETO = Path(__file__).resolve().parent.parent.parent

PERFIS_ESPERADOS: dict[str, tuple[str, set[str]]] = {
    "agent.md": ("agent_base", {"somar"}),
    "agent-ada.md": (
        "agent_ada",
        {
            "somar",
            "verificar_sintaxe_python",
            "analisar_logica_codigo",
            "gerar_exemplo_analogo",
        },
    ),
    "agent-lint.md": (
        "agent_lint",
        {
            "somar",
            "analisar_complexidade_codigo",
            "detectar_antipadroes_python",
            "gerar_checklist_revisao",
        },
    ),
    "agent-val.md": (
        "agent_val",
        {
            "somar",
            "consultar_base_conhecimento",
            "verificar_status_chamado",
            "registrar_escalonamento",
        },
    ),
    "agent-organizador.md": (
        "agent_organizador",
        {
            "obter_pastas_padrao",
            "listar_arquivos",
            "criar_pasta",
            "mover_arquivo",
            "ler_conteudo_ou_resumo",
        },
    ),
}


def importar_modulo(nome_modulo: str) -> Any:
    """Importa dinamicamente um modulo do projeto em tempo de execucao do teste."""
    return importlib.import_module(nome_modulo)


def extrair_nomes_ferramentas_schema(ferramentas: list[dict[str, Any]]) -> list[str]:
    """Extrai a lista de nomes de funcoes declaradas nos schemas OpenAI."""
    return [item["function"]["name"] for item in ferramentas]


def extrair_ferramentas_markdown(md_path: Path) -> list[str]:
    """Extrai os nomes das ferramentas da secao `## Ferramentas disponíveis`."""
    conteudo = md_path.read_text(encoding="utf-8")
    linhas = conteudo.splitlines()
    na_secao = False
    nomes: list[str] = []
    padrao_linha = re.compile(r"^\|\s*`([a-zA-Z0-9_]+)`\s*\|")

    for linha in linhas:
        stripped = linha.strip()
        if stripped.startswith("## Ferramentas disponíveis"):
            na_secao = True
            continue
        if na_secao and stripped.startswith("## "):
            break
        if na_secao:
            match = padrao_linha.match(stripped)
            if match:
                nomes.append(match.group(1))
    return nomes


def descobrir_protocolo_sla_estourado(mod_val: Any) -> str | None:
    """Procura em colecoes publicas do modulo Val um protocolo com horas_em_aberto > 48."""
    for valor in vars(mod_val).values():
        if isinstance(valor, dict):
            for chave, registro in valor.items():
                if isinstance(registro, dict) and registro.get("horas_em_aberto", 0) > 48:
                    return str(chave)
    return None


@pytest.fixture
def e2e_cliente_mock(monkeypatch) -> MagicMock:
    """Fornece cliente OpenAI mockado propagado via `agent._cliente` e limpa `agent_core._cliente`."""
    import agent

    mock_cliente = MagicMock()
    monkeypatch.setattr(agent, "_cliente", mock_cliente)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-e2e-key")

    try:
        agent_core = importlib.import_module("agent_core")
        if hasattr(agent_core, "_cliente"):
            monkeypatch.setattr(agent_core, "_cliente", None)
    except ModuleNotFoundError:
        pass

    return mock_cliente


@pytest.fixture
def e2e_app_factory():
    """Retorna fabrica de AppTest apontando para `3AIER/app.py`."""
    from streamlit.testing.v1 import AppTest

    def _criar() -> AppTest:
        return AppTest.from_file(APP_PATH, default_timeout=10)

    return _criar


__all__ = [
    "APP_PATH",
    "PERFIS_ESPERADOS",
    "RAIZ_PROJETO",
    "criar_mock_resposta_multiplas_tools",
    "criar_mock_resposta_texto",
    "criar_mock_resposta_tool_call",
    "descobrir_protocolo_sla_estourado",
    "e2e_app_factory",
    "e2e_cliente_mock",
    "extrair_ferramentas_markdown",
    "extrair_nomes_ferramentas_schema",
    "importar_modulo",
]
