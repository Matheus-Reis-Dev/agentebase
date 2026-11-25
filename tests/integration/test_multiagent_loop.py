"""Testes de integração cross-module do loop ReAct multiagente para os 5 perfis."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

import agent
import agent_ada
import agent_base
import agent_core
import agent_lint
import agent_organizador
import agent_val

PERFIS_MODULOS: dict[str, Any] = {
    "agent.md": agent_base,
    "agent-ada.md": agent_ada,
    "agent-lint.md": agent_lint,
    "agent-val.md": agent_val,
    "agent-organizador.md": agent_organizador,
}

FERRAMENTAS_ESPERADAS: dict[str, set[str]] = {
    "agent.md": {"somar"},
    "agent-ada.md": {
        "somar",
        "verificar_sintaxe_python",
        "analisar_logica_codigo",
        "gerar_exemplo_analogo",
    },
    "agent-lint.md": {
        "somar",
        "analisar_complexidade_codigo",
        "detectar_antipadroes_python",
        "gerar_checklist_revisao",
    },
    "agent-val.md": {
        "somar",
        "consultar_base_conhecimento",
        "verificar_status_chamado",
        "registrar_escalonamento",
    },
    "agent-organizador.md": {
        "obter_pastas_padrao",
        "listar_arquivos",
        "criar_pasta",
        "mover_arquivo",
        "ler_conteudo_ou_resumo",
    },
}

TODAS_FERRAMENTAS: set[str] = set().union(*FERRAMENTAS_ESPERADAS.values())

FATOS_MEMORY_MD: tuple[str, ...] = (
    "O usuário possui muitos arquivos espalhados",
    "Fotos da viagem para europa",
    "Boletos e Comprovantes",
    "sem saudações desnecessárias",
)

MARCADORES_PERSONA: dict[str, str] = {
    "agent.md": "Você é um assistente que responde em português do Brasil.",
    "agent-ada.md": "socrático",
    "agent-lint.md": "Conclusão primeiro",
    "agent-val.md": "Nimbus Telecom",
    "agent-organizador.md": "Hierarquia de Pastas Obrigatória",
}


def _instalar_snapshots_openai(mock_openai: Any, respostas: list[Any]) -> list[dict[str, Any]]:
    """Configura `side_effect` registrando cópia profunda de `messages` e `tools` a cada turno."""
    fila = list(respostas)
    chamadas: list[dict[str, Any]] = []

    def _create(**kwargs: Any) -> Any:
        chamadas.append({
            "messages": copy.deepcopy(kwargs.get("messages", [])),
            "tools": kwargs.get("tools"),
            "model": kwargs.get("model"),
            "temperature": kwargs.get("temperature"),
        })
        evento = fila.pop(0)
        if isinstance(evento, BaseException):
            raise evento
        return evento

    mock_openai.chat.completions.create.side_effect = _create
    return chamadas


def _nomes_tools_payload(tools_payload: list[dict[str, Any]]) -> list[str]:
    """Extrai os nomes das ferramentas do payload `tools=` enviado à OpenAI."""
    return [item["function"]["name"] for item in tools_payload]


def _extrair_json_tool_por_id(mensagens: list[dict[str, Any]], call_id: str) -> dict[str, Any]:
    """Localiza a mensagem `role='tool'` por `tool_call_id` e decodifica seu JSON."""
    for msg in mensagens:
        if msg.get("role") == "tool" and msg.get("tool_call_id") == call_id:
            return json.loads(msg["content"])
    raise AssertionError(f"Mensagem tool com tool_call_id={call_id!r} não encontrada.")


# ==============================================================================
# 1. LOOP REACT MULTI-TURNO E MULTI-FERRAMENTA PARA TODOS OS 5 PERFIS
# ==============================================================================


def _montar_cenario_multiturno(
    perfil: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Constrói cenário determinístico de 3 turnos (lote + encadeado + texto) por perfil."""
    if perfil == "agent.md":
        return {
            "prompt": "Some 2+3, 10+15 e depois 5+25.",
            "turno1": [("c1", "somar", {"a": 2, "b": 3}), ("c2", "somar", {"a": 10, "b": 15})],
            "turno2": [("c3", "somar", {"a": 5, "b": 25})],
            "final": "As somas são 5, 25 e 30.",
            "verificacoes": [("c1", "resultado", 5), ("c2", "resultado", 25), ("c3", "resultado", 30)],
        }
    if perfil == "agent-ada.md":
        codigo = "i = 0\nwhile i < 3:\n    print(i)\n"
        return {
            "prompt": "Meu laço while não termina; cheque sintaxe, lógica e me dê uma analogia.",
            "turno1": [
                ("c1", "verificar_sintaxe_python", {"codigo": codigo}),
                ("c2", "analisar_logica_codigo", {"codigo": codigo}),
            ],
            "turno2": [("c3", "gerar_exemplo_analogo", {"conceito": "while"})],
            "final": "Qual variável na condição precisa mudar a cada repetição?",
            "verificacoes": [("c1", "sintaxe_valida", True), ("c2", "analisavel", True), ("c3", "conceito", "while")],
        }
    if perfil == "agent-lint.md":
        codigo = "def f(a=[]):\n    return eval('1')\n"
        return {
            "prompt": "Revise esta função com foco em segurança.",
            "turno1": [
                ("c1", "analisar_complexidade_codigo", {"codigo": codigo}),
                ("c2", "detectar_antipadroes_python", {"codigo": codigo}),
            ],
            "turno2": [("c3", "gerar_checklist_revisao", {"tipo_mudanca": "seguranca"})],
            "final": "Reprovado: uso de eval() e argumento mutável padrão.",
            "verificacoes": [
                ("c1", "total_funcoes", 1),
                ("c2", "veredito", "problemas_encontrados"),
                ("c3", "tipo_mudanca", "seguranca"),
            ],
        }
    if perfil == "agent-val.md":
        return {
            "prompt": "Meu chamado NT-2026-100 passou de 48h e quero entender o SLA.",
            "turno1": [
                ("c1", "consultar_base_conhecimento", {"topico": "sla"}),
                ("c2", "verificar_status_chamado", {"protocolo": "NT-2026-100"}),
            ],
            "turno2": [(
                "c3",
                "registrar_escalonamento",
                {"motivo": "acima_48h", "resumo": "Sem conexão há 60h.", "protocolo": "NT-2026-100"},
            )],
            "final": "Bom dia, sou a Val, da Nimbus Telecom. Seu chamado foi escalonado.",
            "verificacoes": [
                ("c1", "topico", "sla"),
                ("c2", "requer_escalonamento", True),
                ("c3", "registrado", True),
            ],
        }

    fake_home = tmp_path / "home"
    entrada_dir = fake_home / "Downloads"
    destino_dir = tmp_path / "Organizados" / "2026" / "Documentos" / "03" / "10"
    entrada_dir.mkdir(parents=True)
    arquivo = entrada_dir / "nota.txt"
    arquivo.write_text("Comprovante de pagamento de março.", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    return {
        "prompt": "Organize minha pasta Downloads.",
        "turno1": [
            ("c1", "obter_pastas_padrao", {}),
            ("c2", "listar_arquivos", {"diretorio": str(entrada_dir), "limite": 5}),
        ],
        "turno2": [
            ("c3", "ler_conteudo_ou_resumo", {"caminho_arquivo": str(arquivo), "limite_caracteres": 100}),
            ("c4", "criar_pasta", {"caminho": str(destino_dir)}),
            ("c5", "mover_arquivo", {"origem": str(arquivo), "destino": str(destino_dir)}),
        ],
        "final": "Arquivo movido para a estrutura organizada.",
        "verificacoes": [("c1", "downloads", str(entrada_dir)), ("c2", "total_encontrados", 1), ("c5", "sucesso", True)],
    }


@pytest.mark.parametrize("perfil", list(PERFIS_MODULOS.keys()))
def test_react_multiturno_executa_ferramentas_e_transicoes_de_papel(
    perfil,
    mock_openai,
    criar_resposta_mock,
    criar_tool_call_mock,
    tmp_path,
    monkeypatch,
):
    """Valida payload `tools=`, execução multi-tool e transições `system->user->assistant->tool->assistant`."""
    modulo = PERFIS_MODULOS[perfil]
    cenario = _montar_cenario_multiturno(perfil, tmp_path, monkeypatch)

    tcs_1 = [criar_tool_call_mock(cid, nome, json.dumps(args)) for cid, nome, args in cenario["turno1"]]
    tcs_2 = [criar_tool_call_mock(cid, nome, json.dumps(args)) for cid, nome, args in cenario["turno2"]]
    chamadas = _instalar_snapshots_openai(
        mock_openai,
        [
            criar_resposta_mock(tool_calls=tcs_1),
            criar_resposta_mock(tool_calls=tcs_2),
            criar_resposta_mock(content=cenario["final"]),
        ],
    )

    mensagens = [
        {"role": "system", "content": modulo.carregar_contexto()},
        {"role": "user", "content": cenario["prompt"]},
    ]
    resposta = modulo.responder(mensagens)

    assert resposta == cenario["final"]
    assert len(chamadas) == 3
    for chamada in chamadas:
        assert chamada["tools"] == modulo.FERRAMENTAS
        assert set(_nomes_tools_payload(chamada["tools"])) == FERRAMENTAS_ESPERADAS[perfil]

    assert [m["role"] for m in chamadas[0]["messages"]] == ["system", "user"]
    papeis_esperados = (
        ["system", "user", "assistant"]
        + ["tool"] * len(tcs_1)
        + ["assistant"]
        + ["tool"] * len(tcs_2)
    )
    assert [m["role"] for m in chamadas[2]["messages"]] == papeis_esperados
    assert [m["role"] for m in mensagens] == papeis_esperados + ["assistant"]
    assert "tool_calls" in mensagens[2]
    assert mensagens[-1] == {"role": "assistant", "content": cenario["final"]}

    for call_id, chave, esperado in cenario["verificacoes"]:
        dados = _extrair_json_tool_por_id(mensagens, call_id)
        assert dados[chave] == esperado


# ==============================================================================
# 2. RECUPERAÇÃO DE `tool_use_failed` E `Tool call validation failed` POR PERFIL
# ==============================================================================


@pytest.mark.parametrize("perfil", list(PERFIS_MODULOS.keys()))
@pytest.mark.parametrize(
    "erro_api",
    [
        "Error code: 400 - tool_use_failed",
        "Tool call validation failed: tool call is not in allowed list",
    ],
)
def test_react_recuperacao_erro_validacao_lista_somente_tools_do_perfil(
    perfil,
    erro_api,
    mock_openai,
    criar_resposta_mock,
    criar_tool_call_mock,
    tmp_path,
):
    """Valida recuperação dos dois erros de validação listando só tools permitidas e retomando o loop."""
    modulo = PERFIS_MODULOS[perfil]
    if perfil == "agent-organizador.md":
        tc_valido = criar_tool_call_mock("c_ok", "listar_arquivos", json.dumps({"diretorio": str(tmp_path)}))
        chave_ok = "diretorio"
    else:
        tc_valido = criar_tool_call_mock("c_ok", "somar", json.dumps({"a": 4, "b": 6}))
        chave_ok = "resultado"

    chamadas = _instalar_snapshots_openai(
        mock_openai,
        [
            RuntimeError(erro_api),
            criar_resposta_mock(tool_calls=[tc_valido]),
            criar_resposta_mock(content="Recuperado e concluído."),
        ],
    )
    mensagens = [
        {"role": "system", "content": modulo.carregar_contexto()},
        {"role": "user", "content": "Execute uma ação."},
    ]

    resposta = modulo.responder(mensagens)

    assert resposta == "Recuperado e concluído."
    assert len(chamadas) == 3
    aviso = next(
        m["content"]
        for m in mensagens
        if m.get("role") == "user" and "Use EXATAMENTE" in m.get("content", "")
    )
    permitidas = FERRAMENTAS_ESPERADAS[perfil]
    proibidas = TODAS_FERRAMENTAS - permitidas
    for tool_ok in permitidas:
        assert tool_ok in aviso
    for tool_alheia in proibidas:
        assert tool_alheia not in aviso

    dados_ok = _extrair_json_tool_por_id(mensagens, "c_ok")
    assert chave_ok in dados_ok


# ==============================================================================
# 3. REJEIÇÃO DE TOOL CALL ESTRANGEIRA DENTRO DO LOOP REACT
# ==============================================================================


@pytest.mark.parametrize(
    ("perfil", "tool_estrangeira", "args_estrangeiros"),
    [
        ("agent.md", "listar_arquivos", {"diretorio": "."}),
        ("agent-ada.md", "registrar_escalonamento", {"motivo": "acima_48h", "resumo": "x"}),
        ("agent-lint.md", "verificar_sintaxe_python", {"codigo": "x = 1"}),
        ("agent-val.md", "criar_pasta", {"caminho": "pasta_proibida"}),
        ("agent-organizador.md", "somar", {"a": 1, "b": 2}),
    ],
)
def test_react_rejeita_chamada_ferramenta_estrangeira_sem_efeito_colateral(
    perfil,
    tool_estrangeira,
    args_estrangeiros,
    mock_openai,
    criar_resposta_mock,
    criar_tool_call_mock,
    tmp_path,
    monkeypatch,
):
    """Garante bloqueio de tool estrangeira dentro de `responder()` sem efeitos colaterais."""
    monkeypatch.chdir(tmp_path)
    modulo = PERFIS_MODULOS[perfil]
    tc_proibido = criar_tool_call_mock("c_foreign", tool_estrangeira, json.dumps(args_estrangeiros))

    chamadas = _instalar_snapshots_openai(
        mock_openai,
        [
            criar_resposta_mock(tool_calls=[tc_proibido]),
            criar_resposta_mock(content="Não tenho acesso a essa ferramenta."),
        ],
    )
    mensagens = [
        {"role": "system", "content": modulo.carregar_contexto()},
        {"role": "user", "content": "Tente executar uma ferramenta de outro perfil."},
    ]

    resposta = modulo.responder(mensagens)

    assert resposta == "Não tenho acesso a essa ferramenta."
    assert len(chamadas) == 2
    erro_tool = _extrair_json_tool_por_id(mensagens, "c_foreign")
    assert erro_tool == {"erro": f"Ferramenta '{tool_estrangeira}' não existe."}
    assert not (tmp_path / "pasta_proibida").exists()


# ==============================================================================
# 4. ISOLAMENTO DE SYSTEM PROMPT + `responder_perfil()` + ROTEAMENTO CLI
# ==============================================================================


@pytest.mark.parametrize("perfil", list(PERFIS_MODULOS.keys()))
def test_isolamento_system_prompt_memory_md_no_fluxo_responder(
    perfil,
    mock_openai,
    criar_resposta_mock,
):
    """Verifica que `memory.md` é enviado à OpenAI somente no Organizador e isolado nos demais."""
    modulo = PERFIS_MODULOS[perfil]
    chamadas = _instalar_snapshots_openai(mock_openai, [criar_resposta_mock(content="OK")])
    mensagens = [
        {"role": "system", "content": modulo.carregar_contexto()},
        {"role": "user", "content": "Olá"},
    ]

    modulo.responder(mensagens)

    system_enviado = chamadas[0]["messages"][0]["content"]
    assert MARCADORES_PERSONA[perfil] in system_enviado
    assert "# Memória" in system_enviado
    if perfil == "agent-organizador.md":
        for fato in FATOS_MEMORY_MD:
            assert fato in system_enviado
    else:
        assert modulo.MEMORIA_PADRAO in system_enviado
        for fato in FATOS_MEMORY_MD:
            assert fato not in system_enviado


@pytest.mark.parametrize("perfil", list(PERFIS_MODULOS.keys()))
def test_agent_core_responder_perfil_roteia_e_isola_ferramentas(
    perfil,
    mock_openai,
    criar_resposta_mock,
    criar_tool_call_mock,
    tmp_path,
):
    """Valida despacho de `agent_core.responder_perfil` para os 5 perfis com tools isoladas."""
    modulo = PERFIS_MODULOS[perfil]
    if perfil == "agent-organizador.md":
        tc = criar_tool_call_mock("c_p", "criar_pasta", json.dumps({"caminho": str(tmp_path / "nova")}))
    else:
        tc = criar_tool_call_mock("c_p", "somar", json.dumps({"a": 3, "b": 4}))

    chamadas = _instalar_snapshots_openai(
        mock_openai,
        [criar_resposta_mock(tool_calls=[tc]), criar_resposta_mock(content="Roteado.")],
    )
    mensagens = [{"role": "user", "content": "Teste de roteamento"}]

    resposta = agent_core.responder_perfil(perfil, mensagens)

    assert resposta == "Roteado."
    assert chamadas[0]["tools"] == modulo.FERRAMENTAS
    if perfil == "agent-organizador.md":
        assert (tmp_path / "nova").is_dir()
    else:
        assert _extrair_json_tool_por_id(mensagens, "c_p")["resultado"] == 7


def test_agent_core_responder_perfil_desconhecido_lanca_value_error():
    """Garante erro explícito quando `responder_perfil` recebe perfil inexistente."""
    with pytest.raises(ValueError, match="desconhecido"):
        agent_core.responder_perfil("agent-inexistente.md", [{"role": "user", "content": "Oi"}])


@pytest.mark.parametrize(
    ("env_perfil", "esperado_titulo"),
    [
        ("agent.md", "agent.md"),
        ("  agent-ada.md  ", "agent-ada.md"),
        ("agent-lint.md", "agent-lint.md"),
        ("agent-val.md", "agent-val.md"),
        ("agent-organizador.md", "agent-organizador.md"),
    ],
)
def test_cli_resolver_executor_e_main_com_agente_perfil_valido(
    env_perfil,
    esperado_titulo,
    monkeypatch,
    mock_openai,
    criar_resposta_mock,
    capsys,
):
    """Valida roteamento via `AGENTE_PERFIL` em `agent._resolver_executor_cli()` e `agent.main()`."""
    modulo = PERFIS_MODULOS[esperado_titulo]
    monkeypatch.setenv("AGENTE_PERFIL", env_perfil)

    titulo, fn_ctx, fn_resp = agent._resolver_executor_cli()
    assert titulo == esperado_titulo
    assert fn_ctx is modulo.carregar_contexto
    assert fn_resp is modulo.responder

    chamadas = _instalar_snapshots_openai(mock_openai, [criar_resposta_mock(content="Resposta CLI.")])
    entradas = iter(["Pergunta de teste", "sair"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(entradas))

    agent.main()

    saida = capsys.readouterr().out
    assert esperado_titulo in saida
    assert "Resposta CLI." in saida
    assert chamadas[0]["tools"] == modulo.FERRAMENTAS
    assert MARCADORES_PERSONA[esperado_titulo] in chamadas[0]["messages"][0]["content"]


@pytest.mark.parametrize("env_perfil", ["", "   ", "perfil-invalido.md"])
def test_cli_resolver_executor_fallback_para_organizador(env_perfil, monkeypatch):
    """Garante fallback seguro para a fachada `agent` quando `AGENTE_PERFIL` é vazio ou inválido."""
    monkeypatch.setenv("AGENTE_PERFIL", env_perfil)

    titulo, fn_ctx, fn_resp = agent._resolver_executor_cli()

    assert titulo == "Agente Organizador de Arquivos"
    assert fn_ctx is agent.carregar_contexto
    assert fn_resp is agent.responder
