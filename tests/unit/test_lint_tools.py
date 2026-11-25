"""Testes unitários do perfil Lint (`agent_lint`) e suas ferramentas de revisão técnica."""

import json
import re
from pathlib import Path

import pytest

import agent
import agent_core
import agent_lint


def _extrair_ferramentas_md(md_path: Path) -> list[str]:
    """Extrai nomes de ferramentas da seção `## Ferramentas disponíveis`."""
    linhas = md_path.read_text(encoding="utf-8").splitlines()
    dentro_secao = False
    nomes: list[str] = []
    padrao = re.compile(r"^\|\s*`([a-zA-Z0-9_]+)`\s*\|")
    for linha in linhas:
        if linha.startswith("## "):
            if linha.strip() == "## Ferramentas disponíveis":
                dentro_secao = True
                continue
            if dentro_secao:
                break
        if dentro_secao:
            match = padrao.match(linha)
            if match:
                nomes.append(match.group(1))
    return nomes


# ==============================================================================
# SEÇÃO A — Contrato do perfil e isolamento estrito
# ==============================================================================


def test_lint_contrato_publico_e_paridade_tools():
    """Garante exposição exclusiva de `somar` e das 3 ferramentas Lint com paridade 1:1."""
    esperado = {
        "somar",
        "analisar_complexidade_codigo",
        "detectar_antipadroes_python",
        "gerar_checklist_revisao",
    }
    assert agent_lint.PERFIL_NOME == "agent-lint.md"
    assert agent_lint.AGENT_MD.name == "agent-lint.md"
    nomes_schema = [t["function"]["name"] for t in agent_lint.FERRAMENTAS]
    assert len(nomes_schema) == 4
    assert set(nomes_schema) == esperado
    assert set(agent_lint.EXECUTORES.keys()) == esperado
    assert agent_core.obter_modulo_perfil("agent-lint.md") is agent_lint

    proibidas = {
        "obter_pastas_padrao",
        "listar_arquivos",
        "criar_pasta",
        "mover_arquivo",
        "ler_conteudo_ou_resumo",
        "verificar_sintaxe_python",
        "analisar_logica_codigo",
        "gerar_exemplo_analogo",
        "consultar_base_conhecimento",
        "verificar_status_chamado",
        "registrar_escalonamento",
    }
    assert set(agent_lint.EXECUTORES.keys()).isdisjoint(proibidas)


def test_lint_carregar_contexto_sem_vazamento_memory_md(monkeypatch, tmp_path):
    """Garante carregamento de `agent-lint.md` com memória neutra e sem vazar `memory.md`."""
    ctx = agent_lint.carregar_contexto()
    assert "Lint" in ctx
    assert "Conclusão primeiro" in ctx
    assert "# Memória" in ctx
    assert agent_lint.MEMORIA_PADRAO in ctx
    assert "Fotos da viagem para europa" not in ctx
    assert "Boletos e Comprovantes" not in ctx

    md_path = agent_core.RAIZ / "agent-lint.md"
    assert set(_extrair_ferramentas_md(md_path)) == set(agent_lint.EXECUTORES.keys())
    conteudo_md = md_path.read_text(encoding="utf-8")
    assert "Se o código estiver bom, diga que está bom e pare." in conteudo_md
    assert "## Exemplo do tom" in conteudo_md

    custom_md = tmp_path / "lint_custom.md"
    custom_md.write_text("Lint Customizado", encoding="utf-8")
    monkeypatch.setattr(agent_lint, "AGENT_MD", custom_md)
    assert "Lint Customizado" in agent_lint.carregar_contexto()

    monkeypatch.setattr(agent_lint, "AGENT_MD", tmp_path / "ausente.md")
    assert "Você é um assistente." in agent_lint.carregar_contexto()


def test_lint_executar_ferramenta_despacho_e_bloqueio():
    """Valida despacho de `somar` e das 3 ferramentas Lint, bloqueando ferramentas alheias."""
    casos = [
        ("somar", {"a": 15, "b": 27}),
        ("analisar_complexidade_codigo", {"codigo": "def f(x):\n    return x\n"}),
        ("detectar_antipadroes_python", {"codigo": "def f(x):\n    return x\n"}),
        ("gerar_checklist_revisao", {"tipo_mudanca": "api"}),
    ]
    for nome, args in casos:
        dados = json.loads(agent_lint.executar_ferramenta(nome, args))
        json.dumps(dados, allow_nan=False, ensure_ascii=False)
        assert not dados.get("erro")

    for proibida in ("listar_arquivos", "verificar_sintaxe_python", "consultar_base_conhecimento"):
        err = json.loads(agent_lint.executar_ferramenta(proibida, {}))
        assert "erro" in err
        assert "não existe" in err["erro"]


# ==============================================================================
# SEÇÃO B — `analisar_complexidade_codigo`
# ==============================================================================


def test_complexidade_funcao_simples_vs_ramificada():
    """Compara função simples (CC=1) com função ramificada (if/for/and/elif/while)."""
    simples = "def inc(x):\n    return x + 1\n"
    res_s = agent_lint.analisar_complexidade_codigo(simples)
    assert res_s["codigo_valido"] is True
    assert res_s["total_funcoes"] == 1
    m_s = res_s["funcoes"][0]
    assert m_s["complexidade_ciclomatica"] == 1
    assert m_s["profundidade_aninhamento"] == 0
    assert m_s["parametros"] == 1
    assert res_s["alertas"] == []

    ramificada = (
        "def proc(itens, ativo):\n"
        "    total = 0\n"
        "    if ativo and len(itens) > 0:\n"
        "        for x in itens:\n"
        "            if x > 10:\n"
        "                total += x\n"
        "            elif x < 0:\n"
        "                while total > 0:\n"
        "                    total -= 1\n"
        "    return total\n"
    )
    res_r = agent_lint.analisar_complexidade_codigo(ramificada)
    m_r = res_r["funcoes"][0]
    assert m_r["complexidade_ciclomatica"] == 7
    assert m_r["profundidade_aninhamento"] == 4


def test_complexidade_cadeia_elif_nao_infla_aninhamento():
    """Garante que `if / elif / elif / else` mantém profundidade 1 com CC=4."""
    codigo = (
        "def classificar(n):\n"
        "    if n < 0:\n"
        "        return 'neg'\n"
        "    elif n == 0:\n"
        "        return 'zero'\n"
        "    elif n < 10:\n"
        "        return 'peq'\n"
        "    else:\n"
        "        return 'grande'\n"
    )
    res = agent_lint.analisar_complexidade_codigo(codigo)
    m = res["funcoes"][0]
    assert m["profundidade_aninhamento"] == 1
    assert m["complexidade_ciclomatica"] == 4


def test_complexidade_gera_alertas_limiares():
    """Valida alertas de complexidade (>10, >15), aninhamento (>=4), >5 params e >50 linhas."""
    ramos = "\n".join(f"    if x == {i}:\n        return {i}" for i in range(16))
    corpo_longo = "\n".join("    y += 1" for _ in range(52))
    codigo = (
        "def complexa(a, b, c, d, e, f):\n"
        "    x = a\n"
        f"{ramos}\n"
        "    if a:\n"
        "        if b:\n"
        "            if c:\n"
        "                if d:\n"
        "                    x += 1\n"
        "    y = 0\n"
        f"{corpo_longo}\n"
        "    return x + y\n"
    )
    res = agent_lint.analisar_complexidade_codigo(codigo)
    tipos = {a["tipo"] for a in res["alertas"]}
    assert "complexidade_excessiva" in tipos
    assert "aninhamento_profundo" in tipos
    assert "funcao_longa" in tipos
    assert "muitos_parametros" in tipos
    ordem = [agent_lint._ORDEM_GRAVIDADE[a["gravidade"]] for a in res["alertas"]]
    assert ordem == sorted(ordem)


def test_complexidade_metodos_async_e_modulo_sem_funcoes():
    """Analisa métodos async em classes (`A.m`) e código de módulo sem funções."""
    codigo_cls = (
        "class A:\n"
        "    async def m(self, *args, **kwargs):\n"
        "        return len(args) + len(kwargs)\n"
    )
    res_cls = agent_lint.analisar_complexidade_codigo(codigo_cls)
    assert res_cls["total_funcoes"] == 1
    assert res_cls["funcoes"][0]["nome"] == "A.m"
    assert res_cls["funcoes"][0]["parametros"] == 3

    codigo_mod = "x = 1\nif x > 0:\n    print(x)\n"
    res_mod = agent_lint.analisar_complexidade_codigo(codigo_mod)
    assert res_mod["total_funcoes"] == 0
    assert res_mod["complexidade_maxima"] == 2
    assert res_mod["profundidade_maxima"] == 1


@pytest.mark.parametrize("entrada", ["", "   \n", "if True print('erro')", None, 123])
def test_complexidade_entradas_invalidas_vazio_e_syntax_error(entrada):
    """Trata entradas vazias, syntax error e não-strings sem lançar exceções."""
    res = agent_lint.analisar_complexidade_codigo(entrada)  # type: ignore[arg-type]
    assert isinstance(res, dict)
    assert res["total_funcoes"] == 0
    json.dumps(res, allow_nan=False, ensure_ascii=False)


# ==============================================================================
# SEÇÃO C — `detectar_antipadroes_python`
# ==============================================================================


def test_antipadroes_codigo_limpo_zero_achados():
    """Código limpo com imports usados, `is None` e `__all__` retorna 0 achados (Regra 3)."""
    codigo = (
        "from __future__ import annotations\n"
        "from typing import Any\n\n"
        "__all__ = ['processar']\n\n"
        "def processar(valor: 'Any | None') -> int:\n"
        "    if valor is None:\n"
        "        return 0\n"
        "    try:\n"
        "        return int(valor)\n"
        "    except ValueError:\n"
        "        return -1\n"
    )
    res = agent_lint.detectar_antipadroes_python(codigo)
    assert res["codigo_valido"] is True
    assert res["total_achados"] == 0
    assert res["achados"] == []
    assert res["veredito"] == "limpo"


def test_antipadroes_detecta_bugs_e_seguranca():
    """Detecta eval/exec, subprocess shell=True, defaults mutáveis, bare/pass except e global."""
    codigo = (
        "import subprocess\n\n"
        "cache = []\n\n"
        "def f(a=[], *, b=set()):\n"
        "    global cache\n"
        "    cache.append(1)\n"
        "    eval('1 + 1')\n"
        "    exec('x = 1')\n"
        "    subprocess.run('echo ok', shell=True)\n"
        "    try:\n"
        "        return a\n"
        "    except:\n"
        "        pass\n"
        "    try:\n"
        "        return b\n"
        "    except Exception:\n"
        "        pass\n"
    )
    res = agent_lint.detectar_antipadroes_python(codigo)
    tipos = {item["tipo"] for item in res["achados"]}
    assert "uso_eval" in tipos
    assert "uso_exec" in tipos
    assert "subprocess_shell_true" in tipos
    assert "argumento_mutavel_padrao" in tipos
    assert "bare_except_silenciado" in tipos
    assert "except_silenciado" in tipos
    assert "mutacao_global" in tipos


def test_antipadroes_global_com_anotacao_pura_sem_valor_nao_eh_mutacao():
    """Garante que `global g` com `g: int` (AnnAssign sem valor) não gera falso positivo."""
    codigo_leitura = (
        "g = 0\n\n"
        "def ler_global() -> int:\n"
        "    global g\n"
        "    g: int\n"
        "    return g\n"
    )
    res_limpo = agent_lint.detectar_antipadroes_python(codigo_leitura)
    assert res_limpo["codigo_valido"] is True
    assert not any(a["tipo"] == "mutacao_global" for a in res_limpo["achados"])
    assert res_limpo["total_achados"] == 0
    assert res_limpo["veredito"] == "limpo"

    codigo_mutacao = (
        "g = 0\n\n"
        "def atualizar_global() -> None:\n"
        "    global g\n"
        "    g: int = 2\n"
    )
    res_mut = agent_lint.detectar_antipadroes_python(codigo_mutacao)
    assert any(a["tipo"] == "mutacao_global" for a in res_mut["achados"])


def test_antipadroes_detecta_estilo_none_e_import_nao_utilizado():
    """Detecta comparações `== None` / `!= None` e imports não referenciados."""
    codigo = (
        "import os\n"
        "from math import sin as s\n\n"
        "def checar(x):\n"
        "    if x == None or None != x:\n"
        "        return False\n"
        "    return True\n"
    )
    res = agent_lint.detectar_antipadroes_python(codigo)
    tipos = [item["tipo"] for item in res["achados"]]
    assert "comparacao_none_igualdade" in tipos
    assert tipos.count("import_nao_utilizado") == 2


def test_antipadroes_ordena_por_gravidade_antes_de_linha():
    """Garante ordenação por gravidade (alta -> media -> baixa) mesmo com estilo no topo."""
    codigo = (
        "import os\n"
        "x = 1\n"
        "if x == None:\n"
        "    pass\n"
        "def bug(a=[]):\n"
        "    global x\n"
        "    x += 1\n"
        "    return eval('1')\n"
    )
    res = agent_lint.detectar_antipadroes_python(codigo)
    gravidades = [agent_lint._ORDEM_GRAVIDADE[a["gravidade"]] for a in res["achados"]]
    assert gravidades == sorted(gravidades)
    assert res["achados"][0]["gravidade"] == "alta"
    assert res["achados"][-1]["gravidade"] == "baixa"


@pytest.mark.parametrize("entrada", ["x = 'olá 🚀'\n", "", "def x(:\n pass", None, 42])
def test_antipadroes_unicode_vazio_syntax_error_e_nao_string(entrada):
    """Garante retorno JSON estrito em Unicode, vazio, SyntaxError e não-strings."""
    res = agent_lint.detectar_antipadroes_python(entrada)  # type: ignore[arg-type]
    assert isinstance(res, dict)
    json.dumps(res, allow_nan=False, ensure_ascii=False)


# ==============================================================================
# SEÇÃO D — `gerar_checklist_revisao`
# ==============================================================================


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("api", "api"),
        ("API", "api"),
        ("concorrencia", "concorrencia"),
        ("Concorrência", "concorrencia"),
        ("seguranca", "seguranca"),
        ("Segurança", "seguranca"),
        ("refatoracao", "refatoracao"),
        ("Refatoração", "refatoracao"),
        ("geral", "geral"),
    ],
)
def test_checklist_todas_categorias_e_normalizacao(entrada, esperado):
    """Valida todas as categorias e normalização de acentos/caixa."""
    res = agent_lint.gerar_checklist_revisao(entrada)
    assert res["tipo_mudanca"] == esperado
    assert res["fallback_geral"] is False
    assert res["foco"]
    assert res["criterio_bloqueio"]
    assert res["total_itens"] == len(res["itens"]) and len(res["itens"]) > 0


@pytest.mark.parametrize("entrada", ["", "   ", "desconhecido", None])
def test_checklist_fallback_para_geral(entrada):
    """Aplica fallback seguro para `geral` em categorias desconhecidas, vazias ou None."""
    res = agent_lint.gerar_checklist_revisao(entrada)  # type: ignore[arg-type]
    assert res["tipo_mudanca"] == "geral"
    assert res["fallback_geral"] is True
    assert len(res["itens"]) > 0


# ==============================================================================
# SEÇÃO E — Loop ReAct mockado de `agent_lint.responder`
# ==============================================================================


def test_lint_responder_envia_apenas_tools_lint_e_executa_multi_turno(
    mock_openai, criar_resposta_mock, criar_tool_call_mock
):
    """Valida envio exclusivo de `agent_lint.FERRAMENTAS` e execução multi-turno."""
    tc1 = criar_tool_call_mock(
        "c1",
        "detectar_antipadroes_python",
        json.dumps({"codigo": "def f(a=[]):\n    return a\n"}),
    )
    tc2 = criar_tool_call_mock(
        "c2",
        "analisar_complexidade_codigo",
        json.dumps({"codigo": "def f(a=[]):\n    return a\n"}),
    )
    tc3 = criar_tool_call_mock("c3", "somar", json.dumps({"a": 1, "b": 2}))
    mock_openai.chat.completions.create.side_effect = [
        criar_resposta_mock(tool_calls=[tc1, tc2]),
        criar_resposta_mock(tool_calls=[tc3]),
        criar_resposta_mock(content="Reprovado: default mutável em f()."),
    ]
    mensagens = [
        {"role": "system", "content": agent_lint.carregar_contexto()},
        {"role": "user", "content": "Revise este código."},
    ]

    resposta = agent_lint.responder(mensagens)

    assert "Reprovado" in resposta
    assert mock_openai.chat.completions.create.call_args_list[0].kwargs["tools"] == agent_lint.FERRAMENTAS
    tool_msgs = [m for m in mensagens if m.get("role") == "tool"]
    assert len(tool_msgs) == 3
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2", "c3"]


def test_lint_responder_tool_use_failed_escopo_estrito(mock_openai, criar_resposta_mock):
    """Garante recuperação de `tool_use_failed` restrita às 4 ferramentas do perfil Lint."""
    mock_openai.chat.completions.create.side_effect = [
        RuntimeError("Error code: 400 - tool_use_failed"),
        criar_resposta_mock(content="Código limpo."),
    ]
    mensagens = [{"role": "user", "content": "Revise"}]
    resposta = agent_lint.responder(mensagens)
    assert resposta == "Código limpo."
    aviso = next(m["content"] for m in mensagens if "Use EXATAMENTE" in m.get("content", ""))
    for permitida in (
        "somar",
        "analisar_complexidade_codigo",
        "detectar_antipadroes_python",
        "gerar_checklist_revisao",
    ):
        assert permitida in aviso
    for alheia in ("listar_arquivos", "verificar_sintaxe_python", "consultar_base_conhecimento"):
        assert alheia not in aviso


def test_lint_responder_circuit_breaker_max_iteracoes(
    mock_openai, criar_resposta_mock, criar_tool_call_mock, monkeypatch
):
    """Garante encerramento ao atingir `MAX_ITERACOES`."""
    monkeypatch.setattr(agent, "MAX_ITERACOES", 2)
    tc = criar_tool_call_mock("c_loop", "gerar_checklist_revisao", json.dumps({"tipo_mudanca": "geral"}))
    resp_tool = criar_resposta_mock(tool_calls=[tc])
    mock_openai.chat.completions.create.side_effect = [resp_tool, resp_tool, resp_tool]
    mensagens = [{"role": "user", "content": "Checklist"}]

    out = agent_lint.responder(mensagens)
    assert mock_openai.chat.completions.create.call_count == 2
    assert out == "Atingi o limite de iterações sem concluir. Tente reformular o pedido."
