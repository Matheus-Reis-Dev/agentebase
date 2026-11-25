"""Testes unitários do núcleo compartilhado (`agent_core`), perfis base/organizador e fachada `agent`."""

import importlib
import json
from unittest.mock import MagicMock

import openpyxl
import pytest

import agent
import agent_base
import agent_core
import agent_organizador


# ==============================================================================
# SEÇÃO A — `somar` e serialização JSON
# ==============================================================================


@pytest.mark.parametrize(
    ("a", "b", "esperado"),
    [
        (2, 3, 5),
        (1.5, 2.25, 3.75),
        (0.1, 0.2, pytest.approx(0.3)),
        (-5, -3, -8),
        (-10, 4, -6),
        (0, 0, 0),
        (0, 5.5, 5.5),
        ("2", "3.5", 5.5),
    ],
)
def test_somar_numeros_validos(a, b, esperado):
    """Valida `somar` com inteiros, floats, negativos, zeros e strings numéricas."""
    res = agent_core.somar(a, b)
    assert set(res.keys()) == {"a", "b", "resultado"}
    assert res["resultado"] == esperado


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("abc", 1),
        (1, None),
        (True, 1),
        ([], 2),
    ],
)
def test_somar_entradas_invalidas_nao_numericas(a, b):
    """Garante rejeição de entradas não numéricas e booleanos com retorno de erro estruturado."""
    res = agent_core.somar(a, b)
    assert isinstance(res, dict)
    assert "erro" in res


def test_somar_via_executar_ferramenta_json_serialization():
    """Valida serialização JSON de `somar` (sucesso e erro) via `executar_ferramenta`."""
    raw = agent_core.executar_ferramenta("somar", {"a": 7, "b": -2}, {"somar": agent_core.somar})
    assert isinstance(raw, str)
    dados = json.loads(raw)
    assert dados == {"a": 7, "b": -2, "resultado": 5}

    raw_err = agent_core.executar_ferramenta(
        "somar", {"a": "nao_numero", "b": 2}, {"somar": agent_core.somar}
    )
    dados_err = json.loads(raw_err)
    assert "erro" in dados_err


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (10**400, 1.0),
        (1e308, 1e308),
        (-1e308, -1e308),
        (float("nan"), 1),
        (False, 1),
    ],
)
def test_somar_overflow_nao_finitos_e_booleano_retorna_erro_json_estrito(a, b):
    """Garante erro estruturado e JSON estrito (`allow_nan=False`) em overflows, NaN e bool."""
    res = agent_core.somar(a, b)
    assert isinstance(res, dict)
    assert "erro" in res
    assert isinstance(res["erro"], str) and res["erro"]
    assert "resultado" not in res

    serializado = json.dumps(res, allow_nan=False, ensure_ascii=False)
    assert json.loads(serializado) == res

    raw_tool = agent_core.executar_ferramenta(
        "somar", {"a": a, "b": b}, {"somar": agent_core.somar}
    )
    dados_tool = json.loads(raw_tool)
    assert "erro" in dados_tool
    json.dumps(dados_tool, allow_nan=False, ensure_ascii=False)


# ==============================================================================
# SEÇÃO B — Engine `agent_core`
# ==============================================================================


def test_core_carregar_contexto_com_e_sem_memory_md(tmp_path):
    """Valida carregamento de contexto com/sem `memory_md`, fallback e `memoria_padrao`."""
    fake_agent = tmp_path / "perfil.md"
    fake_memory = tmp_path / "memoria.md"
    fake_agent.write_text("Identidade de Teste", encoding="utf-8")
    fake_memory.write_text("Memória de Teste", encoding="utf-8")

    ctx_com_mem = agent_core.carregar_contexto(fake_agent, fake_memory)
    assert "Identidade de Teste" in ctx_com_mem
    assert "# Memória" in ctx_com_mem
    assert "Memória de Teste" in ctx_com_mem

    ctx_sem_mem = agent_core.carregar_contexto(fake_agent, memory_md=None)
    assert "Identidade de Teste" in ctx_sem_mem
    assert "Fotos da viagem para europa" not in ctx_sem_mem

    ctx_fallback = agent_core.carregar_contexto(
        tmp_path / "inexistente.md", tmp_path / "sem_mem.md"
    )
    assert "Você é um assistente." in ctx_fallback
    assert "# Memória" in ctx_fallback

    ctx_padrao = agent_core.carregar_contexto(
        fake_agent, memory_md=None, memoria_padrao="Sem histórico."
    )
    assert "Sem histórico." in ctx_padrao


def test_core_executar_ferramenta_desconhecida():
    """Garante erro JSON para ferramenta ausente no mapa de executores."""
    res = agent_core.executar_ferramenta("inexistente", {}, {"somar": agent_core.somar})
    dados = json.loads(res)
    assert "erro" in dados
    assert "não existe" in dados["erro"]


def test_core_executar_ferramenta_captura_excecao():
    """Garante captura de exceção com preservação UTF-8 (`ensure_ascii=False`)."""
    def falha(**kwargs):
        raise RuntimeError("erro simulado com acentuação: ação")

    res = agent_core.executar_ferramenta("falha", {}, {"falha": falha})
    assert "ação" in res
    dados = json.loads(res)
    assert "Falha em 'falha'" in dados["erro"]
    assert "erro simulado" in dados["erro"]


def test_core_executar_loop_react_isolamento_ferramentas(
    criar_resposta_mock, criar_tool_call_mock
):
    """Garante que o loop envia apenas ferramentas do perfil e bloqueia tools de outros perfis."""
    cliente = MagicMock()
    tc = criar_tool_call_mock("call_1", "listar_arquivos", json.dumps({"diretorio": "."}))
    cliente.chat.completions.create.side_effect = [
        criar_resposta_mock(tool_calls=[tc]),
        criar_resposta_mock(content="Usei apenas as ferramentas permitidas."),
    ]
    mensagens = [{"role": "user", "content": "Liste meus arquivos"}]

    resposta = agent_core.executar_loop_react(
        mensagens,
        [agent_core.SOMAR_TOOL_SCHEMA],
        {"somar": agent_core.somar},
        cliente=cliente,
    )

    assert resposta == "Usei apenas as ferramentas permitidas."
    assert cliente.chat.completions.create.call_args_list[0].kwargs["tools"] == [
        agent_core.SOMAR_TOOL_SCHEMA
    ]
    tool_msg = next(m for m in mensagens if m.get("role") == "tool")
    assert json.loads(tool_msg["content"]) == {
        "erro": "Ferramenta 'listar_arquivos' não existe."
    }


def test_core_executar_loop_react_argumentos_json_invalidos(
    criar_resposta_mock, criar_tool_call_mock
):
    """Garante fallback `{}` quando argumentos da tool call chegam com JSON malformado."""
    recebido = []

    def eco(**kwargs):
        recebido.append(kwargs)
        return {"ok": True, "kw": kwargs}

    cliente = MagicMock()
    tc = criar_tool_call_mock("call_bad_json", "eco", "{json_quebrado")
    cliente.chat.completions.create.side_effect = [
        criar_resposta_mock(tool_calls=[tc]),
        criar_resposta_mock(content="OK"),
    ]
    mensagens = [{"role": "user", "content": "Teste JSON inválido"}]

    resposta = agent_core.executar_loop_react(mensagens, [], {"eco": eco}, cliente=cliente)

    assert resposta == "OK"
    assert recebido == [{}]


def test_core_executar_loop_react_recuperacao_tool_use_failed_dinamica(criar_resposta_mock):
    """Valida recuperação dinâmica em `tool_use_failed` listando somente tools do perfil ativo."""
    ferramentas_organizador = (
        "listar_arquivos",
        "mover_arquivo",
        "obter_pastas_padrao",
        "criar_pasta",
        "ler_conteudo_ou_resumo",
    )

    cliente_1 = MagicMock()
    cliente_1.chat.completions.create.side_effect = [
        RuntimeError("Error code: 400 - tool_use_failed"),
        criar_resposta_mock(content="Recuperado"),
    ]
    msgs_1 = [{"role": "user", "content": "Calcule 1+1"}]
    resp_1 = agent_core.executar_loop_react(
        msgs_1, [agent_core.SOMAR_TOOL_SCHEMA], {"somar": agent_core.somar}, cliente=cliente_1
    )
    assert resp_1 == "Recuperado"
    aviso_1 = next(m["content"] for m in msgs_1 if "Use EXATAMENTE" in m.get("content", ""))
    assert "somar" in aviso_1
    for tool_org in ferramentas_organizador:
        assert tool_org not in aviso_1

    cliente_2 = MagicMock()
    cliente_2.chat.completions.create.side_effect = [
        RuntimeError("Tool call validation failed: invalid tool"),
        criar_resposta_mock(content="Recuperado 2"),
    ]
    msgs_2 = [{"role": "user", "content": "Execute alpha"}]
    resp_2 = agent_core.executar_loop_react(
        msgs_2,
        [],
        {"alpha": lambda: {}, "beta": lambda: {}},
        cliente=cliente_2,
    )
    assert resp_2 == "Recuperado 2"
    aviso_2 = next(m["content"] for m in msgs_2 if "Use EXATAMENTE" in m.get("content", ""))
    assert "alpha" in aviso_2 and "beta" in aviso_2
    for tool_org in ferramentas_organizador:
        assert tool_org not in aviso_2


def test_core_executar_loop_react_repropaga_erro_nao_relacionado():
    """Garante que erros não relacionados a `tool_use_failed` são repropagados."""
    cliente = MagicMock()
    cliente.chat.completions.create.side_effect = RuntimeError("Timeout de rede")

    with pytest.raises(RuntimeError, match="Timeout de rede"):
        agent_core.executar_loop_react(
            [{"role": "user", "content": "Oi"}],
            [],
            {},
            cliente=cliente,
        )


def test_core_executar_loop_react_circuit_breaker_max_iteracoes(
    monkeypatch, criar_resposta_mock, criar_tool_call_mock
):
    """Valida parada no teto `MAX_ITERACOES` (via módulo e argumento explícito)."""
    monkeypatch.setattr(agent_core, "MAX_ITERACOES", 3)
    tc = criar_tool_call_mock("call_loop", "somar", json.dumps({"a": 1, "b": 1}))

    cliente = MagicMock()
    cliente.chat.completions.create.return_value = criar_resposta_mock(tool_calls=[tc])
    resposta = agent_core.executar_loop_react(
        [{"role": "user", "content": "Loop"}],
        [agent_core.SOMAR_TOOL_SCHEMA],
        {"somar": agent_core.somar},
        cliente=cliente,
    )
    assert cliente.chat.completions.create.call_count == 3
    assert resposta == "Atingi o limite de iterações sem concluir. Tente reformular o pedido."

    cliente_override = MagicMock()
    cliente_override.chat.completions.create.return_value = criar_resposta_mock(tool_calls=[tc])
    resposta_override = agent_core.executar_loop_react(
        [{"role": "user", "content": "Loop"}],
        [agent_core.SOMAR_TOOL_SCHEMA],
        {"somar": agent_core.somar},
        cliente=cliente_override,
        max_iteracoes=2,
    )
    assert cliente_override.chat.completions.create.call_count == 2
    assert resposta_override == "Atingi o limite de iterações sem concluir. Tente reformular o pedido."


def test_core_obter_modulo_perfil_validos_e_invalido():
    """Valida resolução dinâmica de perfis válidos na M1 e `ValueError` para desconhecido."""
    assert agent_core.obter_modulo_perfil("agent.md") is agent_base
    assert agent_core.obter_modulo_perfil("agent-organizador.md") is agent_organizador
    with pytest.raises(ValueError, match="desconhecido"):
        agent_core.obter_modulo_perfil("perfil-desconhecido.md")


def test_core_get_cliente_sem_chave_lanca_erro(monkeypatch):
    """Garante `RuntimeError` explícito quando `OPENAI_API_KEY` está ausente."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(agent_core, "_cliente", None)
    monkeypatch.setattr(agent, "_cliente", None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        agent_core.get_cliente()


def test_core_get_cliente_respeita_agent_cliente_apos_core_populado(
    monkeypatch, criar_resposta_mock
):
    """Garante precedência de `agent._cliente` mesmo quando `agent_core._cliente` foi populado antes."""
    cliente_obsoleto = MagicMock(name="cliente_core_obsoleto")
    cliente_mock = MagicMock(name="cliente_agent_mock")
    cliente_mock.chat.completions.create.return_value = criar_resposta_mock(content="Mock OK")

    monkeypatch.setattr(agent_core, "_cliente", cliente_obsoleto)
    monkeypatch.setattr(agent, "_cliente", cliente_mock)

    assert agent_core.get_cliente() is cliente_mock
    resposta = agent_base.responder([{"role": "user", "content": "Olá"}])
    assert resposta == "Mock OK"
    assert cliente_mock.chat.completions.create.call_count == 1
    assert cliente_obsoleto.chat.completions.create.call_count == 0


def test_core_get_cliente_ignora_cache_core_quando_agent_cliente_none_sem_chave(monkeypatch):
    """Garante `RuntimeError` se `agent._cliente = None` sem chave, ignorando cache de `agent_core`."""
    monkeypatch.setattr(agent_core, "_cliente", MagicMock(name="cliente_core_obsoleto"))
    monkeypatch.setattr(agent, "_cliente", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        agent_core.get_cliente()


# ==============================================================================
# SEÇÃO C — Perfil `agent_base`
# ==============================================================================


def test_agent_base_isolamento_estrito_ferramentas():
    """Garante que `agent_base` expõe exclusivamente `somar`."""
    assert agent_base.PERFIL_NOME == "agent.md"
    assert [t["function"]["name"] for t in agent_base.FERRAMENTAS] == ["somar"]
    assert set(agent_base.EXECUTORES.keys()) == {"somar"}

    ferramentas_proibidas = {
        "obter_pastas_padrao",
        "listar_arquivos",
        "criar_pasta",
        "mover_arquivo",
        "ler_conteudo_ou_resumo",
    }
    assert set(agent_base.EXECUTORES.keys()).isdisjoint(ferramentas_proibidas)


def test_agent_base_carregar_contexto_sem_vazamento_memory_md(monkeypatch, tmp_path):
    """Garante que `agent_base` lê `agent.md` sem vazar fatos de `memory.md`."""
    ctx = agent_base.carregar_contexto()
    assert "## Identidade" in ctx
    assert "somar" in ctx
    assert "# Memória" in ctx
    assert "Fotos da viagem para europa" not in ctx
    assert "Downloads, Documentos e Área de Trabalho" not in ctx

    custom_md = tmp_path / "base_custom.md"
    custom_md.write_text("Persona Base Customizada", encoding="utf-8")
    monkeypatch.setattr(agent_base, "AGENT_MD", custom_md)
    assert "Persona Base Customizada" in agent_base.carregar_contexto()

    monkeypatch.setattr(agent_base, "AGENT_MD", tmp_path / "ausente.md")
    assert "Você é um assistente." in agent_base.carregar_contexto()


def test_agent_base_executar_ferramenta_somar_e_bloqueio_organizador():
    """Valida execução de `somar` e bloqueio de ferramentas do organizador em `agent_base`."""
    res_ok = json.loads(agent_base.executar_ferramenta("somar", {"a": 4, "b": 6}))
    assert res_ok["resultado"] == 10

    res_block = json.loads(
        agent_base.executar_ferramenta("listar_arquivos", {"diretorio": "."})
    )
    assert "não existe" in res_block["erro"]


def test_agent_base_responder_usa_somente_ferramentas_base(
    mock_openai, criar_resposta_mock, criar_tool_call_mock
):
    """Valida ciclo ReAct de `agent_base.responder` enviando apenas `agent_base.FERRAMENTAS`."""
    tc = criar_tool_call_mock("call_somar", "somar", json.dumps({"a": 2, "b": 3}))
    mock_openai.chat.completions.create.side_effect = [
        criar_resposta_mock(tool_calls=[tc]),
        criar_resposta_mock(content="5"),
    ]
    mensagens = [{"role": "user", "content": "Quanto é 2 + 3?"}]

    resposta = agent_base.responder(mensagens)

    assert resposta == "5"
    assert mock_openai.chat.completions.create.call_args_list[0].kwargs["tools"] == (
        agent_base.FERRAMENTAS
    )
    tool_msg = next(m for m in mensagens if m.get("role") == "tool")
    assert json.loads(tool_msg["content"])["resultado"] == 5


# ==============================================================================
# SEÇÃO D — Perfil `agent_organizador`
# ==============================================================================


def test_agent_organizador_isolamento_estrito_ferramentas():
    """Garante que `agent_organizador` expõe apenas suas 5 ferramentas e não expõe `somar`."""
    esperado = {
        "obter_pastas_padrao",
        "listar_arquivos",
        "criar_pasta",
        "mover_arquivo",
        "ler_conteudo_ou_resumo",
    }
    assert agent_organizador.PERFIL_NOME == "agent-organizador.md"
    nomes_schema = {t["function"]["name"] for t in agent_organizador.FERRAMENTAS}
    assert nomes_schema == esperado
    assert set(agent_organizador.EXECUTORES.keys()) == esperado
    assert "somar" not in nomes_schema
    assert "somar" not in agent_organizador.EXECUTORES


def test_agent_organizador_carregar_contexto_com_memory_md(monkeypatch, tmp_path):
    """Valida leitura real de `agent-organizador.md` + `memory.md` e overrides em `tmp_path`."""
    ctx = agent_organizador.carregar_contexto()
    assert "Org" in ctx
    assert "Hierarquia de Pastas Obrigatória" in ctx
    assert "# Memória" in ctx
    assert "Fotos da viagem para europa" in ctx

    fake_agent = tmp_path / "org.md"
    fake_mem = tmp_path / "mem.md"
    fake_agent.write_text("Org Custom", encoding="utf-8")
    fake_mem.write_text("Mem Custom", encoding="utf-8")
    monkeypatch.setattr(agent_organizador, "AGENT_MD", fake_agent)
    monkeypatch.setattr(agent_organizador, "MEMORY_MD", fake_mem)
    ctx_custom = agent_organizador.carregar_contexto()
    assert "Org Custom" in ctx_custom and "Mem Custom" in ctx_custom

    monkeypatch.setattr(agent_organizador, "AGENT_MD", tmp_path / "ausente.md")
    monkeypatch.setattr(agent_organizador, "MEMORY_MD", tmp_path / "ausente_mem.md")
    assert "Você é um assistente." in agent_organizador.carregar_contexto()


def test_agent_organizador_bloqueia_somar():
    """Garante que `somar` é rejeitada no executor do organizador."""
    dados = json.loads(agent_organizador.executar_ferramenta("somar", {"a": 1, "b": 2}))
    assert "não existe" in dados["erro"]


def test_agent_organizador_responder_envia_somente_5_ferramentas(
    mock_openai, criar_resposta_mock
):
    """Valida que `agent_organizador.responder` envia exatamente as 5 ferramentas sem `somar`."""
    mock_openai.chat.completions.create.return_value = criar_resposta_mock(content="Olá!")

    resposta = agent_organizador.responder([{"role": "user", "content": "Oi"}])

    assert resposta == "Olá!"
    tools = mock_openai.chat.completions.create.call_args.kwargs["tools"]
    assert tools == agent_organizador.FERRAMENTAS
    assert "somar" not in {t["function"]["name"] for t in tools}


def test_agent_organizador_listar_arquivos_limite_zero_e_negativo(tmp_path):
    """Garante que `limite <= 0` retorna lista vazia sem incluir item excedente."""
    (tmp_path / "doc1.txt").write_text("a", encoding="utf-8")
    (tmp_path / "doc2.txt").write_text("b", encoding="utf-8")

    for limite in (0, -1):
        res = agent_organizador.listar_arquivos(str(tmp_path), limite=limite)
        assert res["diretorio"] == str(tmp_path.resolve())
        assert res["total_encontrados"] == 0
        assert res["arquivos"] == []

    res_um = agent_organizador.listar_arquivos(str(tmp_path), limite=1)
    assert res_um["total_encontrados"] == 1
    assert len(res_um["arquivos"]) == 1


@pytest.mark.parametrize("modo_falha", ["sem_abas", "erro_iter_rows"])
def test_agent_organizador_ler_xlsx_fecha_workbook_em_erro(monkeypatch, tmp_path, modo_falha):
    """Garante que `_ler_xlsx` fecha o workbook (`wb.close()`) mesmo quando ocorre exceção."""
    xlsx_falso = tmp_path / "planilha.xlsx"
    xlsx_falso.write_bytes(b"placeholder")

    wb_mock = MagicMock()
    if modo_falha == "sem_abas":
        wb_mock.sheetnames = []
    else:
        wb_mock.sheetnames = ["Aba1"]
        aba_mock = MagicMock()
        aba_mock.iter_rows.side_effect = RuntimeError("erro simulado ao iterar linhas")
        wb_mock.__getitem__.return_value = aba_mock

    monkeypatch.setattr(openpyxl, "load_workbook", lambda *args, **kwargs: wb_mock)

    res = agent_organizador._ler_xlsx(xlsx_falso, 500)
    assert "aviso" in res
    assert "Falha ao ler XLSX" in res["aviso"]
    wb_mock.close.assert_called_once()


def test_agent_organizador_ler_xlsx_corrompido_sem_leak_para_mover(tmp_path):
    """Garante retorno de aviso seguro e liberação de arquivo para `.xlsx` corrompido."""
    xlsx_corrompido = tmp_path / "corrompido.xlsx"
    xlsx_corrompido.write_bytes(b"conteudo-invalido-nao-zip")
    destino = tmp_path / "quarentena"

    res = agent_organizador.ler_conteudo_ou_resumo(str(xlsx_corrompido))
    assert "aviso" in res

    res_mover = agent_organizador.mover_arquivo(str(xlsx_corrompido), str(destino))
    assert res_mover["sucesso"] is True
    assert (destino / "corrompido.xlsx").is_file()


# ==============================================================================
# SEÇÃO E — Retrocompatibilidade da fachada `agent.py`
# ==============================================================================


def test_agent_facade_exports_e_copias_isoladas():
    """Verifica todos os 19 símbolos públicos de `agent` e cópias rasas independentes."""
    simbolos = (
        "RAIZ",
        "AGENT_MD",
        "MEMORY_MD",
        "MODELO",
        "TEMPERATURA",
        "MAX_ITERACOES",
        "_cliente",
        "get_cliente",
        "carregar_contexto",
        "obter_pastas_padrao",
        "listar_arquivos",
        "criar_pasta",
        "mover_arquivo",
        "ler_conteudo_ou_resumo",
        "FERRAMENTAS",
        "EXECUTORES",
        "executar_ferramenta",
        "responder",
        "main",
    )
    for simbolo in simbolos:
        assert hasattr(agent, simbolo), f"Símbolo ausente na fachada agent: {simbolo}"

    assert agent.FERRAMENTAS == agent_organizador.FERRAMENTAS
    assert agent.FERRAMENTAS is not agent_organizador.FERRAMENTAS
    assert agent.EXECUTORES is not agent_organizador.EXECUTORES


def test_agent_facade_monkeypatch_executores_isolado(
    monkeypatch, mock_openai, criar_resposta_mock, criar_tool_call_mock
):
    """Garante que mutar `agent.EXECUTORES` afeta `agent.responder` sem mutar `agent_organizador`."""
    monkeypatch.setitem(agent.EXECUTORES, "obter_pastas_padrao", lambda: {"downloads": "/fake"})
    assert (
        agent_organizador.EXECUTORES["obter_pastas_padrao"]
        is agent_organizador.obter_pastas_padrao
    )

    tc = criar_tool_call_mock("call_pastas", "obter_pastas_padrao", "{}")
    mock_openai.chat.completions.create.side_effect = [
        criar_resposta_mock(tool_calls=[tc]),
        criar_resposta_mock(content="Feito"),
    ]
    mensagens = [{"role": "user", "content": "Pastas?"}]

    resposta = agent.responder(mensagens)

    assert resposta == "Feito"
    tool_msg = next(m for m in mensagens if m.get("role") == "tool")
    assert json.loads(tool_msg["content"]) == {"downloads": "/fake"}


def test_agent_facade_monkeypatch_contexto_isolado(monkeypatch, tmp_path):
    """Garante que `agent.AGENT_MD` e `agent.MEMORY_MD` são resolvidos sem afetar `agent_organizador`."""
    fake_agent = tmp_path / "facade_agent.md"
    fake_mem = tmp_path / "facade_mem.md"
    fake_agent.write_text("Fachada Custom", encoding="utf-8")
    fake_mem.write_text("Memória Fachada", encoding="utf-8")

    monkeypatch.setattr(agent, "AGENT_MD", fake_agent)
    monkeypatch.setattr(agent, "MEMORY_MD", fake_mem)

    ctx_facade = agent.carregar_contexto()
    assert "Fachada Custom" in ctx_facade and "Memória Fachada" in ctx_facade

    ctx_org = agent_organizador.carregar_contexto()
    assert "Hierarquia de Pastas Obrigatória" in ctx_org
    assert "Fachada Custom" not in ctx_org


def test_agent_facade_monkeypatch_max_iteracoes(
    monkeypatch, mock_openai, criar_resposta_mock, criar_tool_call_mock
):
    """Garante que `monkeypatch.setattr(agent, 'MAX_ITERACOES', 2)` limita `agent.responder`."""
    monkeypatch.setattr(agent, "MAX_ITERACOES", 2)
    monkeypatch.setitem(agent.EXECUTORES, "obter_pastas_padrao", lambda: {"ok": True})
    tc = criar_tool_call_mock("call_inf", "obter_pastas_padrao", "{}")
    mock_openai.chat.completions.create.return_value = criar_resposta_mock(tool_calls=[tc])

    resposta = agent.responder([{"role": "user", "content": "Loop infinito"}])

    assert mock_openai.chat.completions.create.call_count == 2
    assert resposta == "Atingi o limite de iterações sem concluir. Tente reformular o pedido."


@pytest.mark.parametrize("valor_perfil", ["", "   "])
def test_agent_facade_agente_perfil_vazio_nao_resolve_para_diretorio(monkeypatch, valor_perfil):
    """Garante que `AGENTE_PERFIL` vazio não resolve `agent.AGENT_MD` para um diretório."""
    try:
        with monkeypatch.context() as m:
            m.setenv("AGENTE_PERFIL", valor_perfil)
            recarregado = importlib.reload(agent)
            assert not recarregado.AGENT_MD.is_dir()
            assert recarregado.AGENT_MD.is_file()
            assert recarregado.AGENT_MD.name == "agent.md"
            ctx = recarregado.carregar_contexto()
            assert isinstance(ctx, str) and "# Memória" in ctx
    finally:
        importlib.reload(agent)
