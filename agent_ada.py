"""
Agente Ada — Tutora Socrática (`agent-ada.md`).

Fornece suporte isolado às ferramentas de apoio à aprendizagem de Python e lógica
(`somar`, `verificar_sintaxe_python`, `analisar_logica_codigo`, `gerar_exemplo_analogo`),
respeitando estritamente o método socrático (sem entregar código pronto de solução)
e sem vazar `memory.md` do Organizador.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable
import unicodedata

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

import agent_core
from agent_core import SOMAR_TOOL_SCHEMA, somar

PERFIL_NOME: str = "agent-ada.md"
AGENT_MD: Path = agent_core.RAIZ / PERFIL_NOME
MEMORIA_PADRAO: str = "Nenhuma preferência ou histórico específico registrado para este perfil."

_ANALOGIAS_CONCEITOS: dict[str, dict[str, str]] = {
    "while": {
        "conceito": "while",
        "dominio_analogo": "Monitoramento de bateria de um drone em voo",
        "analogia": (
            "Imagine um drone que decola com bateria em 100% e gasta 20% a cada foto tirada. "
            "Enquanto a bateria estiver acima de 20%, ele fotografa e desconta 20% da carga. "
            "Se ninguém atualizar o nível da bateria dentro da repetição, a condição continua "
            "sempre verdadeira e o drone tenta fotografar indefinidamente."
        ),
        "pergunta_reflexao": (
            "No seu laço, qual valor está sendo testado na condição e como ele deveria mudar a cada passo?"
        ),
    },
    "for": {
        "conceito": "for",
        "dominio_analogo": "Entrega de cartas em casas numeradas de uma rua",
        "analogia": (
            "Um carteiro recebe uma lista fixa de endereços e visita cada casa uma única vez, "
            "da primeira até a última, sem precisar calcular manualmente quando a rua acaba."
        ),
        "pergunta_reflexao": (
            "Qual coleção finita de itens você está percorrendo e o que precisa fazer com cada item por vez?"
        ),
    },
    "if": {
        "conceito": "if",
        "dominio_analogo": "Triagem de encomendas por faixa de peso",
        "analogia": (
            "Na esteira dos correios, cada caixa passa por uma balança: se pesa até 1 kg vai para "
            "o cesto leve; senão, se pesa até 5 kg vai para o médio; caso contrário, segue para carga pesada."
        ),
        "pergunta_reflexao": (
            "Quais critérios separam cada caminho e o que deve acontecer se nenhuma condição for atendida?"
        ),
    },
    "funcao": {
        "conceito": "funcao",
        "dominio_analogo": "Máquina de café com entrada e entrega no copo",
        "analogia": (
            "Uma máquina de café recebe água e pó (parâmetros), prepara a bebida internamente e "
            "devolve o café pronto no copo (return). Só exibir uma mensagem na tela seria como "
            "a máquina acender um aviso 'café pronto' sem entregar a bebida."
        ),
        "pergunta_reflexao": (
            "Quais informações entram na sua função e qual resultado ela precisa devolver para quem a chamou?"
        ),
    },
    "lista": {
        "conceito": "lista",
        "dominio_analogo": "Vagões numerados de um trem",
        "analogia": (
            "Pense em uma sequência de vagões numerados a partir do vagão 0. Você consegue consultar "
            "um vagão específico pela posição ou percorrer todos do início ao fim em ordem."
        ),
        "pergunta_reflexao": (
            "Se a coleção tem N elementos, qual posição representa o primeiro item e qual representa o último?"
        ),
    },
    "recursao": {
        "conceito": "recursao",
        "dominio_analogo": "Bonecas russas (matrioskas) encaixadas",
        "analogia": (
            "Cada boneca aberta revela outra igual um pouco menor, até você alcançar a menor boneca "
            "maciça que não se abre mais — esse é o caso base que interrompe a abertura."
        ),
        "pergunta_reflexao": (
            "Qual é o caso mais simples em que o problema pode ser respondido diretamente sem se dividir?"
        ),
    },
    "acumulador": {
        "conceito": "acumulador",
        "dominio_analogo": "Cofrinho de moedas",
        "analogia": (
            "Antes de guardar a primeira moeda, o cofrinho começa com saldo zero. A cada moeda nova, "
            "somamos o valor dela ao total que já estava guardado dentro do cofrinho."
        ),
        "pergunta_reflexao": (
            "Em que momento o acumulador deve ser zerado: antes da repetição começar ou dentro dela?"
        ),
    },
    "variavel": {
        "conceito": "variavel",
        "dominio_analogo": "Etiqueta em uma caixa organizadora",
        "analogia": (
            "Uma variável funciona como uma etiqueta colada em uma caixa: você pode trocar o conteúdo "
            "guardado lá dentro ao longo do tempo, e caixas criadas dentro de uma sala (função) "
            "só ficam visíveis dentro daquela sala."
        ),
        "pergunta_reflexao": (
            "Onde esse valor nasce no seu programa e em qual etapa você espera que ele seja atualizado?"
        ),
    },
}

_ALIASES_CONCEITOS: dict[str, str] = {
    "while": "while",
    "laco while": "while",
    "loop while": "while",
    "loop infinito": "while",
    "condicao de parada": "while",
    "for": "for",
    "laco for": "for",
    "loop for": "for",
    "loop": "for",
    "laco": "for",
    "repeticao": "for",
    "iteracao": "for",
    "if": "if",
    "elif": "if",
    "else": "if",
    "if else": "if",
    "condicional": "if",
    "condicionais": "if",
    "decisao": "if",
    "funcao": "funcao",
    "funcoes": "funcao",
    "def": "funcao",
    "return": "funcao",
    "retorno": "funcao",
    "parametro": "funcao",
    "lista": "lista",
    "listas": "lista",
    "list": "lista",
    "array": "lista",
    "indice": "lista",
    "recursao": "recursao",
    "recursividade": "recursao",
    "recursivo": "recursao",
    "caso base": "recursao",
    "acumulador": "acumulador",
    "contador": "acumulador",
    "soma": "acumulador",
    "variavel": "variavel",
    "variaveis": "variavel",
    "atribuicao": "variavel",
    "escopo": "variavel",
}


def _normalizar_conceito(texto: str) -> str:
    """Normaliza acentos, caixa e espaçamento para mapeamento de conceitos."""
    sem_acentos = "".join(
        ch for ch in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(ch)
    )
    return " ".join(sem_acentos.lower().strip().split())


def _nomes_em_expressao(expr: ast.AST) -> set[str]:
    """Coleta nomes de variáveis referenciados em uma expressão AST, ignorando chamadas diretas."""
    chamadas_diretas = {
        nodo.func
        for nodo in ast.walk(expr)
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
    }
    return {
        nodo.id
        for nodo in ast.walk(expr)
        if isinstance(nodo, ast.Name) and nodo not in chamadas_diretas
    }


_ESCOPOS_ISOLADOS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_LACOS_ANINHADOS = (ast.For, ast.AsyncFor, ast.While)
_MATCH_BIND_TYPES = tuple(
    tipo
    for tipo in (
        getattr(ast, "MatchAs", None),
        getattr(ast, "MatchStar", None),
        getattr(ast, "MatchMapping", None),
    )
    if tipo is not None
)
_METODOS_MUTACAO = frozenset({
    "pop",
    "popleft",
    "popitem",
    "remove",
    "clear",
    "append",
    "extend",
    "insert",
    "add",
    "update",
    "setdefault",
    "discard",
    "sort",
    "reverse",
})


def _extrair_nomes_alvo(alvo: ast.AST) -> set[str]:
    """Extrai identificadores de destino em atribuições, desempacotamentos, atributos ou subscritos."""
    if isinstance(alvo, (ast.Tuple, ast.List)):
        nomes: set[str] = set()
        for item in alvo.elts:
            nomes.update(_extrair_nomes_alvo(item))
        return nomes
    if isinstance(alvo, ast.Starred):
        return _extrair_nomes_alvo(alvo.value)
    atual = alvo
    while isinstance(atual, (ast.Attribute, ast.Subscript)):
        atual = atual.value
    if isinstance(atual, ast.Name):
        return {atual.id}
    return set()


def _empilhar_filhos_laco(
    pilha: list[tuple[ast.AST, bool]],
    atual: ast.AST,
    em_laco_interno: bool,
) -> None:
    """Empilha nós filhos mantendo `orelse` de laços aninhados fora do escopo do laço interno."""
    if isinstance(atual, _LACOS_ANINHADOS):
        orelse_ids = {id(item) for item in atual.orelse}
        for filho in ast.iter_child_nodes(atual):
            no_orelse = id(filho) in orelse_ids
            pilha.append((filho, em_laco_interno if no_orelse else True))
        return
    pilha.extend((filho, em_laco_interno) for filho in ast.iter_child_nodes(atual))


def _nomes_modificados_nodo(atual: ast.AST) -> set[str]:
    """Extrai identificadores alterados diretamente por um nó AST no mesmo escopo."""
    if isinstance(atual, (ast.Assign, ast.Delete)):
        nomes: set[str] = set()
        for alvo in atual.targets:
            nomes.update(_extrair_nomes_alvo(alvo))
        return nomes
    if isinstance(atual, (ast.AugAssign, ast.For, ast.AsyncFor, ast.NamedExpr)):
        return _extrair_nomes_alvo(atual.target)
    if isinstance(atual, ast.AnnAssign) and atual.value is not None:
        return _extrair_nomes_alvo(atual.target)
    if isinstance(atual, ast.ExceptHandler):
        return {atual.name} if atual.name else set()
    if isinstance(atual, (ast.With, ast.AsyncWith)):
        nomes_with: set[str] = set()
        for item in atual.items:
            if item.optional_vars is not None:
                nomes_with.update(_extrair_nomes_alvo(item.optional_vars))
        return nomes_with
    if isinstance(atual, ast.Call) and isinstance(atual.func, ast.Attribute) and atual.func.attr in _METODOS_MUTACAO:
        return _extrair_nomes_alvo(atual.func.value)
    if _MATCH_BIND_TYPES and isinstance(atual, _MATCH_BIND_TYPES):
        nome = getattr(atual, "name", None) or getattr(atual, "rest", None)
        return {nome} if nome else set()
    return set()


def _nomes_modificados_no_bloco(instrucoes: list[ast.stmt]) -> tuple[set[str], bool]:
    """Identifica variáveis alteradas no escopo do bloco e se há saída (`break`/`return`)."""
    modificados: set[str] = set()
    tem_saida = False
    pilha: list[tuple[ast.AST, bool]] = [(stmt, False) for stmt in instrucoes]
    while pilha:
        atual, em_laco_interno = pilha.pop()
        if isinstance(atual, _ESCOPOS_ISOLADOS):
            continue
        if isinstance(atual, ast.Return) or (isinstance(atual, ast.Break) and not em_laco_interno):
            tem_saida = True
        modificados.update(_nomes_modificados_nodo(atual))
        _empilhar_filhos_laco(pilha, atual, em_laco_interno)
    return modificados, tem_saida


def _eh_condicao_constante_verdadeira(expr: ast.expr) -> bool:
    """Identifica condições constantes sempre verdadeiras, como `while True:`."""
    return isinstance(expr, ast.Constant) and bool(expr.value)


def _tem_saida_laco(instrucoes: list[ast.stmt]) -> bool:
    """Verifica se o bloco possui `break` deste laço ou `return` no mesmo escopo."""
    pilha: list[tuple[ast.AST, bool]] = [(stmt, False) for stmt in instrucoes]
    while pilha:
        atual, em_laco_interno = pilha.pop()
        if isinstance(atual, ast.Return):
            return True
        if isinstance(atual, ast.Break) and not em_laco_interno:
            return True
        if isinstance(atual, _ESCOPOS_ISOLADOS):
            continue
        _empilhar_filhos_laco(pilha, atual, em_laco_interno)
    return False


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


def _analisar_laco_while(nodo: ast.While) -> tuple[str | None, str | None]:
    """Verifica se variáveis testadas no `while` recebem atualização no corpo do laço."""
    vars_condicao = _nomes_em_expressao(nodo.test)
    if not vars_condicao:
        if _eh_condicao_constante_verdadeira(nodo.test) and not _tem_saida_laco(nodo.body):
            obs = (
                f"Laço 'while' na linha {nodo.lineno} usa condição constante sempre verdadeira "
                "e não possui saída explícita (como 'break' ou 'return')."
            )
            pergunta = (
                "Em qual situação esse laço deve parar, e o que dentro dele poderia "
                "sinalizar esse momento de saída?"
            )
            return obs, pergunta
        return None, None
    modificados, tem_saida = _nomes_modificados_no_bloco(nodo.body)
    for sub in ast.walk(nodo.test):
        if isinstance(sub, ast.NamedExpr):
            modificados.update(_extrair_nomes_alvo(sub.target))
    if not tem_saida and vars_condicao.isdisjoint(modificados):
        nomes = ", ".join(sorted(vars_condicao))
        obs = (
            f"Laço 'while' na linha {nodo.lineno} testa ({nomes}), mas nenhuma dessas "
            "variáveis é atualizada no corpo do laço e não há 'break'."
        )
        pergunta = (
            f"O que precisa acontecer com ({nomes}) dentro do laço para que a condição "
            "de parada deixe de ser verdadeira?"
        )
        return obs, pergunta
    return None, None


def _inspecionar_funcao(nodo: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[dict[str, Any], bool, bool]:
    """Extrai metadados seguros de uma função AST sem expor código pronto."""
    possui_return = False
    recursiva = False
    possui_if = False
    for sub in _nos_do_escopo(nodo.body):
        if isinstance(sub, ast.Return):
            possui_return = True
        elif isinstance(sub, ast.If):
            possui_if = True
        elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == nodo.name:
            recursiva = True
    info = {
        "nome": nodo.name,
        "linha": nodo.lineno,
        "parametros": [arg.arg for arg in nodo.args.args],
        "possui_return": possui_return,
        "recursiva": recursiva,
    }
    return info, possui_return, (recursiva and not possui_if)


def _registrar_funcao_ast(
    nodo: ast.FunctionDef | ast.AsyncFunctionDef,
    estado: dict[str, Any],
) -> None:
    """Registra metadados e observações socráticas de uma função AST."""
    info, tem_return, rec_sem_if = _inspecionar_funcao(nodo)
    estado["funcoes"].append(info)
    if info["recursiva"]:
        estado["recursivas"].append(nodo.name)
    if not tem_return:
        estado["observacoes"].append(f"Função '{nodo.name}' não possui instrução 'return' explícita.")
        estado["perguntas"].append(
            f"A função '{nodo.name}' deveria devolver um valor para quem a chama ou apenas exibir algo?"
        )
    if rec_sem_if:
        estado["observacoes"].append(
            f"Função '{nodo.name}' chama a si mesma sem condicional visível para caso base."
        )
        estado["perguntas"].append("Qual condição simples deve interromper as chamadas recursivas?")


def _registrar_atribuicao_ast(nodo: ast.AST, variaveis: set[str]) -> None:
    """Registra variáveis atribuídas em `Assign`, `AugAssign`, `AnnAssign` ou `NamedExpr`."""
    if isinstance(nodo, ast.Assign):
        for alvo in nodo.targets:
            variaveis.update(_extrair_nomes_alvo(alvo))
    elif isinstance(nodo, (ast.AugAssign, ast.AnnAssign, ast.NamedExpr)):
        variaveis.update(_extrair_nomes_alvo(nodo.target))


def _coletar_estrutura_ast(arvore: ast.AST) -> dict[str, Any]:
    """Percorre a AST coletando métricas estruturais e pontos de reflexão socrática."""
    estado: dict[str, Any] = {
        "funcoes": [],
        "variaveis": set(),
        "observacoes": [],
        "perguntas": [],
        "contagem": {"for": 0, "while": 0, "if": 0},
        "recursivas": [],
    }

    for nodo in ast.walk(arvore):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _registrar_funcao_ast(nodo, estado)
        elif isinstance(nodo, (ast.For, ast.AsyncFor)):
            estado["contagem"]["for"] += 1
            estado["variaveis"].update(_extrair_nomes_alvo(nodo.target))
        elif isinstance(nodo, ast.While):
            estado["contagem"]["while"] += 1
            obs_w, perg_w = _analisar_laco_while(nodo)
            if obs_w and perg_w:
                estado["observacoes"].append(obs_w)
                estado["perguntas"].append(perg_w)
        elif isinstance(nodo, ast.If):
            estado["contagem"]["if"] += 1
        else:
            _registrar_atribuicao_ast(nodo, estado["variaveis"])

    tem_laco = estado["contagem"]["for"] > 0 or estado["contagem"]["while"] > 0
    if tem_laco and estado["contagem"]["if"] == 0 and not estado["observacoes"]:
        estado["observacoes"].append(
            "Há repetição sem seleção condicional interna; todos os passos seguem o mesmo fluxo."
        )
        estado["perguntas"].append(
            "Todos os elementos do laço devem ser tratados da mesma forma ou há algum filtro?"
        )

    if not estado["perguntas"]:
        estado["perguntas"].append(
            "Se você simular o código linha a linha com uma entrada pequena, o que acontece em cada passo?"
        )

    return {
        "funcoes": estado["funcoes"],
        "lacos_for": estado["contagem"]["for"],
        "lacos_while": estado["contagem"]["while"],
        "condicionais_if": estado["contagem"]["if"],
        "variaveis": sorted(estado["variaveis"]),
        "recursao_detectada": sorted(set(estado["recursivas"])),
        "observacoes_logicas": estado["observacoes"],
        "perguntas_guia": estado["perguntas"],
    }


def verificar_sintaxe_python(codigo: str) -> dict:
    """Valida estaticamente a sintaxe de um trecho Python usando `ast.parse`, sem executar o código."""
    if not isinstance(codigo, str):
        return {
            "sintaxe_valida": False,
            "erro": "Entrada inválida: forneça uma string com código Python.",
            "pergunta_socratica": "Qual trecho de código você gostaria de verificar?",
        }
    if not codigo.strip():
        return {
            "sintaxe_valida": False,
            "vazio": True,
            "linhas": 0,
            "mensagem": "Nenhum código Python foi fornecido para verificação.",
            "pergunta_socratica": "Pode compartilhar o trecho que você está tentando escrever?",
        }
    try:
        arvore = ast.parse(codigo)
    except SyntaxError as exc:
        return {
            "sintaxe_valida": False,
            "tipo_erro": type(exc).__name__,
            "linha": exc.lineno,
            "coluna": exc.offset,
            "detalhe": exc.msg or "Estrutura sintática inválida.",
            "pergunta_socratica": (
                "Olhando para a linha indicada, o que você esperava que estivesse escrito ali?"
            ),
        }
    except ValueError:
        return {
            "sintaxe_valida": False,
            "tipo_erro": "ValueError",
            "detalhe": "O texto contém caracteres inválidos para análise sintática.",
            "pergunta_socratica": "Verifique se há caracteres estranhos ao colar o código.",
        }

    return {
        "sintaxe_valida": True,
        "linhas": len(codigo.splitlines()),
        "instrucoes_topo": len(arvore.body),
        "mensagem": "Sintaxe Python válida.",
    }


def analisar_logica_codigo(codigo: str) -> dict:
    """Analisa estaticamente estruturas de controle e fluxo lógico sem gerar código pronto de solução."""
    if not isinstance(codigo, str):
        return {
            "analisavel": False,
            "erro": "Entrada inválida: forneça uma string com código Python.",
            "perguntas_guia": ["Qual trecho de código você gostaria de analisar juntos?"],
        }
    if not codigo.strip():
        return {
            "analisavel": False,
            "vazio": True,
            "mensagem": "Nenhum código foi fornecido para análise lógica.",
            "perguntas_guia": ["Qual problema ou passo lógico você está tentando resolver agora?"],
        }
    try:
        arvore = ast.parse(codigo)
    except (SyntaxError, ValueError) as exc:
        return {
            "analisavel": False,
            "sintaxe_valida": False,
            "linha": getattr(exc, "lineno", None),
            "mensagem": "O código possui problema de sintaxe antes da análise lógica.",
            "perguntas_guia": [
                "Antes de analisar a lógica, o que você observa na estrutura da linha indicada?"
            ],
        }

    estrutura = _coletar_estrutura_ast(arvore)
    return {
        "analisavel": True,
        "sintaxe_valida": True,
        "resumo_estrutural": {
            "funcoes": estrutura["funcoes"],
            "lacos_for": estrutura["lacos_for"],
            "lacos_while": estrutura["lacos_while"],
            "condicionais_if": estrutura["condicionais_if"],
            "variaveis": estrutura["variaveis"],
            "recursao_detectada": estrutura["recursao_detectada"],
        },
        "observacoes_logicas": estrutura["observacoes_logicas"],
        "perguntas_guia": estrutura["perguntas_guia"],
    }


def gerar_exemplo_analogo(conceito: str) -> dict:
    """Fornece analogia de outro domínio e pergunta socrática para destravar um conceito sem dar solução."""
    texto = conceito if isinstance(conceito, str) else ""
    normalizado = _normalizar_conceito(texto)
    chave = _ALIASES_CONCEITOS.get(normalizado)
    if chave is not None:
        entrada = dict(_ANALOGIAS_CONCEITOS[chave])
        entrada["reconhecido"] = True
        entrada["conceito_solicitado"] = texto.strip()
        return entrada

    return {
        "reconhecido": False,
        "conceito_solicitado": texto.strip(),
        "conceito": "decomposicao_geral",
        "dominio_analogo": "Seguir uma receita culinária passo a passo",
        "analogia": (
            "Quando uma receita parece grande demais, separamos os ingredientes (entradas), "
            "conferimos cada etapa em ordem (sequência), decidimos se algo precisa de ajuste "
            "(condição) e repetimos ações até atingir o ponto certo."
        ),
        "pergunta_reflexao": (
            "Se você fosse resolver esse problema no papel antes do Python, qual seria o primeiro passo?"
        ),
    }


VERIFICAR_SINTAXE_SCHEMA: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "verificar_sintaxe_python",
        "description": (
            "Verifica estaticamente a sintaxe de um trecho de código Python sem executá-lo, "
            "retornando linha e detalhe de erro quando inválido."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "codigo": {
                    "type": "string",
                    "description": "Código-fonte Python do estudante para verificação de sintaxe.",
                },
            },
            "required": ["codigo"],
        },
    },
}

ANALISAR_LOGICA_SCHEMA: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "analisar_logica_codigo",
        "description": (
            "Inspeciona estaticamente estruturas de controle, variáveis e pontos de atenção lógica "
            "no código do estudante sem entregar código pronto de solução."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "codigo": {
                    "type": "string",
                    "description": "Código-fonte Python para análise estrutural de lógica.",
                },
            },
            "required": ["codigo"],
        },
    },
}

GERAR_EXEMPLO_ANALOGO_SCHEMA: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "gerar_exemplo_analogo",
        "description": (
            "Retorna uma analogia de outro domínio e uma pergunta socrática para explicar um "
            "conceito de programação (ex.: while, for, if, funcao, lista, recursao)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "conceito": {
                    "type": "string",
                    "description": "Conceito de lógica ou Python que o estudante precisa compreender.",
                },
            },
            "required": ["conceito"],
        },
    },
}

FERRAMENTAS: list[ChatCompletionToolParam] = [
    SOMAR_TOOL_SCHEMA,
    VERIFICAR_SINTAXE_SCHEMA,
    ANALISAR_LOGICA_SCHEMA,
    GERAR_EXEMPLO_ANALOGO_SCHEMA,
]

EXECUTORES: dict[str, Callable[..., Any]] = {
    "somar": somar,
    "verificar_sintaxe_python": verificar_sintaxe_python,
    "analisar_logica_codigo": analisar_logica_codigo,
    "gerar_exemplo_analogo": gerar_exemplo_analogo,
}


def carregar_contexto() -> str:
    """Carrega `agent-ada.md` com `# Memória` neutra, sem vazar `memory.md` do Organizador."""
    return agent_core.carregar_contexto(
        AGENT_MD,
        memory_md=None,
        memoria_padrao=MEMORIA_PADRAO,
    )


def executar_ferramenta(nome: str, argumentos: dict) -> str:
    """Executa apenas ferramentas permitidas ao perfil Ada."""
    return agent_core.executar_ferramenta(nome, argumentos, EXECUTORES)


def responder(mensagens: list[ChatCompletionMessageParam], verboso: bool = False) -> str:
    """Executa o loop ReAct compartilhado com isolamento estrito das ferramentas da Ada."""
    return agent_core.executar_loop_react(
        mensagens,
        FERRAMENTAS,
        EXECUTORES,
        verboso=verboso,
    )
