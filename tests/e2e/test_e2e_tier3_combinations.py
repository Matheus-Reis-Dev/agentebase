"""Tier 3 E2E: Combinacoes Entre Funcionalidades (Pairwise Interactions).

Valida interacoes entre modulos e camadas:
- `somar` + ferramenta de dominio em loop ReAct multi-turno (Ada, Lint, Val)
- Recuperacao `tool_use_failed` isolada estritamente por perfil
- Propagacao de mock `agent._cliente` e hiperparametros de `agent` para todos os perfis
- Integracao `app.py` UI + `agent` + `agent_core` + seletor de perfil (quando presente)
- Execucao em lote de multiplas tool calls no mesmo turno
"""

from __future__ import annotations

import json

import pytest

from tests.e2e.conftest import (
    PERFIS_ESPERADOS,
    criar_mock_resposta_multiplas_tools,
    criar_mock_resposta_texto,
    criar_mock_resposta_tool_call,
    importar_modulo,
)


@pytest.mark.parametrize(
    "modulo_nome,domain_tool,domain_args",
    [
        ("agent_ada", "verificar_sintaxe_python", {"codigo": "x = 2 + 3"}),
        ("agent_lint", "analisar_complexidade_codigo", {"codigo": "def f(x):\n    return x\n"}),
        ("agent_val", "consultar_base_conhecimento", {"topico": "plano"}),
    ],
)
def test_c1_somar_combinado_com_tool_de_dominio_no_loop(
    e2e_cliente_mock, modulo_nome, domain_tool, domain_args
):
    """C1: Multi-turno combinando ferramenta de dominio e `somar` no mesmo loop ReAct."""
    mod = importar_modulo(modulo_nome)
    resp_1 = criar_mock_resposta_tool_call(domain_tool, domain_args, call_id="call_dom")
    resp_2 = criar_mock_resposta_tool_call("somar", {"a": 12, "b": 8}, call_id="call_sum")
    resp_3 = criar_mock_resposta_texto("Analise concluida com resultado 20.")
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_1, resp_2, resp_3]

    msgs = [
        {"role": "system", "content": mod.carregar_contexto()},
        {"role": "user", "content": "Analise e some 12 + 8."},
    ]
    resposta = mod.responder(msgs)

    assert resposta == "Analise concluida com resultado 20."
    assert e2e_cliente_mock.chat.completions.create.call_count == 3
    tool_msgs = [m for m in msgs if m.get("role") == "tool"]
    assert len(tool_msgs) == 2
    assert json.loads(tool_msgs[1]["content"])["resultado"] == 20


@pytest.mark.parametrize("perfil_md,esperado", list(PERFIS_ESPERADOS.items()))
def test_c2_tool_use_failed_recuperacao_escopo_por_perfil(e2e_cliente_mock, perfil_md, esperado):
    """C2: Recuperacao de `tool_use_failed` lista somente as ferramentas do perfil ativo."""
    modulo_nome, tools_esperadas = esperado
    mod = importar_modulo(modulo_nome)

    todas_tools = set().union(*(tools for _, tools in PERFIS_ESPERADOS.values()))
    tools_proibidas = todas_tools - tools_esperadas

    resp_ok = criar_mock_resposta_texto("Recuperado com sucesso.")
    e2e_cliente_mock.chat.completions.create.side_effect = [
        RuntimeError("Error code: 400 - tool_use_failed: Tool call validation failed"),
        resp_ok,
    ]

    msgs = [{"role": "user", "content": "Execute uma ferramenta"}]
    resposta = mod.responder(msgs)

    assert resposta == "Recuperado com sucesso."
    assert e2e_cliente_mock.chat.completions.create.call_count == 2

    msgs_usuario = [m["content"] for m in msgs if m.get("role") == "user"]
    msg_recuperacao = msgs_usuario[-1]
    for tool_permitida in tools_esperadas:
        assert tool_permitida in msg_recuperacao, (
            f"Tool permitida '{tool_permitida}' ausente na recuperacao de {modulo_nome}"
        )
    for tool_alheia in tools_proibidas:
        assert tool_alheia not in msg_recuperacao, (
            f"Vazamento de tool alheia '{tool_alheia}' na recuperacao de {modulo_nome}"
        )


@pytest.mark.parametrize("perfil_md,esperado", list(PERFIS_ESPERADOS.items()))
def test_c3_propagacao_agent_cliente_mock_para_todos_perfis(e2e_cliente_mock, perfil_md, esperado):
    """C3: Mock em `agent._cliente` propaga automaticamente para todos os modulos de perfil."""
    modulo_nome, _ = esperado
    mod = importar_modulo(modulo_nome)
    e2e_cliente_mock.chat.completions.create.return_value = criar_mock_resposta_texto(f"Via {modulo_nome}")

    msgs = [{"role": "user", "content": "Teste de propagacao"}]
    resposta = mod.responder(msgs)

    assert resposta == f"Via {modulo_nome}"
    assert e2e_cliente_mock.chat.completions.create.call_count == 1


def test_c4_propagacao_hiperparametros_agent_para_perfis(e2e_cliente_mock, monkeypatch):
    """C4: Alteracoes em `agent.MODELO`, `agent.TEMPERATURA` e `agent.MAX_ITERACOES` propagam para perfis."""
    import agent

    mod_ada = importar_modulo("agent_ada")
    monkeypatch.setattr(agent, "MODELO", "gpt-custom-e2e")
    monkeypatch.setattr(agent, "TEMPERATURA", 0.15)
    monkeypatch.setattr(agent, "MAX_ITERACOES", 2)

    e2e_cliente_mock.chat.completions.create.return_value = criar_mock_resposta_tool_call(
        "somar",
        {"a": 1, "b": 2},
        call_id="call_hp",
    )

    msgs = [{"role": "user", "content": "Loop curto"}]
    resposta = mod_ada.responder(msgs)

    assert e2e_cliente_mock.chat.completions.create.call_count == 2
    assert "limite de iterações" in resposta.lower()
    _, kwargs = e2e_cliente_mock.chat.completions.create.call_args_list[0]
    assert kwargs["model"] == "gpt-custom-e2e"
    assert kwargs["temperature"] == pytest.approx(0.15)


def test_c5_ui_integrada_com_loop_e_tool_call_real_offline(e2e_app_factory, e2e_cliente_mock, tmp_path):
    """C5: `app.py` executa fluxo completo Streamlit -> `agent.responder` -> tool -> resposta."""
    pasta = tmp_path / "ui_sandbox"
    pasta.mkdir()
    (pasta / "item.txt").write_text("texto", encoding="utf-8")

    resp_tool = criar_mock_resposta_tool_call("listar_arquivos", {"diretorio": str(pasta)}, call_id="call_ui")
    resp_final = criar_mock_resposta_texto("Encontrei 1 arquivo na pasta informada.")
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_tool, resp_final]

    at = e2e_app_factory().run()
    at.chat_input[0].set_value(f"Liste {pasta}").run()

    assert len(at.error) == 0
    assert at.session_state["tela"][-1] == ("assistant", "Encontrei 1 arquivo na pasta informada.")
    assert any(m.get("role") == "tool" for m in at.session_state["mensagens"])


def test_c6_ui_seletor_de_perfil_quando_disponivel(e2e_app_factory, e2e_cliente_mock):
    """C6: Seletor de perfil na sidebar (quando presente) alterna contexto sem quebrar o chat."""
    e2e_cliente_mock.chat.completions.create.return_value = criar_mock_resposta_texto("Resposta perfil.")
    at = e2e_app_factory().run()

    seletores = list(at.sidebar.selectbox) + list(at.sidebar.radio)
    if seletores:
        seletor = seletores[0]
        opcoes = list(getattr(seletor, "options", []))
        alvo = next((opt for opt in opcoes if "ada" in str(opt).lower()), None)
        if alvo is not None:
            seletor.set_value(alvo).run()

    at.chat_input[0].set_value("Me ajude com um loop").run()
    assert not at.exception
    assert len(at.error) == 0
    assert at.session_state["tela"][-1] == ("assistant", "Resposta perfil.")


def test_c7_execucao_multiplas_tools_simultaneas_lint(e2e_cliente_mock):
    """C7: Turno unico com multiplas tool calls simultaneas preserva `tool_call_id` pareados."""
    mod_lint = importar_modulo("agent_lint")
    codigo = "def f(x=[]):\n    try:\n        return x[0]\n    except:\n        return 0\n"

    resp_batch = criar_mock_resposta_multiplas_tools([
        {"id": "call_c1", "nome": "analisar_complexidade_codigo", "argumentos": {"codigo": codigo}},
        {"id": "call_c2", "nome": "detectar_antipadroes_python", "argumentos": {"codigo": codigo}},
    ])
    resp_final = criar_mock_resposta_texto("Reprovado: ha bare except e argumento mutavel.")
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_batch, resp_final]

    msgs = [{"role": "user", "content": "Revise este codigo"}]
    resposta = mod_lint.responder(msgs)

    assert "Reprovado" in resposta
    tool_msgs = [m for m in msgs if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["call_c1", "call_c2"]
