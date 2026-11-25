"""
Perfil Lint (`agent-lint.md`) — revisor técnico sênior e análise estática Python.

Fornece a ferramenta `somar` e três ferramentas determinísticas baseadas em `ast`
para análise de complexidade, detecção de antipadrões e checklists de revisão,
mantendo isolamento estrito de ferramentas e memória.
"""

import ast
from pathlib import Path
import re
from typing import Any, Callable
import unicodedata

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

import agent_core
from agent_core import SOMAR_TOOL_SCHEMA, somar

PERFIL_NOME: str = "agent-lint.md"
AGENT_MD: Path = agent_core.RAIZ / PERFIL_NOME
MEMORIA_PADRAO: str = "Nenhuma preferência ou histórico específico registrado para este perfil."

_ESCOPOS_ISOLADOS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_BLOCOS_ANINHAMENTO = (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)
if hasattr(ast, "Match"):
    _BLOCOS_ANINHAMENTO = _BLOCOS_ANINHAMENTO + (ast.Match,)

_NOS_DECISAO = (
    ast.If,
    ast.IfExp,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
)
_MATCH_CASE_TYPE = getattr(ast, "match_case", None)
_MATCH_BIND_TYPES = tuple(
    tipo
    for tipo in (
        getattr(ast, "MatchAs", None),
        getattr(ast, "MatchStar", None),
        getattr(ast, "MatchMapping", None),
    )
    if tipo is not None
)

_ORDEM_GRAVIDADE: dict[str, int] = {
    "critica": 0,
    "alta": 1,
    "media": 2,
    "baixa": 3,
}

_METODOS_MUTACAO = frozenset({
    "append",
    "extend",
    "insert",
    "pop",
    "remove",
    "clear",
    "update",
    "setdefault",
    "add",
    "discard",
    "sort",
    "reverse",
})

_SUBPROCESS_CALLS = frozenset({"run", "Popen", "call", "check_call", "check_output"})
_IDENTIFICADOR_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_CHECKLISTS_REVISAO: dict[str, dict[str, Any]] = {
    "api": {
        "foco": "Contratos de entrada/saída, compatibilidade retroativa e tratamento de falhas",
        "criterio_bloqueio": "Quebra de contrato público ou exposição de erro interno sem sanitização.",
        "itens": [
            {"prioridade": "alta", "item": "Validar schema, tipos e limites dos parâmetros de entrada."},
            {"prioridade": "alta", "item": "Preservar retrocompatibilidade de payloads e códigos HTTP/erro."},
            {"prioridade": "alta", "item": "Garantir que exceções internas não vazem stack traces ou segredos."},
            {"prioridade": "media", "item": "Conferir timeouts, retries e idempotência em chamadas externas."},
            {"prioridade": "media", "item": "Cobrir casos felizes, erros 4xx/5xx e bordas com testes de contrato."},
        ],
    },
    "concorrencia": {
        "foco": "Estado compartilhado, condições de corrida, locks e cancelamento",
        "criterio_bloqueio": "Escrita concorrente sem sincronização ou risco de deadlock/vazamento de task.",
        "itens": [
            {"prioridade": "alta", "item": "Eliminar mutação de estado global ou caches sem sincronização."},
            {"prioridade": "alta", "item": "Verificar padrões check-then-act (TOCTOU) em arquivos, locks e dicts."},
            {"prioridade": "alta", "item": "Garantir liberação de locks/recursos em blocos finally ou context managers."},
            {"prioridade": "media", "item": "Conferir ordem consistente de aquisição de múltiplos locks."},
            {"prioridade": "media", "item": "Validar timeout, cancelamento limpo e tratamento de exceções em workers."},
        ],
    },
    "seguranca": {
        "foco": "Validação de entrada, superfície de ataque, segredos e privilégios",
        "criterio_bloqueio": "Injeção de código/comando, travessia de caminho ou exposição de credenciais.",
        "itens": [
            {"prioridade": "alta", "item": "Proibir eval, exec, pickle não confiável e subprocess com shell=True."},
            {"prioridade": "alta", "item": "Sanitizar caminhos de arquivo e entradas usadas em queries ou comandos."},
            {"prioridade": "alta", "item": "Confirmar ausência de chaves, tokens ou senhas hardcoded ou em logs."},
            {"prioridade": "alta", "item": "Validar autenticação e autorização antes de qualquer ação sensível."},
            {"prioridade": "media", "item": "Garantir mensagens de erro mínimas sem vazar detalhes de infraestrutura."},
        ],
    },
    "refatoracao": {
        "foco": "Equivalência comportamental, acoplamento e redução de complexidade",
        "criterio_bloqueio": "Regressão de comportamento público ou complexidade maior sem ganho claro.",
        "itens": [
            {"prioridade": "alta", "item": "Confirmar preservação de assinaturas, retornos e efeitos colaterais públicos."},
            {"prioridade": "alta", "item": "Executar testes existentes antes e depois da mudança para provar equivalência."},
            {"prioridade": "media", "item": "Verificar se a complexidade ciclomática e o aninhamento diminuíram de fato."},
            {"prioridade": "media", "item": "Evitar abstrações prematuras para um único ponto de uso."},
            {"prioridade": "baixa", "item": "Remover código morto, variáveis não usadas e imports obsoletos."},
        ],
    },
    "geral": {
        "foco": "Correção funcional, tratamento de erros, clareza e testes",
        "criterio_bloqueio": "Bug funcional, exceção engolida silenciosamente ou ausência de testes para o risco.",
        "itens": [
            {"prioridade": "alta", "item": "Testar casos de borda: None, vazio, limites numéricos e entradas inválidas."},
            {"prioridade": "alta", "item": "Garantir tratamento explícito de erros sem bare except ou pass silencioso."},
            {"prioridade": "media", "item": "Checar liberação determinística de arquivos, conexões e recursos externos."},
            {"prioridade": "media", "item": "Avaliar se funções longas ou muito ramificadas podem ser decompostas."},
            {"prioridade": "baixa", "item": "Confirmar cobertura de testes unitários e conformidade com o linter do projeto."},
        ],
    },
}


def _parsear_codigo(codigo: Any) -> tuple[ast.Module | None, dict[str, Any] | None]:
    """Valida e converte código Python em AST sem lançar exceções."""
    if not isinstance(codigo, str):
        return None, {
            "codigo_valido": False,
            "vazio": False,
            "erro": "Entrada inválida: o parâmetro 'codigo' deve ser uma string.",
            "linha_erro": None,
        }
    if not codigo.strip():
        return None, {
            "codigo_valido": True,
            "vazio": True,
            "erro": None,
            "linha_erro": None,
        }
    try:
        return ast.parse(codigo), None
    except (SyntaxError, ValueError) as exc:
        linha = getattr(exc, "lineno", None)
        msg = getattr(exc, "msg", str(exc))
        detalhe = f"Erro de sintaxe na linha {linha}: {msg}" if linha else f"Erro de sintaxe: {msg}"
        return None, {
            "codigo_valido": False,
            "vazio": False,
            "erro": detalhe,
            "linha_erro": linha,
        }


def _extrair_subblocos(stmt: ast.stmt) -> list[list[ast.stmt]]:
    """Extrai listas de instruções filhas de blocos compostos de controle."""
    blocos: list[list[ast.stmt]] = []
    for attr in ("body", "orelse", "finalbody"):
        filhos = getattr(stmt, attr, None)
        if isinstance(filhos, list):
            blocos.append(filhos)
    for handler in getattr(stmt, "handlers", []):
        blocos.append(handler.body)
    for caso in getattr(stmt, "cases", []):
        blocos.append(caso.body)
    return blocos


def _profundidade_if(stmt: ast.If, nivel: int) -> int:
    """Calcula profundidade máxima de um bloco `if/elif/else` sem inflar cadeias `elif`."""
    proximo = nivel + 1
    prof_body = _profundidade_bloco(stmt.body, proximo)
    if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
        prof_else = _profundidade_if(stmt.orelse[0], nivel)
    elif stmt.orelse:
        prof_else = _profundidade_bloco(stmt.orelse, proximo)
    else:
        prof_else = proximo
    return max(proximo, prof_body, prof_else)


def _profundidade_bloco(instrucoes: list[ast.stmt], nivel: int = 0) -> int:
    """Calcula profundidade máxima de aninhamento dentro do escopo atual."""
    maior = nivel
    for stmt in instrucoes:
        if isinstance(stmt, _ESCOPOS_ISOLADOS):
            continue
        if isinstance(stmt, ast.If):
            maior = max(maior, _profundidade_if(stmt, nivel))
        elif isinstance(stmt, _BLOCOS_ANINHAMENTO):
            proximo = nivel + 1
            maior = max(maior, proximo)
            for subbloco in _extrair_subblocos(stmt):
                maior = max(maior, _profundidade_bloco(subbloco, proximo))
    return maior


def _nos_do_escopo(corpo: list[ast.stmt]) -> list[ast.AST]:
    """Percorre nós do escopo atual sem invadir funções ou classes aninhadas."""
    pilha: list[ast.AST] = list(corpo)
    visitados: list[ast.AST] = []
    while pilha:
        atual = pilha.pop()
        visitados.append(atual)
        if isinstance(atual, _ESCOPOS_ISOLADOS):
            continue
        pilha.extend(ast.iter_child_nodes(atual))
    return visitados


def _complexidade_ciclomatica(corpo: list[ast.stmt]) -> int:
    """Estima complexidade ciclomática (McCabe) do corpo de instruções informado."""
    complexidade = 1
    for no in _nos_do_escopo(corpo):
        if isinstance(no, _NOS_DECISAO):
            complexidade += 1
        elif isinstance(no, ast.BoolOp):
            complexidade += max(0, len(no.values) - 1)
        elif isinstance(no, ast.comprehension):
            complexidade += 1 + len(no.ifs)
        elif _MATCH_CASE_TYPE is not None and isinstance(no, _MATCH_CASE_TYPE):
            complexidade += 1
    return complexidade


def _coletar_funcoes_bloco(
    instrucoes: list[ast.stmt],
    prefixo: str = "",
) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Coleta definições de função e método em ordem de aparição."""
    resultado: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for stmt in instrucoes:
        if isinstance(stmt, ast.ClassDef):
            novo = f"{prefixo}.{stmt.name}" if prefixo else stmt.name
            resultado.extend(_coletar_funcoes_bloco(stmt.body, novo))
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nome = f"{prefixo}.{stmt.name}" if prefixo else stmt.name
            resultado.append((nome, stmt))
            resultado.extend(_coletar_funcoes_bloco(stmt.body, nome))
        else:
            for sub in _extrair_subblocos(stmt):
                resultado.extend(_coletar_funcoes_bloco(sub, prefixo))
    return resultado


def _contar_parametros(func: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Conta todos os parâmetros declarados na assinatura da função."""
    args = func.args
    total = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    if args.vararg is not None:
        total += 1
    if args.kwarg is not None:
        total += 1
    return total


def _avaliar_alertas_funcao(metrica: dict[str, Any]) -> list[dict[str, Any]]:
    """Gera alertas objetivos quando uma função excede limiares de complexidade."""
    alertas: list[dict[str, Any]] = []
    nome = metrica["nome"]
    linha = metrica["linha_inicio"]
    cc = metrica["complexidade_ciclomatica"]

    if cc > 15:
        alertas.append({
            "gravidade": "alta",
            "funcao": nome,
            "linha": linha,
            "tipo": "complexidade_excessiva",
            "mensagem": f"Função '{nome}' (L{linha}) tem complexidade ciclomática {cc} (> 15).",
        })
    elif cc > 10:
        alertas.append({
            "gravidade": "media",
            "funcao": nome,
            "linha": linha,
            "tipo": "complexidade_elevada",
            "mensagem": f"Função '{nome}' (L{linha}) tem complexidade ciclomática {cc} (> 10).",
        })

    if metrica["profundidade_aninhamento"] >= 4:
        prof = metrica["profundidade_aninhamento"]
        alertas.append({
            "gravidade": "media",
            "funcao": nome,
            "linha": linha,
            "tipo": "aninhamento_profundo",
            "mensagem": f"Função '{nome}' (L{linha}) atinge profundidade {prof} (>= 4).",
        })

    if metrica["linhas"] > 50:
        linhas = metrica["linhas"]
        alertas.append({
            "gravidade": "media",
            "funcao": nome,
            "linha": linha,
            "tipo": "funcao_longa",
            "mensagem": f"Função '{nome}' (L{linha}) possui {linhas} linhas (> 50).",
        })

    if metrica["parametros"] > 5:
        params = metrica["parametros"]
        alertas.append({
            "gravidade": "baixa",
            "funcao": nome,
            "linha": linha,
            "tipo": "muitos_parametros",
            "mensagem": f"Função '{nome}' (L{linha}) recebe {params} parâmetros (> 5).",
        })

    return alertas


def analisar_complexidade_codigo(codigo: str) -> dict:
    """Analisa linhas, parâmetros, aninhamento e complexidade ciclomática de código Python."""
    arvore, erro_info = _parsear_codigo(codigo)
    if erro_info is not None:
        return {
            **erro_info,
            "total_linhas": 0,
            "total_funcoes": 0,
            "complexidade_maxima": 0,
            "profundidade_maxima": 0,
            "funcoes": [],
            "alertas": [],
            "resumo": erro_info["erro"] or "Código vazio; nenhuma função analisada.",
        }

    assert arvore is not None
    funcoes: list[dict[str, Any]] = []
    alertas: list[dict[str, Any]] = []

    for nome, func in _coletar_funcoes_bloco(arvore.body):
        linha_fim = getattr(func, "end_lineno", None) or func.lineno
        metrica = {
            "nome": nome,
            "linha_inicio": func.lineno,
            "linha_fim": linha_fim,
            "linhas": max(1, linha_fim - func.lineno + 1),
            "parametros": _contar_parametros(func),
            "profundidade_aninhamento": _profundidade_bloco(func.body, 0),
            "complexidade_ciclomatica": _complexidade_ciclomatica(func.body),
        }
        funcoes.append(metrica)
        alertas.extend(_avaliar_alertas_funcao(metrica))

    if funcoes:
        cc_max = max(item["complexidade_ciclomatica"] for item in funcoes)
        prof_max = max(item["profundidade_aninhamento"] for item in funcoes)
    else:
        cc_max = _complexidade_ciclomatica(arvore.body)
        prof_max = _profundidade_bloco(arvore.body, 0)

    alertas.sort(key=lambda a: (_ORDEM_GRAVIDADE.get(a["gravidade"], 99), a["linha"]))
    total_linhas = len(codigo.splitlines())
    resumo = (
        f"{len(funcoes)} função(ões) analisada(s); complexidade máxima {cc_max}, "
        f"profundidade máxima {prof_max}, {len(alertas)} alerta(s)."
    )
    return {
        "codigo_valido": True,
        "vazio": False,
        "total_linhas": total_linhas,
        "total_funcoes": len(funcoes),
        "complexidade_maxima": cc_max,
        "profundidade_maxima": prof_max,
        "funcoes": funcoes,
        "alertas": alertas,
        "resumo": resumo,
    }


def _criar_achado(
    gravidade: str,
    categoria: str,
    tipo: str,
    linha: int,
    onde: str,
    o_que: str,
    por_que_importa: str,
) -> dict[str, Any]:
    """Cria registro padronizado de achado para revisão técnica."""
    return {
        "gravidade": gravidade,
        "categoria": categoria,
        "tipo": tipo,
        "linha": linha,
        "onde": onde,
        "o_que": o_que,
        "por_que_importa": por_que_importa,
    }


def _detectar_chamadas_inseguras(arvore: ast.Module) -> list[dict[str, Any]]:
    """Detecta chamadas perigosas (`eval`, `exec`, `subprocess(..., shell=True)`)."""
    achados: list[dict[str, Any]] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        if isinstance(no.func, ast.Name) and no.func.id in {"eval", "exec"}:
            achados.append(_criar_achado(
                "alta",
                "seguranca",
                f"uso_{no.func.id}",
                no.lineno,
                f"linha {no.lineno}",
                f"Uso de `{no.func.id}()`.",
                "Executa código arbitrário a partir de strings; risco direto de injeção de código.",
            ))
        elif isinstance(no.func, ast.Attribute) and no.func.attr in _SUBPROCESS_CALLS:
            usa_shell = any(
                kw.arg == "shell"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
                for kw in no.keywords
            )
            if usa_shell:
                achados.append(_criar_achado(
                    "alta",
                    "seguranca",
                    "subprocess_shell_true",
                    no.lineno,
                    f"linha {no.lineno}",
                    f"Chamada `{no.func.attr}(..., shell=True)`.",
                    "Invoca o shell do sistema e abre brecha para command injection.",
                ))
    return achados


def _eh_valor_mutavel(expr: ast.expr | None) -> bool:
    """Identifica literais ou construtores mutáveis usados como valor padrão."""
    if expr is None:
        return False
    if isinstance(expr, (ast.List, ast.Dict, ast.Set)):
        return True
    return (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Name)
        and expr.func.id in {"list", "dict", "set"}
    )


def _detectar_args_mutaveis(arvore: ast.Module) -> list[dict[str, Any]]:
    """Detecta valores padrão mutáveis em parâmetros posicionais ou keyword-only."""
    achados: list[dict[str, Any]] = []
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        posicionais = no.args.posonlyargs + no.args.args
        deslocamento = len(posicionais) - len(no.args.defaults)
        pares = list(zip(posicionais[deslocamento:], no.args.defaults))
        pares.extend(zip(no.args.kwonlyargs, no.args.kw_defaults))
        for param, padrao in pares:
            if _eh_valor_mutavel(padrao):
                achados.append(_criar_achado(
                    "alta",
                    "bug",
                    "argumento_mutavel_padrao",
                    padrao.lineno if padrao is not None else no.lineno,
                    f"{no.name}() linha {no.lineno}",
                    f"Parâmetro `{param.arg}` com valor padrão mutável.",
                    "O objeto é criado uma única vez na definição da função e vaza estado entre chamadas.",
                ))
    return achados


def _corpo_apenas_pass(body: list[ast.stmt]) -> bool:
    """Verifica se um bloco contém apenas `pass` ou reticências `...`."""
    if len(body) != 1:
        return False
    unico = body[0]
    if isinstance(unico, ast.Pass):
        return True
    return (
        isinstance(unico, ast.Expr)
        and isinstance(unico.value, ast.Constant)
        and unico.value.value is Ellipsis
    )


def _detectar_excepts_problematicos(arvore: ast.Module) -> list[dict[str, Any]]:
    """Detecta `bare except:` e blocos `except` que silenciam falhas com `pass`."""
    achados: list[dict[str, Any]] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.ExceptHandler):
            continue
        apenas_pass = _corpo_apenas_pass(no.body)
        if no.type is None and apenas_pass:
            achados.append(_criar_achado(
                "alta",
                "bug",
                "bare_except_silenciado",
                no.lineno,
                f"linha {no.lineno}",
                "Bloco `except:` sem tipo combinado com `pass`.",
                "Captura até KeyboardInterrupt/SystemExit e esconde falhas reais silenciosamente.",
            ))
        elif no.type is None:
            achados.append(_criar_achado(
                "alta",
                "bug",
                "bare_except",
                no.lineno,
                f"linha {no.lineno}",
                "Cláusula `except:` sem tipo de exceção.",
                "Captura exceções inesperadas (como SystemExit/KeyboardInterrupt) e mascara bugs.",
            ))
        elif apenas_pass:
            achados.append(_criar_achado(
                "media",
                "bug",
                "except_silenciado",
                no.lineno,
                f"linha {no.lineno}",
                "Exceção capturada e silenciada com `pass`.",
                "Oculta erros em execução sem registro ou recuperação, dificultando diagnóstico.",
            ))
    return achados


def _nomes_base_alvo(alvo: ast.expr) -> list[str]:
    """Extrai identificadores raiz de alvos de atribuição, desempacotamento, subscrito ou atributo."""
    if isinstance(alvo, (ast.Tuple, ast.List)):
        nomes: list[str] = []
        for elt in alvo.elts:
            nomes.extend(_nomes_base_alvo(elt))
        return nomes
    if isinstance(alvo, ast.Starred):
        return _nomes_base_alvo(alvo.value)
    atual = alvo
    while isinstance(atual, (ast.Attribute, ast.Subscript)):
        atual = atual.value
    if isinstance(atual, ast.Name):
        return [atual.id]
    return []


def _alvos_mutacao_no(no: ast.AST) -> list[ast.expr]:
    """Extrai expressões alvo potencialmente mutadas por um nó AST."""
    if isinstance(no, (ast.Assign, ast.Delete)):
        return list(no.targets)
    if isinstance(no, (ast.AugAssign, ast.For, ast.AsyncFor, ast.NamedExpr)):
        return [no.target]
    if isinstance(no, ast.AnnAssign) and no.value is not None:
        return [no.target]
    if isinstance(no, (ast.With, ast.AsyncWith)):
        return [item.optional_vars for item in no.items if item.optional_vars is not None]
    if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr in _METODOS_MUTACAO:
        return [no.func.value]
    return []


def _nomes_vinculados_no(no: ast.AST) -> list[str]:
    """Extrai identificadores vinculados por `except`, `import` ou `match/case`."""
    if isinstance(no, ast.ExceptHandler):
        return [no.name] if no.name else []
    if isinstance(no, ast.Import):
        return [alias.asname or alias.name.split(".")[0] for alias in no.names]
    if isinstance(no, ast.ImportFrom):
        return [alias.asname or alias.name for alias in no.names if alias.name != "*"]
    if _MATCH_BIND_TYPES and isinstance(no, _MATCH_BIND_TYPES):
        nome = getattr(no, "name", None) or getattr(no, "rest", None)
        return [nome] if nome else []
    return []


def _nomes_parametros_lambda(args: ast.arguments) -> set[str]:
    """Coleta nomes de parâmetros declarados em uma expressão `lambda`."""
    nomes = {p.arg for p in args.posonlyargs + args.args + args.kwonlyargs}
    if args.vararg is not None:
        nomes.add(args.vararg.arg)
    if args.kwarg is not None:
        nomes.add(args.kwarg.arg)
    return nomes


_COMPREENSOES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _nomes_ligados_compreensao(alvo: ast.expr) -> list[str]:
    """Extrai apenas nomes locais vinculados diretamente em alvos de compreensão."""
    if isinstance(alvo, ast.Name):
        return [alvo.id]
    if isinstance(alvo, (ast.Tuple, ast.List)):
        nomes: list[str] = []
        for elt in alvo.elts:
            nomes.extend(_nomes_ligados_compreensao(elt))
        return nomes
    if isinstance(alvo, ast.Starred):
        return _nomes_ligados_compreensao(alvo.value)
    return []


def _mutacoes_alvo_compreensao(
    alvo: ast.expr,
    ativos: set[str],
    pilha: list[tuple[ast.AST, set[str]]],
) -> list[tuple[str, int]]:
    """Extrai mutações globais em alvos `Subscript`/`Attribute` de compreensão."""
    if isinstance(alvo, (ast.Tuple, ast.List)):
        mutacoes: list[tuple[str, int]] = []
        for elt in alvo.elts:
            mutacoes.extend(_mutacoes_alvo_compreensao(elt, ativos, pilha))
        return mutacoes
    if isinstance(alvo, ast.Starred):
        return _mutacoes_alvo_compreensao(alvo.value, ativos, pilha)
    if isinstance(alvo, (ast.Subscript, ast.Attribute)):
        linha = getattr(alvo, "lineno", 0)
        mutacoes = [(nome, linha) for nome in _nomes_base_alvo(alvo) if nome in ativos]
        pilha.extend((filho, ativos) for filho in ast.iter_child_nodes(alvo))
        return mutacoes
    return []


def _empilhar_compreensao(
    pilha: list[tuple[ast.AST, set[str]]],
    atual: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
    ativos: set[str],
) -> list[tuple[str, int]]:
    """Empilha nós de compreensão mantendo `generators[0].iter` e alvos mutáveis no escopo correto."""
    alvos_comp: set[str] = set()
    mutacoes: list[tuple[str, int]] = []
    for idx, gen in enumerate(atual.generators):
        escopo_iter = ativos if idx == 0 else ativos - alvos_comp
        pilha.append((gen.iter, escopo_iter))
        mutacoes.extend(_mutacoes_alvo_compreensao(gen.target, escopo_iter, pilha))
        alvos_comp.update(_nomes_ligados_compreensao(gen.target))
        escopo_filtro = ativos - alvos_comp
        for cond in gen.ifs:
            pilha.append((cond, escopo_filtro))
    escopo_corpo = ativos - alvos_comp
    if isinstance(atual, ast.DictComp):
        pilha.append((atual.key, escopo_corpo))
        pilha.append((atual.value, escopo_corpo))
    else:
        pilha.append((atual.elt, escopo_corpo))
    return mutacoes


def _empilhar_filhos_escopo_global(
    pilha: list[tuple[ast.AST, set[str]]],
    atual: ast.AST,
    ativos: set[str],
) -> list[tuple[str, int]]:
    """Empilha filhos removendo parâmetros de `lambda` e alvos de compreensão sombreados."""
    if isinstance(atual, ast.Lambda):
        params = _nomes_parametros_lambda(atual.args)
        pilha.append((atual.body, ativos - params))
        for padrao in atual.args.defaults + atual.args.kw_defaults:
            if padrao is not None:
                pilha.append((padrao, ativos))
        return []
    if isinstance(atual, _COMPREENSOES):
        return _empilhar_compreensao(pilha, atual, ativos)
    pilha.extend((filho, ativos) for filho in ast.iter_child_nodes(atual))
    return []


def _mutacoes_globais_no(no: ast.AST, globais: set[str]) -> list[tuple[str, int]]:
    """Retorna lista de `(nome_global, linha)` para todas as variáveis globais mutadas pelo nó AST."""
    linha = getattr(no, "lineno", 0)
    resultado: list[tuple[str, int]] = []
    for alvo in _alvos_mutacao_no(no):
        for nome in _nomes_base_alvo(alvo):
            if nome in globais:
                resultado.append((nome, linha))
    for nome in _nomes_vinculados_no(no):
        if nome in globais:
            resultado.append((nome, linha))
    return resultado


def _detectar_mutacao_global(arvore: ast.Module) -> list[dict[str, Any]]:
    """Detecta mutação de estado global dentro de funções via `global`."""
    achados: list[dict[str, Any]] = []
    for func in ast.walk(arvore):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        globais = {
            nome
            for no in _nos_do_escopo(func.body)
            if isinstance(no, ast.Global)
            for nome in no.names
        }
        if not globais:
            continue
        vistos: set[tuple[str, int]] = set()
        pilha: list[tuple[ast.AST, set[str]]] = [(stmt, globais) for stmt in func.body]
        while pilha:
            no, ativos = pilha.pop()
            if isinstance(no, _ESCOPOS_ISOLADOS):
                continue
            mutacoes = _mutacoes_globais_no(no, ativos)
            mutacoes.extend(_empilhar_filhos_escopo_global(pilha, no, ativos))
            for nome_var, linha in mutacoes:
                mut = (nome_var, linha)
                if mut not in vistos:
                    vistos.add(mut)
                    achados.append(_criar_achado(
                        "media",
                        "bug",
                        "mutacao_global",
                        linha,
                        f"{func.name}() linha {linha}",
                        f"Mutação da variável global `{nome_var}`.",
                        "Acopla chamadas, cria corrida em concorrência e quebra isolamento entre testes.",
                    ))
    return achados


def _eh_none_constante(no: ast.AST) -> bool:
    """Verifica se o nó representa o literal `None`."""
    return isinstance(no, ast.Constant) and no.value is None


def _detectar_comparacao_none(arvore: ast.Module) -> list[dict[str, Any]]:
    """Detecta comparações `== None` ou `!= None` que devem usar `is` / `is not`."""
    achados: list[dict[str, Any]] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Compare):
            continue
        for idx, (op, comp) in enumerate(zip(no.ops, no.comparators)):
            if not isinstance(op, (ast.Eq, ast.NotEq)):
                continue
            if _eh_none_constante(comp) or (idx == 0 and _eh_none_constante(no.left)):
                simbolo = "==" if isinstance(op, ast.Eq) else "!="
                sugestao = "is None" if isinstance(op, ast.Eq) else "is not None"
                achados.append(_criar_achado(
                    "baixa",
                    "estilo",
                    "comparacao_none_igualdade",
                    no.lineno,
                    f"linha {no.lineno}",
                    f"Comparação com `None` usando `{simbolo}`.",
                    f"Em Python, identidade com None deve usar `{sugestao}` (evita `__eq__` customizado).",
                ))
                break
    return achados


def _coletar_imports(arvore: ast.Module) -> list[tuple[str, int]]:
    """Lista nomes vinculados por instruções `import` e `from ... import`."""
    imports: list[tuple[str, int]] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for alias in no.names:
                nome = alias.asname or alias.name.split(".")[0]
                imports.append((nome, no.lineno))
        elif isinstance(no, ast.ImportFrom):
            if no.module == "__future__":
                continue
            for alias in no.names:
                if alias.name == "*":
                    continue
                nome = alias.asname or alias.name
                imports.append((nome, no.lineno))
    return imports


def _coletar_nomes_usados(arvore: ast.Module) -> set[str]:
    """Coleta identificadores referenciados em expressões, `__all__` e anotações em string."""
    usados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            usados.add(no.id)
        elif isinstance(no, ast.Assign):
            eh_all = any(isinstance(t, ast.Name) and t.id == "__all__" for t in no.targets)
            if eh_all and isinstance(no.value, (ast.List, ast.Tuple, ast.Set)):
                for item in no.value.elts:
                    if isinstance(item, ast.Constant) and isinstance(item.value, str):
                        usados.add(item.value)
        elif isinstance(no, (ast.arg, ast.AnnAssign)) and isinstance(no.annotation, ast.Constant):
            if isinstance(no.annotation.value, str):
                usados.update(_IDENTIFICADOR_RE.findall(no.annotation.value))
        elif isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and isinstance(no.returns, ast.Constant):
            if isinstance(no.returns.value, str):
                usados.update(_IDENTIFICADOR_RE.findall(no.returns.value))
    return usados


def _detectar_imports_nao_utilizados(arvore: ast.Module) -> list[dict[str, Any]]:
    """Detecta imports declarados sem referência no módulo."""
    imports = _coletar_imports(arvore)
    if not imports:
        return []
    usados = _coletar_nomes_usados(arvore)
    achados: list[dict[str, Any]] = []
    vistos: set[tuple[str, int]] = set()
    for nome, linha in imports:
        if nome not in usados and (nome, linha) not in vistos:
            vistos.add((nome, linha))
            achados.append(_criar_achado(
                "baixa",
                "estilo",
                "import_nao_utilizado",
                linha,
                f"linha {linha}",
                f"Import `{nome}` não utilizado.",
                "Aumenta ruído de leitura e pode manter dependências ou efeitos de carga desnecessários.",
            ))
    return achados


def detectar_antipadroes_python(codigo: str) -> dict:
    """Detecta antipadrões de segurança, bugs e estilo em Python, ordenados por gravidade."""
    arvore, erro_info = _parsear_codigo(codigo)
    if erro_info is not None:
        return {
            **erro_info,
            "total_achados": 0,
            "veredito": "erro_analise" if erro_info["erro"] else "limpo",
            "contagem_por_gravidade": {"critica": 0, "alta": 0, "media": 0, "baixa": 0},
            "achados": [],
            "resumo": erro_info["erro"] or "Código vazio; nenhum antipadrão analisado.",
        }

    assert arvore is not None
    achados: list[dict[str, Any]] = []
    achados.extend(_detectar_chamadas_inseguras(arvore))
    achados.extend(_detectar_args_mutaveis(arvore))
    achados.extend(_detectar_excepts_problematicos(arvore))
    achados.extend(_detectar_mutacao_global(arvore))
    achados.extend(_detectar_comparacao_none(arvore))
    achados.extend(_detectar_imports_nao_utilizados(arvore))

    achados.sort(key=lambda a: (_ORDEM_GRAVIDADE.get(a["gravidade"], 99), a["linha"], a["tipo"]))
    contagem = {"critica": 0, "alta": 0, "media": 0, "baixa": 0}
    for item in achados:
        if item["gravidade"] in contagem:
            contagem[item["gravidade"]] += 1

    return {
        "codigo_valido": True,
        "vazio": False,
        "total_achados": len(achados),
        "veredito": "limpo" if not achados else "problemas_encontrados",
        "contagem_por_gravidade": contagem,
        "achados": achados,
        "resumo": (
            "Nenhum antipadrão detectado."
            if not achados
            else f"{len(achados)} achado(s) detectado(s), ordenados por gravidade."
        ),
    }


def _normalizar_categoria(valor: Any) -> str:
    """Normaliza nome de categoria removendo acentos, espaços e caixa alta."""
    if not isinstance(valor, str):
        return ""
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFKD", valor) if not unicodedata.combining(ch)
    )
    return sem_acento.strip().lower()


def gerar_checklist_revisao(tipo_mudanca: str = "geral") -> dict:
    """Gera checklist estruturado de revisão técnica sênior para o tipo de mudança."""
    chave = _normalizar_categoria(tipo_mudanca)
    usou_fallback = chave not in _CHECKLISTS_REVISAO
    categoria_aplicada = "geral" if usou_fallback else chave
    dados = _CHECKLISTS_REVISAO[categoria_aplicada]
    return {
        "tipo_mudanca": categoria_aplicada,
        "tipo_solicitado": tipo_mudanca if isinstance(tipo_mudanca, str) else "",
        "fallback_geral": usou_fallback,
        "foco": dados["foco"],
        "criterio_bloqueio": dados["criterio_bloqueio"],
        "total_itens": len(dados["itens"]),
        "itens": [dict(item) for item in dados["itens"]],
    }


FERRAMENTAS: list[ChatCompletionToolParam] = [
    SOMAR_TOOL_SCHEMA,
    {
        "type": "function",
        "function": {
            "name": "analisar_complexidade_codigo",
            "description": (
                "Analisa código Python via AST calculando linhas, parâmetros, profundidade "
                "de aninhamento e complexidade ciclomática por função."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {
                        "type": "string",
                        "description": "Trecho ou módulo de código Python a ser medido.",
                    },
                },
                "required": ["codigo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detectar_antipadroes_python",
            "description": (
                "Inspeciona código Python via AST para encontrar bugs, riscos de segurança e "
                "estilo ordenados por gravidade, sem inventar problemas em código limpo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {
                        "type": "string",
                        "description": "Trecho ou módulo de código Python a ser inspecionado.",
                    },
                },
                "required": ["codigo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gerar_checklist_revisao",
            "description": (
                "Retorna checklist de revisão técnica sênior por categoria: "
                "api, concorrencia, seguranca, refatoracao ou geral."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo_mudanca": {
                        "type": "string",
                        "description": (
                            "Categoria da mudança: 'api', 'concorrencia', 'seguranca', "
                            "'refatoracao' ou 'geral' (padrão 'geral')."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
]

EXECUTORES: dict[str, Callable[..., Any]] = {
    "somar": somar,
    "analisar_complexidade_codigo": analisar_complexidade_codigo,
    "detectar_antipadroes_python": detectar_antipadroes_python,
    "gerar_checklist_revisao": gerar_checklist_revisao,
}


def carregar_contexto() -> str:
    """Carrega `agent-lint.md` com seção `# Memória` neutra, sem vazar `memory.md` do Organizador."""
    return agent_core.carregar_contexto(
        AGENT_MD,
        memory_md=None,
        memoria_padrao=MEMORIA_PADRAO,
    )


def executar_ferramenta(nome: str, argumentos: dict) -> str:
    """Executa apenas ferramentas permitidas ao perfil Lint."""
    return agent_core.executar_ferramenta(nome, argumentos, EXECUTORES)


def responder(mensagens: list[ChatCompletionMessageParam], verboso: bool = False) -> str:
    """Executa o loop ReAct compartilhado com isolamento estrito das ferramentas do perfil Lint."""
    return agent_core.executar_loop_react(
        mensagens,
        FERRAMENTAS,
        EXECUTORES,
        verboso=verboso,
    )
