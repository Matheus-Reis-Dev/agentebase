"""Perfil base (`agent.md`) com isolamento estrito para a ferramenta `somar`."""

from pathlib import Path
from typing import Any, Callable

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

import agent_core
from agent_core import SOMAR_TOOL_SCHEMA, somar

PERFIL_NOME: str = "agent.md"
AGENT_MD: Path = agent_core.RAIZ / PERFIL_NOME
MEMORIA_PADRAO: str = "Nenhuma preferência ou histórico específico registrado para este perfil."

FERRAMENTAS: list[ChatCompletionToolParam] = [SOMAR_TOOL_SCHEMA]
EXECUTORES: dict[str, Callable[..., Any]] = {"somar": somar}


def carregar_contexto() -> str:
    """Carrega `agent.md` com seção `# Memória` neutra, sem vazar `memory.md` do Organizador."""
    return agent_core.carregar_contexto(
        AGENT_MD,
        memory_md=None,
        memoria_padrao=MEMORIA_PADRAO,
    )


def executar_ferramenta(nome: str, argumentos: dict) -> str:
    """Executa apenas ferramentas permitidas ao perfil base."""
    return agent_core.executar_ferramenta(nome, argumentos, EXECUTORES)


def responder(mensagens: list[ChatCompletionMessageParam], verboso: bool = False) -> str:
    """Executa o loop ReAct compartilhado com isolamento estrito das ferramentas do perfil base."""
    return agent_core.executar_loop_react(
        mensagens,
        FERRAMENTAS,
        EXECUTORES,
        verboso=verboso,
    )
