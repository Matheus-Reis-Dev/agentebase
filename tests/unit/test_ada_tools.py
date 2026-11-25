"""Testes unitários do perfil Ada (`agent_ada`) e suas ferramentas socráticas."""

import json
import re
from pathlib import Path

import pytest

import agent
import agent_ada
import agent_core


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
# SEÇÃO A — Isolamento, contrato de perfil e sincronização com Markdown
# ==============================================================================


def test_ada_isolamento_estrito_e_paridade_tools():
    """Garante exposição exclusiva de `somar` e das 3 ferramentas Ada com paridade 1:1."""
    esperado = {
        "somar",
        "verificar_sintaxe_python",
        "analisar_logica_codigo",
        "gerar_exemplo_analogo",
    }
    assert agent_ada.PERFIL_NOME == "agent-ada.md"
    assert agent_ada.AGENT_MD.name == "agent-ada.md"
    nomes_schema = [t["function"]["name"] for t in agent_ada.FERRAMENTAS]
    assert len(nomes_schema) == 4
    assert set(nomes_schema) == esperado
    assert set(agent_ada.EXECUTORES.keys()) == esperado
    assert agent_core.obter_modulo_perfil("agent-ada.md") is agent_ada

    proibidas = {
        "obter_pastas_padrao",
        "listar_arquivos",
        "criar_pasta",
        "mover_arquivo",
        "ler_conteudo_ou_resumo",
        "analisar_complexidade_codigo",
        "detectar_antipadroes_python",
        "gerar_checklist_revisao",
        "consultar_base_conhecimento",
        "verificar_status_chamado",
        "registrar_escalonamento",
    }
    assert set(agent_ada.EXECUTORES.keys()).isdisjoint(proibidas)


def test_ada_carregar_contexto_sem_vazamento_memory_md(monkeypatch, tmp_path):
    """Valida contexto da Ada sem vazar `memory.md` e com fallback em `AGENT_MD` ausente."""
    ctx = agent_ada.carregar_contexto()
    assert "Ada" in ctx
    assert "socrático" in ctx
    assert "# Memória" in ctx
    assert agent_ada.MEMORIA_PADRAO in ctx
    for nome in ("somar", "verificar_sintaxe_python", "analisar_logica_codigo", "gerar_exemplo_analogo"):
        assert nome in ctx
    for vazamento in (
        "Fotos da viagem para europa",
        "Boletos e Comprovantes",
        "Downloads, Documentos e Área de Trabalho",
    ):
        assert vazamento not in ctx

    custom_md = tmp_path / "ada_custom.md"
    custom_md.write_text("Ada Customizada", encoding="utf-8")
    monkeypatch.setattr(agent_ada, "AGENT_MD", custom_md)
    assert "Ada Customizada" in agent_ada.carregar_contexto()

    monkeypatch.setattr(agent_ada, "AGENT_MD", tmp_path / "ausente.md")
    assert "Você é um assistente." in agent_ada.carregar_contexto()


def test_ada_markdown_sincronizado_e_regras_preservadas():
    """Confirma tabela `## Ferramentas disponíveis` sincronizada e regras socráticas intactas."""
    md_path = agent_core.RAIZ / "agent-ada.md"
    nomes_md = _extrair_ferramentas_md(md_path)
    assert len(nomes_md) == 4
    assert set(nomes_md) == set(agent_ada.EXECUTORES.keys())

    conteudo = md_path.read_text(encoding="utf-8")
    assert "Nunca dê o código pronto de um exercício" in conteudo
    assert "Se o aluno pedir a resposta direta três vezes seguidas" in conteudo
    assert "Use ferramenta em silêncio, sem narrar." in conteudo
    assert "## Exemplo do tom" in conteudo


def test_ada_executar_ferramenta_despacho_e_bloqueio():
    """Valida despacho JSON estrito das 4 ferramentas e bloqueio de ferramentas alheias."""
    casos = [
        ("somar", {"a": 10, "b": 2.5}, 12.5),
        ("verificar_sintaxe_python", {"codigo": "x = 1 + 2\n"}, None),
        ("analisar_logica_codigo", {"codigo": "for i in range(3):\n    print(i)\n"}, None),
        ("gerar_exemplo_analogo", {"conceito": "while"}, None),
    ]
    for nome, args, esperado_soma in casos:
        bruto = agent_ada.executar_ferramenta(nome, args)
        dados = json.loads(bruto)
        json.dumps(dados, allow_nan=False, ensure_ascii=False)
        assert "erro" not in dados
        if esperado_soma is not None:
            assert dados["resultado"] == esperado_soma

    err_soma = json.loads(agent_ada.executar_ferramenta("somar", {"a": "x", "b": 1}))
    assert "erro" in err_soma

    for proibida in ("listar_arquivos", "analisar_complexidade_codigo", "consultar_base_conhecimento"):
        err = json.loads(agent_ada.executar_ferramenta(proibida, {}))
        assert "erro" in err
        assert "não existe" in err["erro"]


# ==============================================================================
# SEÇÃO B — `verificar_sintaxe_python`
# ==============================================================================


def test_ada_verificar_sintaxe_codigo_valido():
    """Valida retorno limpo e sem menção a syntaxerror em código Python válido."""
    codigo = "def saudar(nome):\n    for i in range(2):\n        pass\n    return f'Oi, {nome}'\n"
    res = agent_ada.verificar_sintaxe_python(codigo)
    assert res["sintaxe_valida"] is True
    assert res["linhas"] == 4
    assert res["instrucoes_topo"] == 1
    assert "erro" not in res
    assert "syntaxerror" not in json.dumps(res, ensure_ascii=False).lower()


@pytest.mark.parametrize(
    ("codigo_quebrado", "tipo_esperado"),
    [
        ("def quebrado(:\n    return 1\n", "SyntaxError"),
        ("if True\n    print('oi')\n", "SyntaxError"),
        ("def ind():\nprint(1)\n", "IndentationError"),
    ],
)
def test_ada_verificar_sintaxe_codigo_invalido(codigo_quebrado, tipo_esperado):
    """Detecta erros de sintaxe e indentação com linha, tipo e pergunta socrática."""
    res = agent_ada.verificar_sintaxe_python(codigo_quebrado)
    assert res["sintaxe_valida"] is False
    assert res["tipo_erro"] == tipo_esperado
    assert isinstance(res["linha"], int) and res["linha"] >= 1
    assert res["detalhe"]
    assert res["pergunta_socratica"]
    json.dumps(res, allow_nan=False, ensure_ascii=False)


@pytest.mark.parametrize("entrada", ["", "   \n\t  ", "a = '\x00'", None, 123])
def test_ada_verificar_sintaxe_entradas_borda_sem_excecao(entrada):
    """Garante retorno estruturado JSON-estrito em vazio, null bytes e não-strings."""
    res = agent_ada.verificar_sintaxe_python(entrada)  # type: ignore[arg-type]
    assert isinstance(res, dict)
    assert res["sintaxe_valida"] is False
    json.dumps(res, allow_nan=False, ensure_ascii=False)


@pytest.mark.parametrize("codigo", ["raise SystemExit(99)", "x = 1 / 0"])
def test_ada_verificar_sintaxe_nao_executa_codigo(codigo):
    """Confirma análise puramente estática sem executar `SystemExit` ou `ZeroDivisionError`."""
    res = agent_ada.verificar_sintaxe_python(codigo)
    assert res["sintaxe_valida"] is True


# ==============================================================================
# SEÇÃO C — `analisar_logica_codigo`
# ==============================================================================


def test_ada_analisar_logica_codigo_estruturado():
    """Extrai métricas estruturais corretas para funções, laços, condicionais e variáveis."""
    codigo = (
        "def contar_positivos(nums):\n"
        "    total = 0\n"
        "    for n in nums:\n"
        "        if n > 0:\n"
        "            total += 1\n"
        "    return total\n"
    )
    res = agent_ada.analisar_logica_codigo(codigo)
    assert res["analisavel"] is True
    assert res["sintaxe_valida"] is True
    resumo = res["resumo_estrutural"]
    assert resumo["lacos_for"] == 1
    assert resumo["lacos_while"] == 0
    assert resumo["condicionais_if"] == 1
    assert "total" in resumo["variaveis"]
    assert "n" in resumo["variaveis"]
    assert len(resumo["funcoes"]) == 1
    assert resumo["funcoes"][0]["possui_return"] is True
    assert len(res["perguntas_guia"]) >= 1


def test_ada_analisar_logica_while_sem_atualizacao_nao_entrega_solucao():
    """Sinaliza laço `while` sem atualização da condição sem entregar código pronto."""
    codigo = "i = 0\nwhile i < 5:\n    print(i)\n"
    res = agent_ada.analisar_logica_codigo(codigo)
    assert res["analisavel"] is True
    assert res["resumo_estrutural"]["lacos_while"] == 1
    assert any("while" in obs.lower() for obs in res["observacoes_logicas"])
    assert len(res["perguntas_guia"]) >= 1
    texto = json.dumps(res, ensure_ascii=False)
    assert "i += 1" not in texto
    assert "i = i + 1" not in texto


def test_ada_analisar_logica_while_true_sem_break_sinaliza_saida_socratica():
    """Sinaliza `while True:` sem `break` como laço sem saída, sem entregar código pronto."""
    codigo = "while True:\n    print(1)\n"
    res = agent_ada.analisar_logica_codigo(codigo)
    assert res["analisavel"] is True
    assert res["resumo_estrutural"]["lacos_while"] == 1
    obs_joined = " ".join(res["observacoes_logicas"]).lower()
    assert "while" in obs_joined
    assert any(
        termo in obs_joined
        for termo in ("break", "parada", "saída", "saida", "infinit", "encerr")
    )
    assert len(res["perguntas_guia"]) >= 1
    texto = json.dumps(res, ensure_ascii=False)
    assert "while True:" not in texto
    assert "i += 1" not in texto
    assert "if " not in texto.lower()

    com_break = "parar = True\nwhile True:\n    if parar:\n        break\n"
    res_break = agent_ada.analisar_logica_codigo(com_break)
    assert res_break["analisavel"] is True
    assert not any("while" in obs.lower() for obs in res_break["observacoes_logicas"])

    com_return = "def f():\n    while True:\n        return 1\n"
    res_ret = agent_ada.analisar_logica_codigo(com_return)
    assert res_ret["analisavel"] is True
    assert not any("while" in obs.lower() for obs in res_ret["observacoes_logicas"])

    while_false = "while False:\n    print(1)\n"
    res_false = agent_ada.analisar_logica_codigo(while_false)
    assert res_false["analisavel"] is True
    assert not any("while" in obs.lower() for obs in res_false["observacoes_logicas"])


def test_ada_analisar_logica_return_em_funcao_aninhada_nao_vaza_para_externa():
    """Garante que `return` e `if` dentro de `inner` não vazam para `outer`."""
    codigo = (
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "    inner()\n"
    )
    res = agent_ada.analisar_logica_codigo(codigo)
    assert res["analisavel"] is True
    por_nome = {f["nome"]: f for f in res["resumo_estrutural"]["funcoes"]}
    assert por_nome["outer"]["possui_return"] is False
    assert por_nome["inner"]["possui_return"] is True
    assert any("outer" in obs and "return" in obs.lower() for obs in res["observacoes_logicas"])
    assert not any("inner" in obs and "return" in obs.lower() for obs in res["observacoes_logicas"])

    codigo_rec = (
        "def rec_outer(n):\n"
        "    def inner_if(x):\n"
        "        if x > 0:\n"
        "            return x\n"
        "        return 0\n"
        "    return rec_outer(n - 1)\n"
    )
    res_rec = agent_ada.analisar_logica_codigo(codigo_rec)
    assert any("rec_outer" in obs and "caso base" in obs.lower() for obs in res_rec["observacoes_logicas"])


def test_ada_analisar_logica_funcao_sem_return_e_recursao_sem_caso_base():
    """Detecta função sem `return` e recursão sem condicional de parada."""
    codigo = "def rec(n):\n    rec(n - 1)\n"
    res = agent_ada.analisar_logica_codigo(codigo)
    assert res["analisavel"] is True
    assert "rec" in res["resumo_estrutural"]["recursao_detectada"]
    obs_joined = " ".join(res["observacoes_logicas"]).lower()
    assert "return" in obs_joined
    assert "caso base" in obs_joined


def test_ada_analisar_logica_nao_entrega_codigo_soma_pares():
    """Assegura conformidade socrática: jamais sugerir solução pronta de exercício."""
    codigo = (
        "def soma_pares(nums):\n"
        "    total = 0\n"
        "    for n in nums:\n"
        "        total += n\n"
        "    return total\n"
    )
    res = agent_ada.analisar_logica_codigo(codigo)
    texto = json.dumps(res, ensure_ascii=False)
    assert "if n % 2 == 0:" not in texto
    assert "return sum(" not in texto


@pytest.mark.parametrize("entrada", ["for i in range(10)\n    print(i)\n", "", "   ", "x='\x00'", None, 42])
def test_ada_analisar_logica_entradas_borda_e_nao_execucao(entrada):
    """Trata erros de sintaxe, vazios e tipos inválidos sem lançar exceções."""
    res = agent_ada.analisar_logica_codigo(entrada)  # type: ignore[arg-type]
    assert isinstance(res, dict)
    assert res["analisavel"] is False
    assert len(res["perguntas_guia"]) >= 1
    json.dumps(res, allow_nan=False, ensure_ascii=False)


def test_ada_analisar_logica_nao_executa_runtime_error():
    """Garante que `analisar_logica_codigo` nunca executa o código analisado."""
    res = agent_ada.analisar_logica_codigo("raise RuntimeError('boom')\n")
    assert res["analisavel"] is True


# ==============================================================================
# SEÇÃO D — `gerar_exemplo_analogo`
# ==============================================================================


@pytest.mark.parametrize(
    ("conceito", "chave_esperada"),
    [
        ("while", "while"),
        ("LOOP", "for"),
        ("for", "for"),
        ("if", "if"),
        ("função", "funcao"),
        ("lista", "lista"),
        ("recursão", "recursao"),
        ("acumulador", "acumulador"),
        ("variável", "variavel"),
    ],
)
def test_ada_gerar_exemplo_analogo_conceitos_e_aliases(conceito, chave_esperada):
    """Mapeia conceitos e variações com acento/caixa para analogias sem código pronto."""
    res = agent_ada.gerar_exemplo_analogo(conceito)
    assert res["reconhecido"] is True
    assert res["conceito"] == chave_esperada
    assert res["dominio_analogo"]
    assert res["analogia"]
    assert res["pergunta_reflexao"]
    assert "erro" not in res
    texto = json.dumps(res, ensure_ascii=False)
    assert "i += 1" not in texto
    assert "i = i + 1" not in texto


@pytest.mark.parametrize("entrada", ["", "   ", "conceito_inexistente_xyz", None])
def test_ada_gerar_exemplo_analogo_fallback_seguro(entrada):
    """Fornece decomposição geral segura para conceitos vazios, desconhecidos ou None."""
    res = agent_ada.gerar_exemplo_analogo(entrada)  # type: ignore[arg-type]
    assert res["reconhecido"] is False
    assert res["conceito"] == "decomposicao_geral"
    assert res["pergunta_reflexao"]
    json.dumps(res, allow_nan=False, ensure_ascii=False)


# ==============================================================================
# SEÇÃO E — Loop ReAct offline de `agent_ada.responder`
# ==============================================================================


def test_ada_responder_multi_turno_envia_apenas_tools_ada(
    mock_openai, criar_resposta_mock, criar_tool_call_mock
):
    """Valida ciclo multi-turno com ferramentas Ada e isolamento estrito do parâmetro `tools`."""
    tc1 = criar_tool_call_mock(
        "c1",
        "verificar_sintaxe_python",
        json.dumps({"codigo": "i = 0\nwhile i < 5:\n    print(i)\n"}),
    )
    tc2 = criar_tool_call_mock(
        "c2",
        "analisar_logica_codigo",
        json.dumps({"codigo": "i = 0\nwhile i < 5:\n    print(i)\n"}),
    )
    tc3 = criar_tool_call_mock(
        "c3",
        "gerar_exemplo_analogo",
        json.dumps({"conceito": "while"}),
    )
    mock_openai.chat.completions.create.side_effect = [
        criar_resposta_mock(tool_calls=[tc1, tc2]),
        criar_resposta_mock(tool_calls=[tc3]),
        criar_resposta_mock(content="O que muda o valor de `i` dentro do laço?"),
    ]
    mensagens = [
        {"role": "system", "content": agent_ada.carregar_contexto()},
        {"role": "user", "content": "Meu while não para."},
    ]

    resposta = agent_ada.responder(mensagens)

    assert "laço" in resposta
    assert mock_openai.chat.completions.create.call_args_list[0].kwargs["tools"] == agent_ada.FERRAMENTAS
    tool_msgs = [m for m in mensagens if m.get("role") == "tool"]
    assert len(tool_msgs) == 3
    for tm in tool_msgs:
        assert "i += 1" not in tm["content"]


def test_ada_responder_tool_use_failed_e_circuit_breaker(
    mock_openai, criar_resposta_mock, monkeypatch
):
    """Valida recuperação de `tool_use_failed` isolada à Ada e teto `MAX_ITERACOES`."""
    mock_openai.chat.completions.create.side_effect = [
        RuntimeError("Error code: 400 - tool_use_failed"),
        criar_resposta_mock(content="O que você esperava que o código fizesse?"),
    ]
    mensagens = [{"role": "user", "content": "Ajuda"}]
    resposta = agent_ada.responder(mensagens)
    assert "esperava" in resposta
    aviso = next(m["content"] for m in mensagens if "Use EXATAMENTE" in m.get("content", ""))
    for permitida in ("somar", "verificar_sintaxe_python", "analisar_logica_codigo", "gerar_exemplo_analogo"):
        assert permitida in aviso
    for alheia in ("listar_arquivos", "analisar_complexidade_codigo", "consultar_base_conhecimento"):
        assert alheia not in aviso

    monkeypatch.setattr(agent, "MAX_ITERACOES", 2)
    tc = criar_resposta_mock(
        tool_calls=[
            type(
                "TC",
                (),
                {
                    "id": "loop_id",
                    "function": type(
                        "Fn",
                        (),
                        {"name": "gerar_exemplo_analogo", "arguments": json.dumps({"conceito": "while"})},
                    )(),
                },
            )()
        ]
    )
    mock_openai.chat.completions.create.side_effect = [tc, tc, tc]
    msgs_cb = [{"role": "user", "content": "Loop infinito"}]
    out = agent_ada.responder(msgs_cb)
    assert out == "Atingi o limite de iterações sem concluir. Tente reformular o pedido."
