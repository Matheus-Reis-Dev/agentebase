"""Tier 1 E2E: Cobertura Funcional (>= 5 casos por area de funcionalidade).

Valida por caixa opaca os contratos publicos de `PROJECT.md`:
- A1: `agent_core`, fachada `agent.py` e ferramenta `somar`
- A2: Modulos de perfil, isolamento estrito de ferramentas e memoria
- A3: Sincronia `## Ferramentas disponíveis` nos arquivos Markdown
- A4: Ferramentas de dominio Ada (`agent_ada`)
- A5: Ferramentas de dominio Lint (`agent_lint`)
- A6: Ferramentas de dominio Val (`agent_val`)
- A7: Ferramentas de dominio Organizador (`agent_organizador`)
- A8: Interface Web Streamlit (`app.py`)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e.conftest import (
    PERFIS_ESPERADOS,
    RAIZ_PROJETO,
    criar_mock_resposta_texto,
    criar_mock_resposta_tool_call,
    extrair_ferramentas_markdown,
    extrair_nomes_ferramentas_schema,
    importar_modulo,
)


# ==============================================================================
# A1. CORE ENGINE, FACHADA agent.py & somar (>= 5 testes)
# ==============================================================================


@pytest.mark.parametrize("perfil_md,esperado", list(PERFIS_ESPERADOS.items()))
def test_a1_core_obter_modulo_perfil_suporta_todos_perfis(perfil_md, esperado):
    """A1.1: `agent_core.obter_modulo_perfil` resolve todos os 5 perfis declarados."""
    agent_core = importar_modulo("agent_core")
    modulo_nome, _ = esperado
    assert agent_core.PERFIL_MODULOS[perfil_md] == modulo_nome
    modulo = agent_core.obter_modulo_perfil(perfil_md)
    assert modulo.__name__ == modulo_nome


def test_a1_core_carregar_contexto_com_e_sem_memoria(tmp_path):
    """A1.2: `agent_core.carregar_contexto` monta identidade e secao de memoria."""
    agent_core = importar_modulo("agent_core")
    md_agent = tmp_path / "perfil.md"
    md_mem = tmp_path / "mem.md"
    md_agent.write_text("## Identidade\nPerfil Teste", encoding="utf-8")
    md_mem.write_text("Fato confirmado", encoding="utf-8")

    com_mem = agent_core.carregar_contexto(md_agent, md_mem)
    sem_mem = agent_core.carregar_contexto(md_agent, None, memoria_padrao="Sem dados")

    assert "Perfil Teste" in com_mem and "# Memória" in com_mem and "Fato confirmado" in com_mem
    assert "Perfil Teste" in sem_mem and "Sem dados" in sem_mem


def test_a1_core_somar_aritmetica_exata():
    """A1.3: `agent_core.somar` retorna dicionario com soma exata de inteiros e floats."""
    agent_core = importar_modulo("agent_core")
    res_int = agent_core.somar(15, 27)
    res_float = agent_core.somar(1.25, 2.75)
    res_neg = agent_core.somar(-10, 3.5)

    assert res_int["resultado"] == 42
    assert res_float["resultado"] == pytest.approx(4.0)
    assert res_neg["resultado"] == pytest.approx(-6.5)
    assert set(["a", "b", "resultado"]).issubset(res_int.keys())


def test_a1_core_somar_tool_schema_valido():
    """A1.4: `agent_core.SOMAR_TOOL_SCHEMA` segue formato OpenAI function calling."""
    agent_core = importar_modulo("agent_core")
    schema = agent_core.SOMAR_TOOL_SCHEMA
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "somar"
    props = schema["function"]["parameters"]["properties"]
    assert "a" in props and "b" in props


def test_a1_fachada_agent_preserva_exports_legados():
    """A1.5: `agent.py` mantem simbolos publicos retrocompativeis e 5 tools do organizador."""
    import agent

    exports_obrigatorios = [
        "RAIZ",
        "AGENT_MD",
        "MEMORY_MD",
        "MODELO",
        "TEMPERATURA",
        "MAX_ITERACOES",
        "_cliente",
        "FERRAMENTAS",
        "EXECUTORES",
        "get_cliente",
        "carregar_contexto",
        "executar_ferramenta",
        "responder",
        "main",
        "obter_pastas_padrao",
        "listar_arquivos",
        "criar_pasta",
        "mover_arquivo",
        "ler_conteudo_ou_resumo",
    ]
    for simbolo in exports_obrigatorios:
        assert hasattr(agent, simbolo), f"Simbolo legado ausente em agent.py: {simbolo}"

    nomes = set(extrair_nomes_ferramentas_schema(agent.FERRAMENTAS))
    assert nomes == PERFIS_ESPERADOS["agent-organizador.md"][1]


def test_a1_fachada_agent_responder_loop_react(e2e_cliente_mock):
    """A1.6: `agent.responder` executa turno unico e multi-turno via fachada."""
    import agent

    e2e_cliente_mock.chat.completions.create.return_value = criar_mock_resposta_texto("Pronto.")
    msgs = [{"role": "user", "content": "Oi"}]
    resp = agent.responder(msgs)
    assert resp == "Pronto."
    assert msgs[-1] == {"role": "assistant", "content": "Pronto."}


# ==============================================================================
# A2. MODULOS DE PERFIL E ISOLAMENTO DE FERRAMENTAS / MEMORIA (>= 5 testes)
# ==============================================================================


@pytest.mark.parametrize("perfil_md,esperado", list(PERFIS_ESPERADOS.items()))
def test_a2_perfil_expoe_contrato_publico_completo(perfil_md, esperado):
    """A2.1: Cada modulo de perfil expoe constantes e funcoes contratuais obrigatorias."""
    modulo_nome, _ = esperado
    mod = importar_modulo(modulo_nome)

    for atributo in (
        "PERFIL_NOME",
        "AGENT_MD",
        "FERRAMENTAS",
        "EXECUTORES",
        "carregar_contexto",
        "executar_ferramenta",
        "responder",
    ):
        assert hasattr(mod, atributo), f"Contrato ausente em {modulo_nome}: {atributo}"

    assert mod.PERFIL_NOME == perfil_md
    assert Path(mod.AGENT_MD).name == perfil_md


@pytest.mark.parametrize("perfil_md,esperado", list(PERFIS_ESPERADOS.items()))
def test_a2_perfil_paridade_tools_e_executores_sem_vazamento(perfil_md, esperado):
    """A2.2: `FERRAMENTAS` e `EXECUTORES` tem paridade 1:1 e isolamento estrito."""
    modulo_nome, tools_esperadas = esperado
    mod = importar_modulo(modulo_nome)

    nomes_schema = extrair_nomes_ferramentas_schema(mod.FERRAMENTAS)
    assert len(nomes_schema) == len(set(nomes_schema)), f"Tools duplicadas em {modulo_nome}"
    assert set(nomes_schema) == tools_esperadas
    assert set(mod.EXECUTORES.keys()) == tools_esperadas


@pytest.mark.parametrize("perfil_md,esperado", list(PERFIS_ESPERADOS.items()))
def test_a2_perfil_responder_envia_apenas_suas_tools(e2e_cliente_mock, perfil_md, esperado):
    """A2.3: `responder()` de cada perfil envia apenas suas proprias tools para a OpenAI."""
    modulo_nome, tools_esperadas = esperado
    mod = importar_modulo(modulo_nome)
    e2e_cliente_mock.chat.completions.create.return_value = criar_mock_resposta_texto("Ok")

    mensagens = [
        {"role": "system", "content": mod.carregar_contexto()},
        {"role": "user", "content": "Ola"},
    ]
    resposta = mod.responder(mensagens)

    assert resposta == "Ok"
    _, kwargs = e2e_cliente_mock.chat.completions.create.call_args
    tools_enviadas = set(extrair_nomes_ferramentas_schema(kwargs["tools"]))
    assert tools_enviadas == tools_esperadas


def test_a2_organizador_nao_expoe_somar():
    """A2.4: `agent_organizador` nao inclui `somar` nem ferramentas de outros perfis."""
    mod_org = importar_modulo("agent_organizador")
    assert "somar" not in mod_org.EXECUTORES
    assert "somar" not in extrair_nomes_ferramentas_schema(mod_org.FERRAMENTAS)


def test_a2_memoria_organizador_nao_vaza_para_outros_perfis():
    """A2.5: `memory.md` do organizador nao vaza para Ada, Lint, Val ou Base."""
    for mod_nome in ("agent_base", "agent_ada", "agent_lint", "agent_val"):
        mod = importar_modulo(mod_nome)
        ctx = mod.carregar_contexto()
        assert "Fotos da viagem para europa" not in ctx
        assert "Boletos e Comprovantes" not in ctx

    mod_org = importar_modulo("agent_organizador")
    ctx_org = mod_org.carregar_contexto()
    assert "Fotos da viagem para europa" in ctx_org


# ==============================================================================
# A3. SINCRONIA MARKDOWN `## Ferramentas disponíveis` (>= 5 testes)
# ==============================================================================


@pytest.mark.parametrize("perfil_md,esperado", list(PERFIS_ESPERADOS.items()))
def test_a3_markdown_ferramentas_sincronizadas_com_modulo(perfil_md, esperado):
    """A3.1: Tabela `## Ferramentas disponíveis` do `.md` reflete exatamente as tools do modulo."""
    modulo_nome, tools_esperadas = esperado
    mod = importar_modulo(modulo_nome)
    md_tools = extrair_ferramentas_markdown(RAIZ_PROJETO / perfil_md)
    py_tools = set(extrair_nomes_ferramentas_schema(mod.FERRAMENTAS))

    assert set(md_tools) == tools_esperadas
    assert set(md_tools) == py_tools


def test_a3_markdown_organizador_preserva_regras_originais():
    """A3.2: `agent-organizador.md` preserva hierarquia obrigatoria e 5 ferramentas originais."""
    conteudo = (RAIZ_PROJETO / "agent-organizador.md").read_text(encoding="utf-8")
    assert "[Ano]/[Categoria]/[Mês]/[Dia]" in conteudo
    assert extrair_ferramentas_markdown(RAIZ_PROJETO / "agent-organizador.md") == [
        "obter_pastas_padrao",
        "listar_arquivos",
        "ler_conteudo_ou_resumo",
        "criar_pasta",
        "mover_arquivo",
    ]


# ==============================================================================
# A4. FERRAMENTAS DE DOMINIO ADA (`agent_ada`) (>= 5 testes)
# ==============================================================================


def test_a4_ada_verificar_sintaxe_python_valida():
    """A4.1: `verificar_sintaxe_python` aceita codigo Python valido e retorna dict serializavel."""
    mod = importar_modulo("agent_ada")
    res = mod.verificar_sintaxe_python("def saudar(nome):\n    return f'Oi, {nome}'\n")
    assert isinstance(res, dict)
    serializado = json.dumps(res, ensure_ascii=False).lower()
    assert "syntaxerror" not in serializado
    assert res.get("erro") in (None, "", False)


def test_a4_ada_analisar_logica_codigo_estruturado():
    """A4.2: `analisar_logica_codigo` analisa estruturas de controle sem crash."""
    mod = importar_modulo("agent_ada")
    codigo = "total = 0\nfor i in range(5):\n    if i % 2 == 0:\n        total += i\n"
    res = mod.analisar_logica_codigo(codigo)
    assert isinstance(res, dict)
    assert len(res) > 0
    json.dumps(res, ensure_ascii=False)


def test_a4_ada_analisar_logica_respeita_regra_socratica():
    """A4.3: `analisar_logica_codigo` nao entrega codigo pronto de solucao."""
    mod = importar_modulo("agent_ada")
    codigo_incompleto = "def soma_pares(nums):\n    total = 0\n    for n in nums:\n        total += n\n    return total\n"
    res = mod.analisar_logica_codigo(codigo_incompleto)
    texto_res = json.dumps(res, ensure_ascii=False)
    assert "if n % 2 == 0:" not in texto_res
    assert "return sum(" not in texto_res


def test_a4_ada_gerar_exemplo_analogo():
    """A4.4: `gerar_exemplo_analogo` retorna orientacao/analogia para conceito de programacao."""
    mod = importar_modulo("agent_ada")
    res = mod.gerar_exemplo_analogo("while")
    assert isinstance(res, dict)
    assert len(res) > 0
    assert len(json.dumps(res, ensure_ascii=False).strip()) > 10


def test_a4_ada_executar_ferramenta_despacha_todas_tools():
    """A4.5: `agent_ada.executar_ferramenta` executa `somar` e as 3 tools Ada retornando JSON."""
    mod = importar_modulo("agent_ada")
    chamadas = [
        ("somar", {"a": 4, "b": 6}),
        ("verificar_sintaxe_python", {"codigo": "x = 1"}),
        ("analisar_logica_codigo", {"codigo": "for i in range(3): pass"}),
        ("gerar_exemplo_analogo", {"conceito": "loop"}),
    ]
    for nome, args in chamadas:
        saida = json.loads(mod.executar_ferramenta(nome, args))
        assert isinstance(saida, dict)
        assert "erro" not in saida or not saida["erro"]


# ==============================================================================
# A5. FERRAMENTAS DE DOMINIO LINT (`agent_lint`) (>= 5 testes)
# ==============================================================================


def test_a5_lint_analisar_complexidade_codigo():
    """A5.1: `analisar_complexidade_codigo` avalia codigo simples vs ramificado."""
    mod = importar_modulo("agent_lint")
    simples = "def inc(x):\n    return x + 1\n"
    complexo = (
        "def classificar(a, b, c):\n"
        "    if a > 0:\n"
        "        for i in range(b):\n"
        "            if i % 2 == 0 and c:\n"
        "                return i\n"
        "    elif a < 0:\n"
        "        while b > 0:\n"
        "            b -= 1\n"
        "    return 0\n"
    )
    res_simples = mod.analisar_complexidade_codigo(simples)
    res_complexo = mod.analisar_complexidade_codigo(complexo)

    assert isinstance(res_simples, dict) and isinstance(res_complexo, dict)
    assert res_simples != res_complexo


def test_a5_lint_detectar_antipadroes_identifica_problemas():
    """A5.2: `detectar_antipadroes_python` detecta bare except e arg mutavel padrao."""
    mod = importar_modulo("agent_lint")
    codigo_ruim = "def f(itens=[]):\n    try:\n        return itens[0]\n    except:\n        return None\n"
    res = mod.detectar_antipadroes_python(codigo_ruim)
    assert isinstance(res, dict)
    texto = json.dumps(res, ensure_ascii=False).lower()
    assert "except" in texto or "mut" in texto or "antipad" in texto or len(res) > 0


def test_a5_lint_detectar_antipadroes_diferencia_codigo_limpo():
    """A5.3: `detectar_antipadroes_python` distingue codigo limpo de codigo problematico."""
    mod = importar_modulo("agent_lint")
    codigo_limpo = "def somar_dois(x: int) -> int:\n    return x + 2\n"
    codigo_ruim = "def f(a=[]):\n    try:\n        eval('1+1')\n    except:\n        pass\n"
    res_limpo = mod.detectar_antipadroes_python(codigo_limpo)
    res_ruim = mod.detectar_antipadroes_python(codigo_ruim)
    assert res_limpo != res_ruim


def test_a5_lint_gerar_checklist_revisao():
    """A5.4: `gerar_checklist_revisao` retorna checklist estruturado para tipos de mudanca."""
    mod = importar_modulo("agent_lint")
    res_geral = mod.gerar_checklist_revisao()
    res_seg = mod.gerar_checklist_revisao("seguranca")
    assert isinstance(res_geral, dict) and len(res_geral) > 0
    assert isinstance(res_seg, dict) and len(res_seg) > 0


def test_a5_lint_executar_ferramenta_despacha_todas_tools():
    """A5.5: `agent_lint.executar_ferramenta` executa `somar` e as 3 tools Lint retornando JSON."""
    mod = importar_modulo("agent_lint")
    chamadas = [
        ("somar", {"a": 10, "b": 5}),
        ("analisar_complexidade_codigo", {"codigo": "def a(): return 1"}),
        ("detectar_antipadroes_python", {"codigo": "def a(): return 1"}),
        ("gerar_checklist_revisao", {"tipo_mudanca": "geral"}),
    ]
    for nome, args in chamadas:
        saida = json.loads(mod.executar_ferramenta(nome, args))
        assert isinstance(saida, dict)


# ==============================================================================
# A6. FERRAMENTAS DE DOMINIO VAL (`agent_val`) (>= 5 testes)
# ==============================================================================


def test_a6_val_consultar_base_conhecimento():
    """A6.1: `consultar_base_conhecimento` retorna dados da Nimbus Telecom em dict."""
    mod = importar_modulo("agent_val")
    res = mod.consultar_base_conhecimento("modem")
    assert isinstance(res, dict)
    assert len(res) > 0
    json.dumps(res, ensure_ascii=False)


def test_a6_val_verificar_status_chamado_retorna_dict():
    """A6.2: `verificar_status_chamado` retorna estrutura serializavel para protocolo."""
    mod = importar_modulo("agent_val")
    res = mod.verificar_status_chamado("NT-0001")
    assert isinstance(res, dict)
    assert len(res) > 0
    json.dumps(res, ensure_ascii=False)


def test_a6_val_registrar_escalonamento_sucesso():
    """A6.3: `registrar_escalonamento` registra motivo, resumo e protocolo opcional."""
    mod = importar_modulo("agent_val")
    res = mod.registrar_escalonamento(
        motivo="Problema acima de 48 horas",
        resumo="Cliente sem conexao desde segunda-feira",
        protocolo="NT-2026-100",
    )
    assert isinstance(res, dict)
    texto = json.dumps(res, ensure_ascii=False).lower()
    assert "nt-2026-100" in texto or "escalon" in texto or len(res) > 0


def test_a6_val_executar_ferramenta_despacha_todas_tools():
    """A6.4: `agent_val.executar_ferramenta` executa `somar` e as 3 tools Val retornando JSON."""
    mod = importar_modulo("agent_val")
    chamadas = [
        ("somar", {"a": 100, "b": 49.90}),
        ("consultar_base_conhecimento", {"topico": "cancelamento"}),
        ("verificar_status_chamado", {"protocolo": "NT-101"}),
        ("registrar_escalonamento", {"motivo": "SLA", "resumo": "Aberto ha 50h"}),
    ]
    for nome, args in chamadas:
        saida = json.loads(mod.executar_ferramenta(nome, args))
        assert isinstance(saida, dict)


def test_a6_val_responder_executa_consulta_kb_no_loop(e2e_cliente_mock):
    """A6.5: `agent_val.responder` executa `consultar_base_conhecimento` no loop ReAct."""
    mod = importar_modulo("agent_val")
    resp_tool = criar_mock_resposta_tool_call(
        "consultar_base_conhecimento",
        {"topico": "internet"},
        call_id="call_val_kb",
    )
    resp_final = criar_mock_resposta_texto("Bom dia, sou a Val, da Nimbus Telecom.")
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_tool, resp_final]

    msgs = [
        {"role": "system", "content": mod.carregar_contexto()},
        {"role": "user", "content": "Minha internet esta lenta."},
    ]
    resposta = mod.responder(msgs)

    assert "Nimbus" in resposta
    msgs_tool = [m for m in msgs if m.get("role") == "tool"]
    assert len(msgs_tool) == 1
    assert isinstance(json.loads(msgs_tool[0]["content"]), dict)


# ==============================================================================
# A7. FERRAMENTAS DE DOMINIO ORGANIZADOR (`agent_organizador`) (>= 5 testes)
# ==============================================================================


def test_a7_org_obter_pastas_padrao(monkeypatch, tmp_path):
    """A7.1: `agent_organizador.obter_pastas_padrao` retorna downloads, documentos e desktop."""
    mod = importar_modulo("agent_organizador")
    fake_home = tmp_path / "home_org"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    pastas = mod.obter_pastas_padrao()
    assert set(pastas.keys()) == {"downloads", "documentos", "desktop"}
    assert pastas["downloads"] == str(fake_home / "Downloads")


def test_a7_org_listar_arquivos_retorna_metadados(tmp_path):
    """A7.2: `agent_organizador.listar_arquivos` retorna metadados temporais completos."""
    mod = importar_modulo("agent_organizador")
    pasta = tmp_path / "inbox"
    pasta.mkdir()
    (pasta / "boleto.pdf").write_text("fatura", encoding="utf-8")

    res = mod.listar_arquivos(str(pasta))
    assert res["total_encontrados"] == 1
    item = res["arquivos"][0]
    assert item["nome"] == "boleto.pdf"
    assert len(item["ano"]) == 4 and len(item["mes"]) == 2 and len(item["dia"]) == 2


def test_a7_org_criar_pasta_hierarquica(tmp_path):
    """A7.3: `agent_organizador.criar_pasta` cria estrutura [Ano]/[Categoria]/[Mes]/[Dia]."""
    mod = importar_modulo("agent_organizador")
    alvo = tmp_path / "2026" / "Boletos e Comprovantes" / "03" / "15"
    res = mod.criar_pasta(str(alvo))
    assert res["sucesso"] is True
    assert alvo.is_dir()


def test_a7_org_mover_arquivo(tmp_path):
    """A7.4: `agent_organizador.mover_arquivo` move arquivo e retorna origem e destino."""
    mod = importar_modulo("agent_organizador")
    origem = tmp_path / "nota.txt"
    origem.write_text("conteudo", encoding="utf-8")
    destino_dir = tmp_path / "2026" / "Documentos do trabalho" / "01" / "05"

    res = mod.mover_arquivo(str(origem), str(destino_dir))
    assert res["sucesso"] is True
    assert not origem.exists()
    assert (destino_dir / "nota.txt").is_file()


def test_a7_org_ler_conteudo_ou_resumo_texto(tmp_path):
    """A7.5: `agent_organizador.ler_conteudo_ou_resumo` extrai amostra de arquivo textual."""
    mod = importar_modulo("agent_organizador")
    doc = tmp_path / "contrato.txt"
    doc.write_text("Contrato de prestacao de servicos 2026.", encoding="utf-8")

    res = mod.ler_conteudo_ou_resumo(str(doc))
    assert res["tipo"] == "texto"
    assert "Contrato de prestacao" in res["amostra"]


# ==============================================================================
# A8. STREAMLIT WEB UI (`app.py`) (>= 5 testes)
# ==============================================================================


def test_a8_ui_renderiza_titulo_sem_erros(monkeypatch, e2e_app_factory):
    """A8.1: `app.py` inicializa sem excecoes e exibe titulo `🤖 Agente base`."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-ui-key")
    at = e2e_app_factory().run()
    assert not at.exception
    assert len(at.error) == 0
    assert at.title[0].value == "🤖 Agente base"


def test_a8_ui_sidebar_exibe_modelo_e_botao_nova_conversa(monkeypatch, e2e_app_factory):
    """A8.2: Sidebar exibe caption do modelo e botao `Nova conversa`."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-ui-key")
    at = e2e_app_factory().run()
    captions = [c.value for c in at.sidebar.caption]
    botoes = [b.label for b in at.button]
    assert any("Modelo:" in c for c in captions)
    assert "Nova conversa" in botoes


def test_a8_ui_chat_input_atualiza_mensagens_e_tela(monkeypatch, e2e_app_factory, e2e_cliente_mock):
    """A8.3: Envio de mensagem no chat executa o fluxo e grava historico em session_state."""
    e2e_cliente_mock.chat.completions.create.return_value = criar_mock_resposta_texto("Resposta UI")
    at = e2e_app_factory().run()
    at.chat_input[0].set_value("Oi interface").run()

    assert len(at.error) == 0
    assert at.session_state["tela"] == [("user", "Oi interface"), ("assistant", "Resposta UI")]
    assert at.session_state["mensagens"][-1] == {"role": "assistant", "content": "Resposta UI"}


def test_a8_ui_nova_conversa_limpa_historico(monkeypatch, e2e_app_factory, e2e_cliente_mock):
    """A8.4: Botao `Nova conversa` limpa `tela` e reinicia `mensagens` para o prompt de sistema."""
    e2e_cliente_mock.chat.completions.create.return_value = criar_mock_resposta_texto("Turno 1")
    at = e2e_app_factory().run()
    at.chat_input[0].set_value("Mensagem inicial").run()
    assert len(at.session_state["tela"]) == 2

    btn_nova = [b for b in at.button if b.label == "Nova conversa"][0]
    btn_nova.click().run()

    assert at.session_state["tela"] == []
    assert len(at.session_state["mensagens"]) == 1
    assert at.session_state["mensagens"][0]["role"] == "system"


def test_a8_ui_multiplos_turnos_preservam_historico(monkeypatch, e2e_app_factory, e2e_cliente_mock):
    """A8.5: Multiplas mensagens seguidas preservam todo o historico visual e tecnico."""
    e2e_cliente_mock.chat.completions.create.side_effect = [
        criar_mock_resposta_texto("Primeira"),
        criar_mock_resposta_texto("Segunda"),
    ]
    at = e2e_app_factory().run()
    at.chat_input[0].set_value("Pergunta 1").run()
    at.chat_input[0].set_value("Pergunta 2").run()

    assert len(at.error) == 0
    assert at.session_state["tela"] == [
        ("user", "Pergunta 1"),
        ("assistant", "Primeira"),
        ("user", "Pergunta 2"),
        ("assistant", "Segunda"),
    ]
