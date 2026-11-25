"""Tier 2 E2E: Casos de Borda, Limites e Tratamento de Erros (>= 5 por area).

Cobre entradas vazias/malformadas, erros de sintaxe (Ada/Lint), escalonamento
`horas_em_aberto > 48` (Val), ferramenta desconhecida / JSON invalido,
circuit breaker `MAX_ITERACOES`, arquivos ocultos/sistema (Organizador) e
ausencia de `OPENAI_API_KEY` em `app.py`.
"""

from __future__ import annotations

import json

import pytest

from tests.e2e.conftest import (
    PERFIS_ESPERADOS,
    criar_mock_resposta_texto,
    criar_mock_resposta_tool_call,
    descobrir_protocolo_sla_estourado,
    importar_modulo,
)


# ==============================================================================
# B1. CORE ENGINE, somar & CIRCUIT BREAKER (>= 5 testes)
# ==============================================================================


@pytest.mark.parametrize("perfil_invalido", ["", "inexistente.md", "../agent.md", "agent-xyz.md"])
def test_b1_core_obter_modulo_perfil_desconhecido_lanca_value_error(perfil_invalido):
    """B1.1: `agent_core.obter_modulo_perfil` rejeita perfis invalidos com ValueError."""
    agent_core = importar_modulo("agent_core")
    with pytest.raises(ValueError):
        agent_core.obter_modulo_perfil(perfil_invalido)


def test_b1_core_somar_entrada_nao_numerica_falha_limpamente():
    """B1.2: `somar` com entrada nao numerica falha sem crash nao tratado via executor."""
    agent_core = importar_modulo("agent_core")
    mod_base = importar_modulo("agent_base")

    res_json = mod_base.executar_ferramenta("somar", {"a": "nao_numero", "b": 2})
    dados = json.loads(res_json)
    assert isinstance(dados, dict)
    assert "erro" in dados

    try:
        direto = agent_core.somar("abc", 1)
        assert isinstance(direto, dict) and "erro" in direto
    except (TypeError, ValueError):
        pass


@pytest.mark.parametrize("perfil_md,esperado", list(PERFIS_ESPERADOS.items()))
def test_b1_perfis_ferramenta_desconhecida_retorna_json_erro(perfil_md, esperado):
    """B1.3: Todos os perfis retornam JSON com chave `erro` para tool inexistente."""
    modulo_nome, _ = esperado
    mod = importar_modulo(modulo_nome)
    saida = json.loads(mod.executar_ferramenta("ferramenta_que_nao_existe", {}))
    assert isinstance(saida, dict)
    assert "erro" in saida


def test_b1_loop_argumentos_json_malformados_nao_quebram_execucao(e2e_cliente_mock):
    """B1.4: Argumentos JSON corrompidos em `tool_calls` sao tratados sem excecao."""
    mod_base = importar_modulo("agent_base")
    resp_quebrada = criar_mock_resposta_tool_call("somar", "{json_invalido", call_id="call_bad")
    resp_final = criar_mock_resposta_texto("Precisei ajustar os argumentos.")
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_quebrada, resp_final]

    msgs = [{"role": "user", "content": "Some algo"}]
    resposta = mod_base.responder(msgs)

    assert resposta == "Precisei ajustar os argumentos."
    tool_msgs = [m for m in msgs if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert "erro" in json.loads(tool_msgs[0]["content"])


def test_b1_loop_max_iteracoes_circuit_breaker(e2e_cliente_mock, monkeypatch):
    """B1.5: Loop infinito de tools e interrompido exatamente em `MAX_ITERACOES`."""
    import agent

    mod_base = importar_modulo("agent_base")
    monkeypatch.setattr(agent, "MAX_ITERACOES", 3)

    resp_loop = criar_mock_resposta_tool_call("somar", {"a": 1, "b": 1}, call_id="loop_1")
    e2e_cliente_mock.chat.completions.create.return_value = resp_loop

    msgs = [{"role": "user", "content": "Entre em loop"}]
    resposta = mod_base.responder(msgs)

    assert e2e_cliente_mock.chat.completions.create.call_count == 3
    assert resposta == "Atingi o limite de iterações sem concluir. Tente reformular o pedido."


def test_b1_core_carregar_contexto_fallback_sem_arquivos(tmp_path):
    """B1.6: `carregar_contexto` aplica fallback seguro quando arquivos .md nao existem."""
    agent_core = importar_modulo("agent_core")
    ctx = agent_core.carregar_contexto(tmp_path / "missing_a.md", tmp_path / "missing_m.md")
    assert "Você é um assistente." in ctx
    assert "# Memória" in ctx


# ==============================================================================
# B2. ADA BOUNDARY & CORNER CASES (>= 5 testes)
# ==============================================================================


def test_b2_ada_verificar_sintaxe_com_erro_de_sintaxe():
    """B2.1: `verificar_sintaxe_python` reporta erro estruturado para codigo invalido."""
    mod = importar_modulo("agent_ada")
    res = mod.verificar_sintaxe_python("def quebrado(:\n    return 1\n")
    assert isinstance(res, dict)
    texto = json.dumps(res, ensure_ascii=False).lower()
    assert res.get("valida") is False or res.get("sintaxe_valida") is False or "erro" in texto or "linha" in texto


@pytest.mark.parametrize("entrada_vazia", ["", "   \n\t  "])
def test_b2_ada_verificar_sintaxe_entrada_vazia(entrada_vazia):
    """B2.2: `verificar_sintaxe_python` lida com string vazia/espacos sem crash."""
    mod = importar_modulo("agent_ada")
    res = mod.verificar_sintaxe_python(entrada_vazia)
    assert isinstance(res, dict)
    json.dumps(res, ensure_ascii=False)


def test_b2_ada_analisar_logica_com_erro_de_sintaxe():
    """B2.3: `analisar_logica_codigo` nao lanca SyntaxError ao receber codigo quebrado."""
    mod = importar_modulo("agent_ada")
    res = mod.analisar_logica_codigo("for i in range(10)\n    print(i)\n")
    assert isinstance(res, dict)
    assert len(res) > 0


def test_b2_ada_analisar_logica_codigo_vazio():
    """B2.4: `analisar_logica_codigo` trata entrada vazia retornando dict valido."""
    mod = importar_modulo("agent_ada")
    res = mod.analisar_logica_codigo("")
    assert isinstance(res, dict)


@pytest.mark.parametrize("conceito", ["", "conceito_desconhecido_xyz"])
def test_b2_ada_gerar_exemplo_analogo_conceito_vazio_ou_desconhecido(conceito):
    """B2.5: `gerar_exemplo_analogo` oferece fallback seguro para conceitos desconhecidos."""
    mod = importar_modulo("agent_ada")
    res = mod.gerar_exemplo_analogo(conceito)
    assert isinstance(res, dict)
    assert len(res) > 0


# ==============================================================================
# B3. LINT BOUNDARY & CORNER CASES (>= 5 testes)
# ==============================================================================


def test_b3_lint_complexidade_com_erro_de_sintaxe():
    """B3.1: `analisar_complexidade_codigo` trata SyntaxError sem quebrar o agente."""
    mod = importar_modulo("agent_lint")
    res = mod.analisar_complexidade_codigo("if True print('erro')")
    assert isinstance(res, dict)
    assert len(res) > 0


def test_b3_lint_complexidade_entrada_vazia():
    """B3.2: `analisar_complexidade_codigo` lida com string vazia."""
    mod = importar_modulo("agent_lint")
    res = mod.analisar_complexidade_codigo("")
    assert isinstance(res, dict)


def test_b3_lint_antipadroes_com_erro_de_sintaxe_e_vazio():
    """B3.3: `detectar_antipadroes_python` trata codigo vazio ou sintaticamente invalido."""
    mod = importar_modulo("agent_lint")
    res_vazio = mod.detectar_antipadroes_python("")
    res_erro = mod.detectar_antipadroes_python("def x(:\n pass")
    assert isinstance(res_vazio, dict)
    assert isinstance(res_erro, dict)


def test_b3_lint_antipadroes_com_caracteres_especiais_e_unicode():
    """B3.4: `detectar_antipadroes_python` preserva estabilidade com Unicode e escapes."""
    mod = importar_modulo("agent_lint")
    codigo = 'msg = "Olá çãõ \\n \\"teste\\""\ndef f(x=[]):\n    return msg\n'
    res = mod.detectar_antipadroes_python(codigo)
    assert isinstance(res, dict)
    json.dumps(res, ensure_ascii=False)


@pytest.mark.parametrize("tipo", ["", "tipo_inexistente"])
def test_b3_lint_checklist_revisao_tipo_desconhecido(tipo):
    """B3.5: `gerar_checklist_revisao` retorna checklist padrao para tipo vazio/desconhecido."""
    mod = importar_modulo("agent_lint")
    res = mod.gerar_checklist_revisao(tipo)
    assert isinstance(res, dict)
    assert len(res) > 0


# ==============================================================================
# B4. VAL BOUNDARY & CORNER CASES (>= 5 testes)
# ==============================================================================


@pytest.mark.parametrize("topico", ["", "receita de bolo de chocolate", "telefonia movel"])
def test_b4_val_kb_fora_de_escopo_ou_vazio(topico):
    """B4.1: `consultar_base_conhecimento` responde com segurança a topicos vazios ou fora de escopo."""
    mod = importar_modulo("agent_val")
    res = mod.consultar_base_conhecimento(topico)
    assert isinstance(res, dict)
    assert len(res) > 0


@pytest.mark.parametrize("protocolo", ["", "PROTO-INEXISTENTE-9999"])
def test_b4_val_verificar_status_chamado_inexistente_ou_vazio(protocolo):
    """B4.2: `verificar_status_chamado` nao quebra para protocolo vazio ou inexistente."""
    mod = importar_modulo("agent_val")
    res = mod.verificar_status_chamado(protocolo)
    assert isinstance(res, dict)
    assert len(res) > 0


def test_b4_val_escalonamento_horas_em_aberto_maior_48(e2e_cliente_mock, monkeypatch):
    """B4.3: Chamado com `horas_em_aberto > 48` aciona fluxo de escalonamento na Val."""
    mod = importar_modulo("agent_val")

    protocolo_real = descobrir_protocolo_sla_estourado(mod)
    if protocolo_real:
        status_real = mod.verificar_status_chamado(protocolo_real)
        assert status_real.get("horas_em_aberto", 0) > 48

    protocolo_teste = protocolo_real or "NT-48H-SIM"
    if not protocolo_real:
        monkeypatch.setitem(
            mod.EXECUTORES,
            "verificar_status_chamado",
            lambda protocolo: {
                "encontrado": True,
                "protocolo": protocolo,
                "status": "aberto",
                "horas_em_aberto": 72,
                "requer_escalonamento": True,
            },
        )

    resp_1 = criar_mock_resposta_tool_call(
        "verificar_status_chamado",
        {"protocolo": protocolo_teste},
        call_id="call_status",
    )
    resp_2 = criar_mock_resposta_tool_call(
        "registrar_escalonamento",
        {
            "motivo": "Chamado aberto ha mais de 48 horas",
            "resumo": "Cliente sem internet ha 72h",
            "protocolo": protocolo_teste,
        },
        call_id="call_esc",
    )
    resp_3 = criar_mock_resposta_texto("Encaminhei seu chamado para o time especialista por superar 48 horas.")
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_1, resp_2, resp_3]

    msgs = [{"role": "user", "content": f"Meu chamado {protocolo_teste} esta aberto ha 3 dias."}]
    resposta = mod.responder(msgs)

    assert "escalon" in json.dumps(msgs, ensure_ascii=False).lower()
    assert "48 horas" in resposta


def test_b4_val_registrar_escalonamento_campos_vazios():
    """B4.4: `registrar_escalonamento` trata strings vazias sem excecao nao capturada."""
    mod = importar_modulo("agent_val")
    res = mod.registrar_escalonamento(motivo="", resumo="", protocolo="")
    assert isinstance(res, dict)


def test_b4_val_cliente_envia_dados_sensiveis_nao_dispara_tools(e2e_cliente_mock):
    """B4.5: Mensagem com dado sensivel (senha/CVV) e tratada em texto sem tool espúria."""
    mod = importar_modulo("agent_val")
    e2e_cliente_mock.chat.completions.create.return_value = criar_mock_resposta_texto(
        "Por seguranca, nao compartilhe senhas ou CVV neste chat."
    )
    msgs = [
        {"role": "system", "content": mod.carregar_contexto()},
        {"role": "user", "content": "Minha senha e 123456 e meu CVV e 999."},
    ]
    resposta = mod.responder(msgs)
    assert "nao compartilhe" in resposta.lower()
    assert [m for m in msgs if m.get("role") == "tool"] == []


# ==============================================================================
# B5. ORGANIZADOR BOUNDARY & CORNER CASES (>= 5 testes)
# ==============================================================================


@pytest.mark.parametrize("oculto", [".DS_Store", ".env", ".gitignore", "desktop.ini", "DESKTOP.INI"])
def test_b5_org_listar_arquivos_ignora_ocultos_e_ini(tmp_path, oculto):
    """B5.1: `listar_arquivos` ignora arquivos ocultos (.) e .ini case-insensitive."""
    mod = importar_modulo("agent_organizador")
    pasta = tmp_path / "sandbox"
    pasta.mkdir()
    (pasta / "valido.pdf").write_text("ok", encoding="utf-8")
    (pasta / oculto).write_text("sistema", encoding="utf-8")

    res = mod.listar_arquivos(str(pasta))
    nomes = [a["nome"] for a in res["arquivos"]]
    assert nomes == ["valido.pdf"]


def test_b5_org_listar_arquivos_ignora_pastas_ano_e_aplica_teto_8(tmp_path):
    """B5.2: `listar_arquivos` ignora pastas de 4 digitos (ex: 2025) e limita a 8 itens."""
    mod = importar_modulo("agent_organizador")
    pasta = tmp_path / "cheia"
    pasta.mkdir()
    (pasta / "2025").mkdir()
    for idx in range(12):
        (pasta / f"doc_{idx:02d}.txt").write_text("x", encoding="utf-8")

    res = mod.listar_arquivos(str(pasta), limite=50)
    nomes = [a["nome"] for a in res["arquivos"]]
    assert "2025" not in nomes
    assert res["total_encontrados"] == 8


def test_b5_org_listar_arquivos_diretorio_inexistente(tmp_path):
    """B5.3: `listar_arquivos` retorna dict com `erro` para caminho inexistente."""
    mod = importar_modulo("agent_organizador")
    res = mod.listar_arquivos(str(tmp_path / "nao_existe"))
    assert "erro" in res


def test_b5_org_mover_arquivo_origem_inexistente(tmp_path):
    """B5.4: `mover_arquivo` retorna dict com `erro` se origem nao existir."""
    mod = importar_modulo("agent_organizador")
    res = mod.mover_arquivo(str(tmp_path / "fantasma.txt"), str(tmp_path / "destino"))
    assert "erro" in res


def test_b5_org_ler_conteudo_binario_inexistente_e_truncamento(tmp_path):
    """B5.5: `ler_conteudo_ou_resumo` avisa binario, erra em inexistente e trunca texto longo."""
    mod = importar_modulo("agent_organizador")
    binario = tmp_path / "img.png"
    binario.write_bytes(b"\x89PNG")
    longo = tmp_path / "grande.txt"
    longo.write_text("Z" * 1000, encoding="utf-8")

    res_bin = mod.ler_conteudo_ou_resumo(str(binario))
    res_miss = mod.ler_conteudo_ou_resumo(str(tmp_path / "ausente.txt"))
    res_trunc = mod.ler_conteudo_ou_resumo(str(longo), limite_caracteres=120)

    assert "aviso" in res_bin
    assert "erro" in res_miss
    assert len(res_trunc["amostra"]) == 120


# ==============================================================================
# B6. STREAMLIT UI (`app.py`) BOUNDARIES & ERROR HANDLING (>= 5 testes)
# ==============================================================================


def test_b6_ui_sem_openai_api_key_exibe_st_error(monkeypatch, e2e_app_factory):
    """B6.1: `app.py` sem `OPENAI_API_KEY` exibe `st.error` e aborta execucao limpa."""
    import agent

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(agent, "_cliente", None)

    at = e2e_app_factory().run()
    assert len(at.error) > 0
    assert "OPENAI_API_KEY" in at.error[0].value


def test_b6_ui_openai_api_key_vazia_exibe_st_error(monkeypatch, e2e_app_factory):
    """B6.2: `app.py` com `OPENAI_API_KEY=""` exibe `st.error` sem crash."""
    import agent

    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr(agent, "_cliente", None)

    at = e2e_app_factory().run()
    assert len(at.error) > 0
    assert "OPENAI_API_KEY" in at.error[0].value


def test_b6_ui_erro_no_responder_faz_rollback_de_mensagens(monkeypatch, e2e_app_factory, e2e_cliente_mock):
    """B6.3: Excecao durante `responder` descarta historico parcial e mostra `st.error`."""
    e2e_cliente_mock.chat.completions.create.side_effect = RuntimeError("Falha simulada na API")
    at = e2e_app_factory().run()
    tamanho_inicial = len(at.session_state["mensagens"])

    at.chat_input[0].set_value("Vai falhar").run()

    assert len(at.error) > 0
    assert "Falha simulada na API" in at.error[0].value
    assert len(at.session_state["mensagens"]) == tamanho_inicial + 1
    assert [m["role"] for m in at.session_state["mensagens"]] == ["system", "user"]


def test_b6_ui_erro_apos_tool_call_nao_deixa_tool_orfa_no_historico(
    monkeypatch, e2e_app_factory, e2e_cliente_mock
):
    """B6.4: Erro no turno 2 apos tool_call remove a chamada incompleta evitando corrupcao do historico."""
    resp_tool = criar_mock_resposta_tool_call("obter_pastas_padrao", {}, call_id="call_fail")
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_tool, RuntimeError("Timeout turno 2")]

    at = e2e_app_factory().run()
    at.chat_input[0].set_value("Quais minhas pastas?").run()

    assert len(at.error) > 0
    papeis = [m["role"] for m in at.session_state["mensagens"]]
    assert papeis == ["system", "user"]


def test_b6_ui_nova_conversa_sem_mensagens_previas_nao_falha(monkeypatch, e2e_app_factory):
    """B6.5: Clicar em `Nova conversa` antes de qualquer mensagem mantem estado consistente."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-ui-key")
    at = e2e_app_factory().run()
    btn_nova = [b for b in at.button if b.label == "Nova conversa"][0]
    btn_nova.click().run()

    assert not at.exception
    assert len(at.error) == 0
    assert at.session_state["tela"] == []
    assert len(at.session_state["mensagens"]) == 1
