"""
Núcleo compartilhado do runtime multiagente.

Centraliza configuração, carregamento de contexto, resolução do cliente OpenAI,
despacho de ferramentas, loop ReAct e registro preguiçoso de perfis.
"""

import importlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Callable, cast

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

load_dotenv()

RAIZ: Path = Path(__file__).resolve().parent

MODELO: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TEMPERATURA: float = float(os.getenv("AGENTE_TEMPERATURA", "0.6"))
MAX_ITERACOES: int = int(os.getenv("AGENTE_MAX_ITERACOES", "8"))

_DEFAULTS: dict[str, Any] = {
    "MODELO": MODELO,
    "TEMPERATURA": TEMPERATURA,
    "MAX_ITERACOES": MAX_ITERACOES,
}

_cliente: OpenAI | None = None

PERFIL_MODULOS: dict[str, str] = {
    "agent.md": "agent_base",
    "agent-ada.md": "agent_ada",
    "agent-lint.md": "agent_lint",
    "agent-val.md": "agent_val",
    "agent-organizador.md": "agent_organizador",
}


def _resolver_config(nome: str, valor_explicito: Any) -> Any:
    """Resolve configuração respeitando argumento explícito, monkeypatch em `agent` ou `agent_core`."""
    if valor_explicito is not None:
        return valor_explicito

    agent_mod = sys.modules.get("agent")
    if agent_mod is not None and hasattr(agent_mod, nome):
        agent_val = getattr(agent_mod, nome)
        if agent_val != _DEFAULTS[nome]:
            return agent_val

    return globals()[nome]


def criar_cliente() -> OpenAI:
    """Cria uma nova instância do cliente OpenAI de forma stateless a partir das variáveis de ambiente."""
    chave = os.getenv("OPENAI_API_KEY")
    if not chave:
        raise RuntimeError(
            "OPENAI_API_KEY não encontrada. Copie .env.example para .env e coloque sua chave."
        )
    base_url = os.getenv("OPENAI_BASE_URL")
    return OpenAI(api_key=chave, base_url=base_url) if base_url else OpenAI(api_key=chave)


def get_cliente() -> OpenAI:
    """Retorna o cliente OpenAI em singleton preguiçoso, sincronizado com `agent._cliente`."""
    global _cliente
    agent_mod = sys.modules.get("agent")
    if agent_mod is not None:
        _cliente = None
        agent_cliente = getattr(agent_mod, "_cliente", None)
        if agent_cliente is None:
            agent_cliente = criar_cliente()
            setattr(agent_mod, "_cliente", agent_cliente)
        return agent_cliente

    if _cliente is None:
        _cliente = criar_cliente()
    return _cliente


def carregar_contexto(
    agent_md: Path,
    memory_md: Path | None = None,
    memoria_padrao: str = "",
) -> str:
    """Monta o prompt de sistema a partir do arquivo de perfil e memória opcional."""
    identidade = agent_md.read_text(encoding="utf-8") if agent_md.exists() else "Você é um assistente."
    if memory_md is not None and memory_md.exists():
        memoria = memory_md.read_text(encoding="utf-8")
    else:
        memoria = memoria_padrao
    return f"{identidade}\n\n---\n\n# Memória\n\n{memoria}"


def _converter_numero(valor: Any) -> int | float:
    """Converte entrada para int/float rejeitando booleanos, não-finitos e valores não numéricos."""
    if isinstance(valor, bool):
        raise ValueError("Valor booleano não é permitido como número.")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        if not math.isfinite(valor):
            raise ValueError("Valor numérico deve ser finito.")
        return valor
    if isinstance(valor, str):
        texto = valor.strip()
        try:
            return int(texto)
        except ValueError:
            num = float(texto)
            if not math.isfinite(num):
                raise ValueError("Valor numérico deve ser finito.")
            return num
    raise TypeError(f"Valor não numérico: {type(valor).__name__}")


def somar(a: float, b: float) -> dict:
    """Soma dois números e retorna dicionário estruturado com os operandos e o resultado."""
    try:
        num_a = _converter_numero(a)
        num_b = _converter_numero(b)
        resultado = num_a + num_b
    except (TypeError, ValueError, OverflowError) as exc:
        return {"erro": f"Parâmetros inválidos para somar: {exc}"}
    if isinstance(resultado, float) and not math.isfinite(resultado):
        return {"erro": "Resultado numérico fora dos limites finitos."}
    return {
        "a": num_a,
        "b": num_b,
        "resultado": resultado,
    }


SOMAR_TOOL_SCHEMA: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "somar",
        "description": "Soma dois números (a + b) com precisão exata.",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {
                    "type": "number",
                    "description": "Primeiro número da soma.",
                },
                "b": {
                    "type": "number",
                    "description": "Segundo número da soma.",
                },
            },
            "required": ["a", "b"],
        },
    },
}


def executar_ferramenta(
    nome: str,
    argumentos: dict,
    executores: dict[str, Callable[..., Any]],
) -> str:
    """Executa uma ferramenta do perfil ativo e devolve SEMPRE uma string JSON."""
    funcao = executores.get(nome)
    if funcao is None:
        return json.dumps({"erro": f"Ferramenta '{nome}' não existe."}, ensure_ascii=False)
    try:
        return json.dumps(funcao(**argumentos), ensure_ascii=False, allow_nan=False)
    except Exception as exc:
        return json.dumps({"erro": f"Falha em '{nome}': {exc}"}, ensure_ascii=False)


def _processar_chamadas_ferramenta(
    mensagens: list[ChatCompletionMessageParam],
    mensagem: Any,
    executores: dict[str, Callable[..., Any]],
    verboso: bool,
) -> None:
    """Executa todas as tool_calls de um turno e anexa as mensagens ao histórico."""
    msg_dict = {k: v for k, v in mensagem.model_dump().items() if v is not None}
    mensagens.append(cast(ChatCompletionMessageParam, msg_dict))

    for chamada in mensagem.tool_calls:
        nome = chamada.function.name
        try:
            argumentos = json.loads(chamada.function.arguments or "{}")
        except (json.JSONDecodeError, TypeError):
            argumentos = {}

        if verboso:
            print(f"  [ferramenta] {nome}({argumentos})")

        resultado = executar_ferramenta(nome, argumentos, executores)

        mensagens.append({
            "role": "tool",
            "tool_call_id": chamada.id,
            "content": resultado,
        })


def executar_loop_react(
    mensagens: list[ChatCompletionMessageParam],
    ferramentas: list[ChatCompletionToolParam],
    executores: dict[str, Callable[..., Any]],
    *,
    cliente: OpenAI | None = None,
    modelo: str | None = None,
    temperatura: float | None = None,
    max_iteracoes: int | None = None,
    verboso: bool = False,
) -> str:
    """Executa o loop ReAct isolado para as ferramentas e executores fornecidos."""
    cliente_ativo = cliente if cliente is not None else get_cliente()
    modelo_ativo = _resolver_config("MODELO", modelo)
    temperatura_ativo = _resolver_config("TEMPERATURA", temperatura)
    max_iteracoes_ativo = _resolver_config("MAX_ITERACOES", max_iteracoes)

    for _ in range(max_iteracoes_ativo):
        try:
            resposta = cliente_ativo.chat.completions.create(
                model=modelo_ativo,
                messages=mensagens,
                tools=ferramentas,
                temperature=temperatura_ativo,
            )
        except Exception as exc:
            if "tool_use_failed" in str(exc) or "Tool call validation failed" in str(exc):
                nomes_validos = ", ".join(executores.keys())
                mensagens.append({
                    "role": "user",
                    "content": (
                        "Erro de validação na chamada de ferramenta. "
                        f"Use EXATAMENTE um dos nomes: {nomes_validos}."
                    ),
                })
                continue
            raise

        mensagem = resposta.choices[0].message
        if mensagem.tool_calls:
            _processar_chamadas_ferramenta(mensagens, mensagem, executores, verboso)
        else:
            conteudo = mensagem.content or ""
            mensagens.append({"role": "assistant", "content": conteudo})
            return conteudo

    return "Atingi o limite de iterações sem concluir. Tente reformular o pedido."


def obter_modulo_perfil(perfil: str) -> Any:
    """Importa dinamicamente e retorna o módulo Python correspondente ao perfil."""
    modulo_nome = PERFIL_MODULOS.get(perfil)
    if modulo_nome is None:
        perfis_validos = ", ".join(PERFIL_MODULOS.keys())
        raise ValueError(f"Perfil '{perfil}' desconhecido. Perfis suportados: {perfis_validos}.")
    return importlib.import_module(modulo_nome)


def responder_perfil(
    perfil: str,
    mensagens: list[ChatCompletionMessageParam],
    verboso: bool = False,
) -> str:
    """Executa o loop do agente utilizando o módulo associado ao perfil informado."""
    modulo = obter_modulo_perfil(perfil)
    return modulo.responder(mensagens, verboso=verboso)
