"""Testes unitários do perfil Val (`agent_val`) e suas ferramentas Nimbus Telecom."""

import json
import re
from pathlib import Path

import pytest

import agent_core
import agent_val


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
# SEÇÃO A — Contrato de perfil e isolamento estrito de ferramentas/memória
# ==============================================================================


def test_agent_val_isolamento_estrito_ferramentas():
    """Garante exposição exclusiva de `somar` e das 3 ferramentas Val com paridade 1:1."""
    esperado = {
        "somar",
        "consultar_base_conhecimento",
        "verificar_status_chamado",
        "registrar_escalonamento",
    }
    assert agent_val.PERFIL_NOME == "agent-val.md"
    assert agent_val.AGENT_MD.name == "agent-val.md"
    nomes_schema = [t["function"]["name"] for t in agent_val.FERRAMENTAS]
    assert len(nomes_schema) == 4
    assert set(nomes_schema) == esperado
    assert set(agent_val.EXECUTORES.keys()) == esperado
    assert agent_core.obter_modulo_perfil("agent-val.md") is agent_val

    proibidas = {
        "obter_pastas_padrao",
        "listar_arquivos",
        "criar_pasta",
        "mover_arquivo",
        "ler_conteudo_ou_resumo",
        "verificar_sintaxe_python",
        "analisar_logica_codigo",
        "gerar_exemplo_analogo",
        "analisar_complexidade_codigo",
        "detectar_antipadroes_python",
        "gerar_checklist_revisao",
    }
    assert set(agent_val.EXECUTORES.keys()).isdisjoint(proibidas)


def test_agent_val_carregar_contexto_sem_vazamento_memory_md(monkeypatch, tmp_path):
    """Garante carregamento de `agent-val.md` com memória neutra e sem vazar `memory.md`."""
    ctx = agent_val.carregar_contexto()
    assert "Nimbus Telecom" in ctx
    assert "Val" in ctx
    assert "# Memória" in ctx
    assert agent_val.MEMORIA_PADRAO in ctx
    assert "Fotos da viagem para europa" not in ctx
    assert "Boletos e Comprovantes" not in ctx

    md_path = agent_core.RAIZ / "agent-val.md"
    assert set(_extrair_ferramentas_md(md_path)) == set(agent_val.EXECUTORES.keys())
    conteudo_md = md_path.read_text(encoding="utf-8")
    assert "Nimbus Telecom é uma empresa fictícia" in conteudo_md
    assert "Nunca prometa prazo, desconto, isenção ou reembolso." in conteudo_md
    assert "## Exemplo do tom" in conteudo_md

    custom_md = tmp_path / "val_custom.md"
    custom_md.write_text("Val Customizada", encoding="utf-8")
    monkeypatch.setattr(agent_val, "AGENT_MD", custom_md)
    assert "Val Customizada" in agent_val.carregar_contexto()

    monkeypatch.setattr(agent_val, "AGENT_MD", tmp_path / "ausente.md")
    assert "Você é um assistente." in agent_val.carregar_contexto()


def test_agent_val_executar_ferramenta_somar_e_bloqueio_alheias():
    """Valida execução de `somar` e bloqueio de ferramentas de outros perfis."""
    res_somar = json.loads(agent_val.executar_ferramenta("somar", {"a": 99.9, "b": 30.0}))
    assert res_somar["resultado"] == pytest.approx(129.9)

    for nome_proibido in ("listar_arquivos", "verificar_sintaxe_python", "analisar_complexidade_codigo"):
        res_err = json.loads(agent_val.executar_ferramenta(nome_proibido, {}))
        assert "erro" in res_err
        assert "não existe" in res_err["erro"]


# ==============================================================================
# SEÇÃO B — Base de conhecimento (`consultar_base_conhecimento`)
# ==============================================================================


@pytest.mark.parametrize(
    "topico",
    [
        "planos",
        "precos",
        "sla",
        "prazos",
        "cobertura",
        "cancelamento",
        "suporte_modem",
        "fatura",
        "escalonamento",
    ],
)
def test_kb_cobre_todos_topicos_canonicos(topico):
    """Garante hit determinístico para todos os 9 tópicos canônicos da Nimbus Telecom."""
    res = agent_val.consultar_base_conhecimento(topico)
    assert res["encontrado"] is True
    assert res["topico"] == topico
    assert res["titulo"]
    assert res["resumo"]
    assert isinstance(res["detalhes"], list) and len(res["detalhes"]) > 0
    json.dumps(res, allow_nan=False, ensure_ascii=False)


@pytest.mark.parametrize(
    ("consulta", "topico_esperado"),
    [
        ("plano", "planos"),
        ("internet", "planos"),
        ("preços", "precos"),
        ("modem", "suporte_modem"),
        ("sem conexão", "suporte_modem"),
        ("boleto", "fatura"),
        ("48 horas", "sla"),
    ],
)
def test_kb_resolve_aliases_e_normalizacao_acentos(consulta, topico_esperado):
    """Garante normalização de acentos e mapeamento determinístico de sinônimos."""
    res = agent_val.consultar_base_conhecimento(consulta)
    assert res["encontrado"] is True
    assert res["topico"] == topico_esperado


@pytest.mark.parametrize(
    "consulta_invalida",
    ["", "   ", "telefonia movel", "receita de bolo de chocolate", "topico_desconhecido_xyz", None],
)
def test_kb_trata_topico_desconhecido_ou_fora_de_escopo(consulta_invalida):
    """Garante retorno seguro (`encontrado=False`) sem improvisação para fora de escopo."""
    res = agent_val.consultar_base_conhecimento(consulta_invalida)  # type: ignore[arg-type]
    assert res["encontrado"] is False
    assert res["topico"] is None
    assert set(agent_val.BASE_CONHECIMENTO.keys()).issubset(set(res["topicos_disponiveis"]))


def test_kb_nao_solicita_nem_ecoa_dados_sensiveis():
    """Garante conformidade com a Regra 4 na base de conhecimento e no eco de consulta."""
    texto_kb = json.dumps(agent_val.BASE_CONHECIMENTO, ensure_ascii=False).lower()
    for termo_proibido in ("informe sua senha", "envie seu cvv", "envie foto de documento"):
        assert termo_proibido not in texto_kb

    res = agent_val.consultar_base_conhecimento("Minha senha é 998877")
    serializado = json.dumps(res, ensure_ascii=False)
    assert "998877" not in serializado
    assert res["dado_sensivel_removido"] is True


# ==============================================================================
# SEÇÃO C — Consulta de chamados (`verificar_status_chamado`)
# ==============================================================================


@pytest.mark.parametrize("protocolo", ["NT-0001", "nt-0001", "NT-101"])
def test_verificar_status_chamado_dentro_janela_48h(protocolo):
    """Valida chamados em aberto até 48h sem exigir escalonamento por SLA."""
    res = agent_val.verificar_status_chamado(protocolo)
    assert res["encontrado"] is True
    assert res["horas_em_aberto"] <= 48
    assert res["requer_escalonamento"] is False
    assert res["motivo_escalonamento_sugerido"] is None


def test_verificar_status_chamado_limite_exato_48h_nao_estoura():
    """Valida fronteira exata `horas_em_aberto == 48` (escalonamento só ocorre em `> 48`)."""
    res = agent_val.verificar_status_chamado("NT-2026-048")
    assert res["encontrado"] is True
    assert res["horas_em_aberto"] == 48
    assert res["requer_escalonamento"] is False


@pytest.mark.parametrize("protocolo", ["NT-2026-100", "NT-2026-205"])
def test_verificar_status_chamado_acima_48h_sinaliza_escalonamento(protocolo):
    """Valida que `horas_em_aberto > 48` retorna `requer_escalonamento=True` conforme Regra 3."""
    res = agent_val.verificar_status_chamado(protocolo)
    assert res["encontrado"] is True
    assert res["horas_em_aberto"] > 48
    assert res["requer_escalonamento"] is True
    assert res["motivo_escalonamento_sugerido"] == "acima_48h"


def test_verificar_status_chamado_concluido_nao_requer_escalonamento():
    """Garante que chamado concluído não marca escalonamento pendente."""
    res = agent_val.verificar_status_chamado("NT-2026-300")
    assert res["encontrado"] is True
    assert res["status"] == "concluido"
    assert res["requer_escalonamento"] is False


@pytest.mark.parametrize("protocolo", ["", "   ", "NT-9999", "PROTO-INEXISTENTE-9999", None])
def test_verificar_status_chamado_inexistente_ou_invalido(protocolo):
    """Garante tratamento seguro de protocolos vazios, inválidos ou desconhecidos."""
    res = agent_val.verificar_status_chamado(protocolo)  # type: ignore[arg-type]
    assert res["encontrado"] is False
    assert res["horas_em_aberto"] == 0
    assert res["requer_escalonamento"] is False
    json.dumps(res, allow_nan=False, ensure_ascii=False)


# ==============================================================================
# SEÇÃO D — Escalonamento (`registrar_escalonamento`)
# ==============================================================================


@pytest.mark.parametrize(
    "motivo",
    ["cancelamento", "cobranca_contestada", "acima_48h", "excecao_politica"],
)
def test_registrar_escalonamento_motivos_canonicos(motivo):
    """Valida registro estruturado para todos os 4 motivos obrigatórios sem promessas."""
    res = agent_val.registrar_escalonamento(
        motivo=motivo,
        resumo="Solicitação validada com o cliente no chat.",
        protocolo="NT-2026-100",
    )
    assert res["registrado"] is True
    assert res["status"] == "escalonado"
    assert res["motivo"] == motivo
    assert res["protocolo"] == "NT-2026-100"
    assert res["id_escalonamento"].startswith("ESC-")
    assert res["promessa_sla_ou_desconto"] is False
    assert res["area_destino"]


@pytest.mark.parametrize(
    ("motivo_livre", "esperado"),
    [
        ("Problema acima de 48 horas", "acima_48h"),
        ("SLA", "acima_48h"),
        ("Cancelar assinatura", "cancelamento"),
        ("Contestação de fatura", "cobranca_contestada"),
        ("Pedido de exceção à regra", "excecao_politica"),
    ],
)
def test_registrar_escalonamento_normaliza_aliases(motivo_livre, esperado):
    """Garante aceitação de descrições equivalentes mapeadas aos 4 códigos oficiais."""
    res = agent_val.registrar_escalonamento(
        motivo=motivo_livre,
        resumo="Resumo operacional do chamado.",
    )
    assert res["registrado"] is True
    assert res["motivo"] == esperado
    assert res["protocolo"] == "NÃO INFORMADO"


@pytest.mark.parametrize(
    ("motivo", "resumo"),
    [
        ("", "Resumo válido"),
        ("motivo_invalido_xyz", "Resumo válido"),
        ("cancelamento", ""),
        ("acima_48h", "   "),
    ],
)
def test_registrar_escalonamento_rejeita_motivo_ou_resumo_invalidos(motivo, resumo):
    """Garante erro estruturado quando motivo for desconhecido ou resumo estiver vazio."""
    res = agent_val.registrar_escalonamento(motivo=motivo, resumo=resumo)
    assert res["registrado"] is False
    assert "erro" in res
    assert set(agent_val.MOTIVOS_ESCALONAMENTO.keys()).issubset(set(res["motivos_validos"]))


def test_registrar_escalonamento_sanitiza_dados_sensiveis_regra_4():
    """Garante que senhas, CVV, códigos 2FA e fotos de documento não sejam ecoados."""
    res = agent_val.registrar_escalonamento(
        motivo="cobranca_contestada",
        resumo="Cliente enviou senha: 123456, CVV 999, 2FA 884422 e foto de documento.",
        protocolo="NT-2026-205",
    )
    assert res["registrado"] is True
    assert res["dado_sensivel_removido"] is True
    serializado = json.dumps(res, ensure_ascii=False)
    for segredo in ("123456", "999", "884422", "foto de documento"):
        assert segredo not in serializado


@pytest.mark.parametrize(
    ("payload", "segredo_proibido"),
    [
        ("código de dois fatores: 884422", "884422"),
        ("CÓDIGO DE DOIS FATORES: 112233", "112233"),
        ("meu código de dois fatores é 654321", "654321"),
        ("código 2fa 123456", "123456"),
        ("código de 2fa: 654321", "654321"),
        ("foto do meu documento", "foto do meu documento"),
        ("foto da minha cnh", "foto da minha cnh"),
        ("foto do seu rg", "foto do seu rg"),
        ("foto da sua identidade", "foto da sua identidade"),
        ("foto de um documento", "foto de um documento"),
        ("senha: abc", "abc"),
        ("senha=abc", "abc"),
        ("minha senha é abc", "abc"),
        ("password=x", "password=x"),
        ('senha="abc"', "abc"),
        ("senha='123456'", "123456"),
        ('senha: "123456"', "123456"),
        ("senha: 'abc'", "abc"),
        ('código de dois fatores é "112233"', "112233"),
        ('cvv: "999"', "999"),
        ("senha: !123456", "!123456"),
        ("senha: a!b123", "!b123"),
        ("senha: 123/456", "/456"),
    ],
)
def test_todas_ferramentas_val_sanitizam_variacoes_regra_4(payload, segredo_proibido):
    """Garante sanitização de 2FA acentuado, foto possessiva e senha curta nas 3 tools da Val."""
    kb = json.loads(agent_val.executar_ferramenta("consultar_base_conhecimento", {"topico": payload}))
    assert kb["dado_sensivel_removido"] is True
    assert segredo_proibido not in kb["consulta_original"].lower()
    assert segredo_proibido not in json.dumps(kb, ensure_ascii=False).lower()

    st = json.loads(agent_val.executar_ferramenta("verificar_status_chamado", {"protocolo": payload}))
    assert st["dado_sensivel_removido"] is True
    assert segredo_proibido not in st["protocolo"].lower()
    assert segredo_proibido not in json.dumps(st, ensure_ascii=False).lower()

    esc = json.loads(
        agent_val.executar_ferramenta(
            "registrar_escalonamento",
            {"motivo": "cancelamento", "resumo": payload, "protocolo": payload},
        )
    )
    assert esc["registrado"] is True
    assert esc["dado_sensivel_removido"] is True
    assert segredo_proibido not in esc["resumo"].lower()
    assert segredo_proibido not in esc["protocolo"].lower()
    sem_id = {k: v for k, v in esc.items() if k != "id_escalonamento"}
    assert segredo_proibido not in json.dumps(sem_id, ensure_ascii=False).lower()


@pytest.mark.parametrize(
    ("motivo_bruto", "motivo_esperado", "segredo_proibido"),
    [
        ("cancelamento senha: abc", "cancelamento", "abc"),
        ("cancelamento senha: 123456", "cancelamento", "123456"),
        ("cancelamento código de dois fatores: 112233", "cancelamento", "112233"),
        ("cobranca_contestada foto do meu documento", "cobranca_contestada", "foto do meu documento"),
        ('cancelamento senha="abc"', "cancelamento", "abc"),
        ("cancelamento senha: !123456", "cancelamento", "!123456"),
    ],
)
def test_registrar_escalonamento_sanitiza_motivo_informado(
    motivo_bruto, motivo_esperado, segredo_proibido
):
    """Garante que `motivo_informado` também é sanitizado quando contém credencial ou documento."""
    res = agent_val.registrar_escalonamento(
        motivo=motivo_bruto,
        resumo="Solicitação validada sem dados extras.",
        protocolo="NT-2026-100",
    )
    assert res["registrado"] is True
    assert res["motivo"] == motivo_esperado
    assert res["dado_sensivel_removido"] is True
    assert segredo_proibido not in res["motivo_informado"].lower()
    sem_id = {k: v for k, v in res.items() if k != "id_escalonamento"}
    assert segredo_proibido not in json.dumps(sem_id, ensure_ascii=False).lower()


@pytest.mark.parametrize(
    "prosa_normal",
    [
        "esqueci minha senha hoje",
        "esqueci minha senha do portal",
        "esqueci minha senha",
        "como alterar a senha de acesso",
        "foto do meu modem",
        "cvv e código 2fa",
        "esqueci minha senha e quero trocar",
        "troquei a senha e deu erro",
        "cvv e codigo 2fa",
        "esqueci minha senha e modem",
        "duvida sobre senha e fatura",
        "não recebi o código 2fa e preciso de ajuda",
        "código 2fa (2 tentativas)",
        "Qual minha senha: ?",
    ],
)
def test_val_prosa_normal_sobre_senha_nao_gera_falso_positivo(prosa_normal):
    """Garante que menções comuns sem segredo real preservam a prosa normal intacta."""
    kb = agent_val.consultar_base_conhecimento(prosa_normal)
    assert kb["dado_sensivel_removido"] is False
    assert kb["consulta_original"] == prosa_normal

    st = agent_val.verificar_status_chamado(prosa_normal)
    assert st["dado_sensivel_removido"] is False
    assert st["protocolo"] == prosa_normal.upper()

    esc = agent_val.registrar_escalonamento(
        motivo="excecao_politica",
        resumo=f"Cliente relatou: {prosa_normal}.",
    )
    assert esc["registrado"] is True
    assert esc["dado_sensivel_removido"] is False
    assert prosa_normal in esc["resumo"]


@pytest.mark.parametrize(
    ("consulta", "topico_esperado"),
    [
        ("esqueci minha senha e modem", "suporte_modem"),
        ("duvida sobre senha e fatura", "fatura"),
    ],
)
def test_val_kb_preserva_consulta_com_palavra_chave_e_topico(consulta, topico_esperado):
    """Garante que prosa `<credencial> e <topico>` preserva consulta e resolve o tópico na KB."""
    res = agent_val.consultar_base_conhecimento(consulta)
    assert res["encontrado"] is True
    assert res["topico"] == topico_esperado
    assert res["dado_sensivel_removido"] is False
    assert res["consulta_original"] == consulta


# ==============================================================================
# SEÇÃO E — Loop ReAct offline de `agent_val.responder`
# ==============================================================================


def test_agent_val_responder_fluxo_chamado_acima_48h_e_escalonamento(
    mock_openai, criar_resposta_mock, criar_tool_call_mock
):
    """Valida ciclo multi-turno `verificar_status_chamado` (>48h) -> `registrar_escalonamento`."""
    tc_status = criar_tool_call_mock(
        "call_status",
        "verificar_status_chamado",
        json.dumps({"protocolo": "NT-2026-100"}),
    )
    tc_esc = criar_tool_call_mock(
        "call_esc",
        "registrar_escalonamento",
        json.dumps({
            "motivo": "acima_48h",
            "resumo": "Sem conexão há 60h com luz vermelha no modem.",
            "protocolo": "NT-2026-100",
        }),
    )
    mock_openai.chat.completions.create.side_effect = [
        criar_resposta_mock(tool_calls=[tc_status]),
        criar_resposta_mock(tool_calls=[tc_esc]),
        criar_resposta_mock(content="Bom dia, sou a Val, da Nimbus Telecom. Seu caso foi escalonado."),
    ]
    mensagens = [
        {"role": "system", "content": agent_val.carregar_contexto()},
        {"role": "user", "content": "Meu chamado NT-2026-100 está aberto há 60 horas."},
    ]

    resposta = agent_val.responder(mensagens)

    assert "Nimbus Telecom" in resposta
    assert mock_openai.chat.completions.create.call_args_list[0].kwargs["tools"] == agent_val.FERRAMENTAS
    tool_msgs = [m for m in mensagens if m.get("role") == "tool"]
    assert len(tool_msgs) == 2
    assert json.loads(tool_msgs[0]["content"])["requer_escalonamento"] is True
    assert json.loads(tool_msgs[1]["content"])["registrado"] is True


def test_agent_val_responder_recuperacao_tool_use_failed_isolada(
    mock_openai, criar_resposta_mock
):
    """Garante que recuperação de `tool_use_failed` cita apenas as 4 tools da Val."""
    mock_openai.chat.completions.create.side_effect = [
        RuntimeError("Error code: 400 - tool_use_failed"),
        criar_resposta_mock(content="Recuperado."),
    ]
    mensagens = [{"role": "user", "content": "Consulte meu plano"}]

    resposta = agent_val.responder(mensagens)

    assert resposta == "Recuperado."
    aviso = next(m["content"] for m in mensagens if "Use EXATAMENTE" in m.get("content", ""))
    for permitida in ("somar", "consultar_base_conhecimento", "verificar_status_chamado", "registrar_escalonamento"):
        assert permitida in aviso
    for alheia in ("listar_arquivos", "verificar_sintaxe_python", "analisar_complexidade_codigo"):
        assert alheia not in aviso
