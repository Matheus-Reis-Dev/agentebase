"""Tier 4 E2E: Cenarios Reais de Aplicacao Ponta a Ponta (>= 5 cenarios).

Simula jornadas completas multi-turno com OpenAI mockado para todos os perfis
e interface Streamlit:
1. Ada: Tutoria socratica em Python sem vazar codigo pronto da solucao
2. Lint: Revisao tecnica veredito-primeiro com complexidade, antipadroes e checklist
3. Val: Atendimento Nimbus Telecom com consulta KB, status > 48h e escalonamento
4. Organizador: Triagem e organizacao completa de pasta sandbox ignorando ocultos/.ini
5. Base: Conversa direta pt-BR sem tools + calculo exato com `somar`
6. Streamlit UI: Sessao completa multi-turno em `app.py` com tool call e reset
"""

from __future__ import annotations

from datetime import datetime
import json
import os

from tests.e2e.conftest import (
    criar_mock_resposta_multiplas_tools,
    criar_mock_resposta_texto,
    criar_mock_resposta_tool_call,
    descobrir_protocolo_sla_estourado,
    importar_modulo,
)


def test_t4_cenario_1_ada_tutoria_socratica_python_sem_vazar_codigo(e2e_cliente_mock):
    """Cenario 1: Ada analisa codigo com loop infinito e conduz o aluno sem dar codigo pronto."""
    mod_ada = importar_modulo("agent_ada")
    codigo_aluno = "i = 0\nwhile i < 5:\n    print(i)\n"

    resp_1 = criar_mock_resposta_multiplas_tools([
        {"id": "ada_1", "nome": "verificar_sintaxe_python", "argumentos": {"codigo": codigo_aluno}},
        {"id": "ada_2", "nome": "analisar_logica_codigo", "argumentos": {"codigo": codigo_aluno}},
    ])
    resp_2 = criar_mock_resposta_tool_call(
        "gerar_exemplo_analogo",
        {"conceito": "while"},
        call_id="ada_3",
    )
    resp_3 = criar_mock_resposta_texto(
        "Boa tentativa! A sintaxe esta valida, mas o que precisa mudar no valor de `i` "
        "a cada volta para a condicao `i < 5` ficar falsa?"
    )
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_1, resp_2, resp_3]

    historico = [
        {"role": "system", "content": mod_ada.carregar_contexto()},
        {"role": "user", "content": f"Meu loop nao para, me da o codigo corrigido:\n{codigo_aluno}"},
    ]
    resposta = mod_ada.responder(historico)

    assert "Ada" in historico[0]["content"]
    assert "?" in resposta
    assert "i += 1" not in resposta and "i = i + 1" not in resposta
    tool_msgs = [m for m in historico if m.get("role") == "tool"]
    assert len(tool_msgs) == 3
    for tm in tool_msgs:
        assert "i += 1" not in tm["content"]


def test_t4_cenario_2_lint_revisao_veredito_primeiro(e2e_cliente_mock):
    """Cenario 2: Lint executa complexidade, antipadroes e checklist e entrega veredito-primeiro."""
    mod_lint = importar_modulo("agent_lint")
    codigo_pr = (
        "def processar(itens=[]):\n"
        "    if itens:\n"
        "        for x in itens:\n"
        "            try:\n"
        "                if x > 0:\n"
        "                    return x\n"
        "            except:\n"
        "                pass\n"
        "    return None\n"
    )

    resp_1 = criar_mock_resposta_multiplas_tools([
        {"id": "lint_1", "nome": "analisar_complexidade_codigo", "argumentos": {"codigo": codigo_pr}},
        {"id": "lint_2", "nome": "detectar_antipadroes_python", "argumentos": {"codigo": codigo_pr}},
    ])
    resp_2 = criar_mock_resposta_tool_call(
        "gerar_checklist_revisao",
        {"tipo_mudanca": "geral"},
        call_id="lint_3",
    )
    resp_3 = criar_mock_resposta_texto(
        "Reprovado: ha dois problemas criticos antes do merge.\n"
        "- Bug (`except:`): captura tudo silenciosamente e esconde falhas reais.\n"
        "- Estado compartilhado (`itens=[]`): lista mutavel padrao vaza estado entre chamadas."
    )
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_1, resp_2, resp_3]

    historico = [
        {"role": "system", "content": mod_lint.carregar_contexto()},
        {"role": "user", "content": f"Revise este PR:\n{codigo_pr}"},
    ]
    resposta = mod_lint.responder(historico)

    assert "Lint" in historico[0]["content"]
    assert resposta.startswith("Reprovado")
    tool_msgs = [m for m in historico if m.get("role") == "tool"]
    assert len(tool_msgs) == 3


def test_t4_cenario_3_val_nimbus_telecom_atendimento_e_escalonamento(e2e_cliente_mock, monkeypatch):
    """Cenario 3: Val consulta KB, verifica chamado > 48h e registra escalonamento."""
    mod_val = importar_modulo("agent_val")

    protocolo_sla = descobrir_protocolo_sla_estourado(mod_val) or "NT-2026-999"
    if not descobrir_protocolo_sla_estourado(mod_val):
        monkeypatch.setitem(
            mod_val.EXECUTORES,
            "verificar_status_chamado",
            lambda protocolo: {
                "encontrado": True,
                "protocolo": protocolo,
                "status": "aberto",
                "horas_em_aberto": 60,
                "requer_escalonamento": True,
            },
        )

    resp_1 = criar_mock_resposta_tool_call(
        "consultar_base_conhecimento",
        {"topico": "sem conexao"},
        call_id="val_1",
    )
    resp_2 = criar_mock_resposta_tool_call(
        "verificar_status_chamado",
        {"protocolo": protocolo_sla},
        call_id="val_2",
    )
    resp_3 = criar_mock_resposta_tool_call(
        "registrar_escalonamento",
        {
            "motivo": "Chamado aberto acima de 48 horas",
            "resumo": "Cliente sem internet fixa ha 60h com luz vermelha no modem",
            "protocolo": protocolo_sla,
        },
        call_id="val_3",
    )
    resp_4 = criar_mock_resposta_texto(
        "Bom dia, sou a Val, da Nimbus Telecom. Entendo que voce esta sem conexao ha mais de 48 horas. "
        "Registrei o escalonamento do seu atendimento para analise prioritaria da equipe tecnica."
    )
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_1, resp_2, resp_3, resp_4]

    historico = [
        {"role": "system", "content": mod_val.carregar_contexto()},
        {"role": "user", "content": f"Estou sem internet ha 60h, protocolo {protocolo_sla}!"},
    ]
    resposta = mod_val.responder(historico)

    assert "Nimbus Telecom" in resposta
    assert "escalonamento" in resposta.lower()
    tool_msgs = [m for m in historico if m.get("role") == "tool"]
    assert len(tool_msgs) == 3
    assert "reembolso" not in resposta.lower()


def test_t4_cenario_4_organizador_triagem_sandbox_completa(e2e_cliente_mock, tmp_path):
    """Cenario 4: Organizador lista sandbox, le nota ambigua, cria pastas e move arquivos reais."""
    mod_org = importar_modulo("agent_organizador")
    inbox = tmp_path / "Downloads_E2E"
    destino_base = tmp_path / "Organizados_E2E"
    inbox.mkdir()

    nota = inbox / "nota_01.txt"
    nota.write_text("Boleto de energia eletrica referente a outubro.", encoding="utf-8")
    foto = inbox / "torre_eiffel.jpg"
    foto.write_bytes(b"img")
    oculto = inbox / ".DS_Store"
    oculto.write_text("meta", encoding="utf-8")
    sistema = inbox / "desktop.ini"
    sistema.write_text("[ViewState]", encoding="utf-8")

    ts_2025 = datetime(2025, 10, 8, 10, 0, 0).timestamp()
    os.utime(nota, (ts_2025, ts_2025))
    os.utime(foto, (ts_2025, ts_2025))

    pasta_boletos = destino_base / "2025" / "Boletos e Comprovantes" / "10" / "08"
    pasta_fotos = destino_base / "2025" / "Fotos da viagem para europa" / "10" / "08"

    resp_1 = criar_mock_resposta_tool_call("listar_arquivos", {"diretorio": str(inbox)}, call_id="org_1")
    resp_2 = criar_mock_resposta_tool_call(
        "ler_conteudo_ou_resumo",
        {"caminho_arquivo": str(nota)},
        call_id="org_2",
    )
    resp_3 = criar_mock_resposta_multiplas_tools([
        {"id": "org_3", "nome": "criar_pasta", "argumentos": {"caminho": str(pasta_boletos)}},
        {"id": "org_4", "nome": "criar_pasta", "argumentos": {"caminho": str(pasta_fotos)}},
        {"id": "org_5", "nome": "mover_arquivo", "argumentos": {"origem": str(nota), "destino": str(pasta_boletos)}},
        {"id": "org_6", "nome": "mover_arquivo", "argumentos": {"origem": str(foto), "destino": str(pasta_fotos)}},
    ])
    resp_4 = criar_mock_resposta_texto("Arquivos organizados em 2025/Boletos e Comprovantes e Fotos.")
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_1, resp_2, resp_3, resp_4]

    historico = [
        {"role": "system", "content": mod_org.carregar_contexto()},
        {"role": "user", "content": f"Organize {inbox} em {destino_base}"},
    ]
    resposta = mod_org.responder(historico)

    assert "organizados" in resposta.lower()
    assert (pasta_boletos / "nota_01.txt").is_file()
    assert (pasta_fotos / "torre_eiffel.jpg").is_file()
    assert not nota.exists() and not foto.exists()
    assert oculto.exists() and sistema.exists()


def test_t4_cenario_5_base_conversa_direta_e_calculo_somar(e2e_cliente_mock):
    """Cenario 5: Agente base responde identidade sem tools e usa `somar` no turno matematico."""
    mod_base = importar_modulo("agent_base")

    resp_t1 = criar_mock_resposta_texto("Sou um assistente direto em portugues do Brasil.")
    resp_t2_tool = criar_mock_resposta_tool_call(
        "somar",
        {"a": 1234.56, "b": 7890.44},
        call_id="base_sum",
    )
    resp_t2_final = criar_mock_resposta_texto("O total exato e 9125.0.")
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_t1, resp_t2_tool, resp_t2_final]

    historico = [
        {"role": "system", "content": mod_base.carregar_contexto()},
        {"role": "user", "content": "Quem e voce?"},
    ]
    r1 = mod_base.responder(historico)
    assert "assistente" in r1.lower()
    assert [m for m in historico if m.get("role") == "tool"] == []

    historico.append({"role": "user", "content": "Quanto e 1234.56 + 7890.44?"})
    r2 = mod_base.responder(historico)
    assert "9125" in r2
    tool_msgs = [m for m in historico if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert json.loads(tool_msgs[0]["content"])["resultado"] == 9125.0


def test_t4_cenario_6_streamlit_sessao_completa_com_reset(e2e_app_factory, e2e_cliente_mock, tmp_path):
    """Cenario 6: Sessao E2E no `app.py` com consulta real de ferramenta, chat e Nova conversa."""
    pasta = tmp_path / "app_e2e"
    pasta.mkdir()
    (pasta / "fatura.pdf").write_text("pdf", encoding="utf-8")

    resp_tool = criar_mock_resposta_tool_call("listar_arquivos", {"diretorio": str(pasta)}, call_id="app_1")
    resp_msg_1 = criar_mock_resposta_texto("Encontrei fatura.pdf.")
    resp_msg_2 = criar_mock_resposta_texto("Conversa reiniciada com sucesso.")
    e2e_cliente_mock.chat.completions.create.side_effect = [resp_tool, resp_msg_1, resp_msg_2]

    at = e2e_app_factory().run()
    at.chat_input[0].set_value(f"Verifique {pasta}").run()
    assert at.session_state["tela"] == [
        ("user", f"Verifique {pasta}"),
        ("assistant", "Encontrei fatura.pdf."),
    ]

    btn_nova = [b for b in at.button if b.label == "Nova conversa"][0]
    btn_nova.click().run()
    assert at.session_state["tela"] == []

    at.chat_input[0].set_value("Oi de novo").run()
    assert at.session_state["tela"] == [
        ("user", "Oi de novo"),
        ("assistant", "Conversa reiniciada com sucesso."),
    ]
    assert len(at.error) == 0
