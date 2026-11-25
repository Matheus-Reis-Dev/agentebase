"""
Agente base — fachada retrocompatível e ponto de entrada CLI.

Preserva integralmente os símbolos públicos e globais esperados por `app.py`
e pela suíte existente em `tests/`, delegando a lógica compartilhada ao
`agent_core` e as ferramentas padrão ao `agent_organizador`.

Rode com:  python agent.py
"""

import os
import sys
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

import agent_core
import agent_organizador
from agent_organizador import (  # noqa: F401
    criar_pasta,
    ler_conteudo_ou_resumo,
    listar_arquivos,
    mover_arquivo,
    obter_pastas_padrao,
)

# ==========================================================================
# 1. CONFIGURAÇÃO
# ==========================================================================

RAIZ: Path = agent_core.RAIZ
AGENT_MD: Path = RAIZ / (os.getenv("AGENTE_PERFIL", "").strip() or "agent.md")
MEMORY_MD: Path = RAIZ / "memory.md"

MODELO: str = agent_core.MODELO
TEMPERATURA: float = agent_core.TEMPERATURA
MAX_ITERACOES: int = agent_core.MAX_ITERACOES

_cliente: OpenAI | None = None


def get_cliente() -> OpenAI:
    """Instancia o cliente da OpenAI uma vez só, isolado em `agent._cliente`."""
    global _cliente
    if _cliente is None:
        _cliente = agent_core.criar_cliente()
    return _cliente


# ==========================================================================
# 2. CONTEXTO
# ==========================================================================


def carregar_contexto() -> str:
    """Monta o prompt de sistema usando `agent.AGENT_MD` e `agent.MEMORY_MD` em tempo de chamada."""
    return agent_core.carregar_contexto(AGENT_MD, MEMORY_MD)


# ==========================================================================
# 3. FERRAMENTAS (Fachada padrão: Organizador de Arquivos)
# ==========================================================================

FERRAMENTAS: list[ChatCompletionToolParam] = list(agent_organizador.FERRAMENTAS)
EXECUTORES: dict[str, Callable[..., Any]] = dict(agent_organizador.EXECUTORES)


def executar_ferramenta(nome: str, argumentos: dict) -> str:
    """Executa uma ferramenta usando `agent.EXECUTORES` em tempo de chamada."""
    return agent_core.executar_ferramenta(nome, argumentos, EXECUTORES)


# ==========================================================================
# 4. O LOOP DO AGENTE
# ==========================================================================


def responder(mensagens: list[ChatCompletionMessageParam], verboso: bool = False) -> str:
    """Executa o loop ReAct resolvendo parâmetros, ferramentas e cliente de `agent` em tempo de chamada."""
    return agent_core.executar_loop_react(
        mensagens,
        FERRAMENTAS,
        EXECUTORES,
        cliente=get_cliente(),
        modelo=MODELO,
        temperatura=TEMPERATURA,
        max_iteracoes=MAX_ITERACOES,
        verboso=verboso,
    )


# ==========================================================================
# 5. O TERMINAL
# ==========================================================================


def _resolver_executor_cli():
    """Seleciona módulo do perfil via `AGENTE_PERFIL` quando válido, com fallback para `agent`."""
    perfil = os.getenv("AGENTE_PERFIL", "").strip()
    if perfil:
        try:
            modulo = agent_core.obter_modulo_perfil(perfil)
            return perfil, modulo.carregar_contexto, modulo.responder
        except (ValueError, ImportError):
            pass
    return "Agente Organizador de Arquivos", carregar_contexto, responder


def main() -> None:
    """Interface de terminal mínima."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        get_cliente()
    except RuntimeError as erro:
        print(f"\nErro: {erro}\n")
        sys.exit(1)

    titulo_perfil, fn_contexto, fn_responder = _resolver_executor_cli()
    print("=" * 60)
    print(f" {titulo_perfil}")
    print(f" Modelo: {MODELO} | Digite 'sair' para encerrar")
    print("=" * 60)

    mensagens: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": fn_contexto()}
    ]

    while True:
        try:
            pergunta = input("\nVocê: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAté logo!")
            break

        if not pergunta:
            continue
        if pergunta.lower() in {"sair", "exit", "quit"}:
            print("Até logo!")
            break

        marca = len(mensagens)
        mensagens.append({"role": "user", "content": pergunta})
        print("\nAgente: ", end="", flush=True)
        try:
            resposta = fn_responder(mensagens, verboso=True)
            print(resposta)
        except Exception as erro:
            del mensagens[marca:]
            print(f"\nErro ao chamar o modelo: {erro}")


if __name__ == "__main__":
    main()
