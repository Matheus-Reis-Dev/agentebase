"""Módulo de Evals determinísticos multiagente (Prompt Contract Testing offline).

Cobre os 5 perfis do repositório (`agent.md`, `agent-ada.md`, `agent-lint.md`,
`agent-val.md`, `agent-organizador.md`) nas 4 dimensões de avaliação:
1. Tool Selection & JSON Contract
2. Profile Tool & Memory Isolation
3. Persona Adherence Without Spurious Tool Calls
4. Circuit Breaker Resilience (`MAX_ITERACOES`)
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

import agent
import agent_ada
import agent_core
import agent_lint
import agent_val

TODAS_FERRAMENTAS: frozenset[str] = frozenset({
    "somar",
    "verificar_sintaxe_python",
    "analisar_logica_codigo",
    "gerar_exemplo_analogo",
    "analisar_complexidade_codigo",
    "detectar_antipadroes_python",
    "gerar_checklist_revisao",
    "consultar_base_conhecimento",
    "verificar_status_chamado",
    "registrar_escalonamento",
    "obter_pastas_padrao",
    "listar_arquivos",
    "criar_pasta",
    "mover_arquivo",
    "ler_conteudo_ou_resumo",
})

MARCADORES_MEMORIA_ORGANIZADOR: tuple[str, ...] = (
    "Fotos da viagem para europa",
    "Documentos do trabalho",
    "Boletos e Comprovantes",
    "Downloads, Documentos e Área de Trabalho",
)

_SCHEMA_SOMAR: dict[str, Any] = {
    "required": {"a", "b"},
    "props": {"a": "number", "b": "number"},
}

PERFIL_SPECS: dict[str, dict[str, Any]] = {
    "agent.md": {
        "tools": frozenset({"somar"}),
        "usa_memory_md": False,
        "tool_segura_loop": ("somar", {"a": 1, "b": 1}),
        "ferramenta_estrangeira": ("listar_arquivos", {"diretorio": "."}),
        "marcadores_persona": (
            "# Agente base",
            "## Identidade",
            "Direto ao ponto.",
            "Não invente.",
            "Use as ferramentas quando elas souberem melhor que você.",
        ),
        "tool_schemas_esperados": {
            "somar": _SCHEMA_SOMAR,
        },
    },
    "agent-ada.md": {
        "tools": frozenset({
            "somar",
            "verificar_sintaxe_python",
            "analisar_logica_codigo",
            "gerar_exemplo_analogo",
        }),
        "usa_memory_md": False,
        "tool_segura_loop": ("somar", {"a": 2, "b": 3}),
        "ferramenta_estrangeira": ("detectar_antipadroes_python", {"codigo": "x = 1"}),
        "marcadores_persona": (
            "# Ada — tutora socrática",
            "você não entrega a resposta pronta.",
            "Uma pergunta por vez.",
            "Nunca dê o código pronto de um exercício.",
            "Use ferramenta em silêncio, sem narrar.",
        ),
        "tool_schemas_esperados": {
            "somar": _SCHEMA_SOMAR,
            "verificar_sintaxe_python": {"required": {"codigo"}, "props": {"codigo": "string"}},
            "analisar_logica_codigo": {"required": {"codigo"}, "props": {"codigo": "string"}},
            "gerar_exemplo_analogo": {"required": {"conceito"}, "props": {"conceito": "string"}},
        },
    },
    "agent-lint.md": {
        "tools": frozenset({
            "somar",
            "analisar_complexidade_codigo",
            "detectar_antipadroes_python",
            "gerar_checklist_revisao",
        }),
        "usa_memory_md": False,
        "tool_segura_loop": ("somar", {"a": 10, "b": 5}),
        "ferramenta_estrangeira": ("consultar_base_conhecimento", {"topico": "planos"}),
        "marcadores_persona": (
            "# Lint — revisor técnico sênior",
            "Conclusão primeiro.",
            "ordenados por gravidade",
            "Separe o que você sabe do que você supõe.",
            "Não invente API.",
            "Se o código estiver bom, diga que está bom e pare.",
        ),
        "tool_schemas_esperados": {
            "somar": _SCHEMA_SOMAR,
            "analisar_complexidade_codigo": {"required": {"codigo"}, "props": {"codigo": "string"}},
            "detectar_antipadroes_python": {"required": {"codigo"}, "props": {"codigo": "string"}},
            "gerar_checklist_revisao": {"required": set(), "props": {"tipo_mudanca": "string"}},
        },
    },
    "agent-val.md": {
        "tools": frozenset({
            "somar",
            "consultar_base_conhecimento",
            "verificar_status_chamado",
            "registrar_escalonamento",
        }),
        "usa_memory_md": False,
        "tool_segura_loop": ("somar", {"a": 99.9, "b": 30.0}),
        "ferramenta_estrangeira": ("verificar_sintaxe_python", {"codigo": "x = 1"}),
        "marcadores_persona": (
            "# Val — atendimento Nimbus Telecom",
            "Nimbus Telecom",
            "Só afirme o que está na base de conhecimento.",
            "Nunca prometa prazo, desconto, isenção ou reembolso.",
            "Não peça dados sensíveis.",
            "Fora do escopo, redirecione com clareza.",
        ),
        "tool_schemas_esperados": {
            "somar": _SCHEMA_SOMAR,
            "consultar_base_conhecimento": {"required": {"topico"}, "props": {"topico": "string"}},
            "verificar_status_chamado": {"required": {"protocolo"}, "props": {"protocolo": "string"}},
            "registrar_escalonamento": {
                "required": {"motivo", "resumo"},
                "props": {"motivo": "string", "resumo": "string", "protocolo": "string"},
            },
        },
    },
    "agent-organizador.md": {
        "tools": frozenset({
            "obter_pastas_padrao",
            "listar_arquivos",
            "criar_pasta",
            "mover_arquivo",
            "ler_conteudo_ou_resumo",
        }),
        "usa_memory_md": True,
        "tool_segura_loop": ("obter_pastas_padrao", {}),
        "ferramenta_estrangeira": ("somar", {"a": 1, "b": 2}),
        "marcadores_persona": (
            "# Org — organizador e classificador de arquivos",
            "Plano antes da ação.",
            "Hierarquia de Pastas Obrigatória",
            "Não invente arquivos nem caminhos.",
            "Segurança de dados.",
        ),
        "tool_schemas_esperados": {
            "obter_pastas_padrao": {"required": set(), "props": {}},
            "listar_arquivos": {
                "required": {"diretorio"},
                "props": {"diretorio": "string", "limite": "integer"},
            },
            "criar_pasta": {"required": {"caminho"}, "props": {"caminho": "string"}},
            "mover_arquivo": {
                "required": {"origem", "destino"},
                "props": {"origem": "string", "destino": "string"},
            },
            "ler_conteudo_ou_resumo": {
                "required": {"caminho_arquivo"},
                "props": {"caminho_arquivo": "string", "limite_caracteres": "integer"},
            },
        },
    },
}


def _extrair_ferramentas_markdown(md_path: Path) -> set[str]:
    """Extrai os nomes de ferramentas declaradas na tabela `## Ferramentas disponíveis`."""
    conteudo = md_path.read_text(encoding="utf-8")
    inicio = conteudo.find("## Ferramentas disponíveis")
    assert inicio != -1, f"Seção '## Ferramentas disponíveis' ausente em {md_path}."
    proximo = conteudo.find("\n## ", inicio + 1)
    secao = conteudo[inicio:] if proximo == -1 else conteudo[inicio:proximo]
    return set(re.findall(r"^\|\s*`([a-zA-Z0-9_]+)`\s*\|", secao, flags=re.MULTILINE))


def _executar_eval_tool(
    modulo: Any,
    mock_openai: Any,
    criar_resposta_mock: Any,
    criar_tool_call_mock: Any,
    prompt_usuario: str,
    nome_tool: str,
    argumentos: dict[str, Any],
    resposta_final: str,
) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Executa ciclo eval de 2 turnos (tool_call -> resposta final) e retorna artefatos."""
    historico: list[dict[str, Any]] = [
        {"role": "system", "content": modulo.carregar_contexto()},
        {"role": "user", "content": prompt_usuario},
    ]
    tc = criar_tool_call_mock("call_eval_1", nome_tool, json.dumps(argumentos))
    mock_openai.chat.completions.create.side_effect = [
        criar_resposta_mock(tool_calls=[tc]),
        criar_resposta_mock(content=resposta_final),
    ]

    resposta = modulo.responder(historico)
    kwargs_t1 = mock_openai.chat.completions.create.call_args_list[0].kwargs
    tool_msgs = [m for m in historico if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    tool_json = json.loads(tool_msgs[0]["content"])
    return resposta, historico, kwargs_t1, tool_json


def _validar_contrato_schema(
    tool_def: dict[str, Any],
    esperado: dict[str, Any],
) -> None:
    """Valida estrutura OpenAI Function Calling e tipos de parâmetros do schema."""
    assert tool_def["type"] == "function"
    fn = tool_def["function"]
    assert isinstance(fn["description"], str) and len(fn["description"].strip()) > 0
    params = fn["parameters"]
    assert params["type"] == "object"
    assert set(params.get("required", [])) == esperado["required"]
    props = params["properties"]
    assert set(props.keys()) == set(esperado["props"].keys())
    for campo, tipo_esperado in esperado["props"].items():
        assert props[campo]["type"] == tipo_esperado


# ==============================================================================
# DIMENSÃO 1: TOOL SELECTION & JSON CONTRACT
# ==============================================================================


@pytest.mark.parametrize("perfil", list(PERFIL_SPECS))
def test_eval_contrato_prompt_e_schemas_por_perfil(perfil: str) -> None:
    """EVAL D1.1: Valida contrato do prompt de sistema e schemas OpenAI por perfil."""
    modulo = agent_core.obter_modulo_perfil(perfil)
    spec = PERFIL_SPECS[perfil]

    assert modulo.PERFIL_NOME == perfil
    contexto = modulo.carregar_contexto()
    assert "## Identidade" in contexto
    assert "## Ferramentas disponíveis" in contexto
    for marcador in spec["marcadores_persona"]:
        assert marcador in contexto

    schemas_por_nome = {t["function"]["name"]: t for t in modulo.FERRAMENTAS}
    esperados = spec["tool_schemas_esperados"]
    assert set(schemas_por_nome.keys()) == set(esperados.keys())
    for nome, contrato in esperados.items():
        _validar_contrato_schema(schemas_por_nome[nome], contrato)


@pytest.mark.parametrize("perfil", ["agent.md", "agent-ada.md", "agent-lint.md", "agent-val.md"])
def test_eval_selecao_somar_perfis_habilitados(
    perfil: str,
    mock_openai: Any,
    criar_resposta_mock: Any,
    criar_tool_call_mock: Any,
) -> None:
    """EVAL D1.2: Perfis habilitados acionam `somar` com contrato JSON exato."""
    modulo = agent_core.obter_modulo_perfil(perfil)
    spec = PERFIL_SPECS[perfil]

    resposta, historico, kwargs_t1, tool_json = _executar_eval_tool(
        modulo,
        mock_openai,
        criar_resposta_mock,
        criar_tool_call_mock,
        "Some exatamente 17.5 com 2.5.",
        "somar",
        {"a": 17.5, "b": 2.5},
        "O resultado exato é 20.0.",
    )

    assert mock_openai.chat.completions.create.call_count == 2
    assert kwargs_t1["model"] == agent_core.MODELO
    assert kwargs_t1["temperature"] == agent_core.TEMPERATURA
    assert spec["marcadores_persona"][0] in kwargs_t1["messages"][0]["content"]
    assert any(t["function"]["name"] == "somar" for t in kwargs_t1["tools"])
    assert tool_json == {"a": 17.5, "b": 2.5, "resultado": 20.0}
    assert historico[-1] == {"role": "assistant", "content": resposta}


def _checar_ada_sintaxe(dados: dict[str, Any]) -> None:
    assert dados["sintaxe_valida"] is False
    assert isinstance(dados.get("linha"), int)
    assert len(dados.get("pergunta_socratica", "").strip()) > 0


def _checar_ada_logica(dados: dict[str, Any]) -> None:
    assert dados["analisavel"] is True
    assert dados["resumo_estrutural"]["lacos_while"] == 1
    assert len(dados.get("perguntas_guia", [])) >= 1
    textos = " ".join(dados.get("observacoes_logicas", []) + dados.get("perguntas_guia", []))
    assert "```" not in textos and "def " not in textos and "x += 1" not in textos


def _checar_ada_analogia(dados: dict[str, Any]) -> None:
    assert dados["reconhecido"] is True
    assert len(dados.get("dominio_analogo", "").strip()) > 0
    assert len(dados.get("pergunta_reflexao", "").strip()) > 0


@pytest.mark.parametrize(
    ("nome_tool", "argumentos", "prompt", "checar_json"),
    [
        (
            "verificar_sintaxe_python",
            {"codigo": "while True\n    print(1)"},
            "Meu código Python não roda, pode checar a sintaxe?",
            _checar_ada_sintaxe,
        ),
        (
            "analisar_logica_codigo",
            {"codigo": "x = 0\nwhile x < 5:\n    print(x)"},
            "Meu laço while não termina nunca.",
            _checar_ada_logica,
        ),
        (
            "gerar_exemplo_analogo",
            {"conceito": "while"},
            "Não entendi como funciona o laço while, me dá uma analogia?",
            _checar_ada_analogia,
        ),
    ],
)
def test_eval_selecao_ferramentas_dominio_ada(
    nome_tool: str,
    argumentos: dict[str, Any],
    prompt: str,
    checar_json: Any,
    mock_openai: Any,
    criar_resposta_mock: Any,
    criar_tool_call_mock: Any,
) -> None:
    """EVAL D1.3: Ada seleciona ferramentas de sintaxe, lógica socrática e analogia."""
    modulo = agent_core.obter_modulo_perfil("agent-ada.md")
    resposta, historico, kwargs_t1, tool_json = _executar_eval_tool(
        modulo,
        mock_openai,
        criar_resposta_mock,
        criar_tool_call_mock,
        prompt,
        nome_tool,
        argumentos,
        "O que precisa mudar para a condição deixar de ser verdadeira?",
    )

    assert any(t["function"]["name"] == nome_tool for t in kwargs_t1["tools"])
    checar_json(tool_json)
    assert historico[-1] == {"role": "assistant", "content": resposta}


def _checar_lint_complexidade(dados: dict[str, Any]) -> None:
    assert dados["codigo_valido"] is True
    assert dados["total_funcoes"] == 1
    assert dados["complexidade_maxima"] >= 2
    assert len(dados.get("resumo", "").strip()) > 0


def _checar_lint_sujo(dados: dict[str, Any]) -> None:
    assert dados["veredito"] == "problemas_encontrados"
    assert dados["total_achados"] >= 3
    assert dados["achados"][0]["gravidade"] == "alta"


def _checar_lint_limpo(dados: dict[str, Any]) -> None:
    assert dados["veredito"] == "limpo"
    assert dados["total_achados"] == 0
    assert dados["achados"] == []


def _checar_lint_checklist(dados: dict[str, Any]) -> None:
    assert dados["tipo_mudanca"] == "seguranca"
    assert dados["fallback_geral"] is False
    assert dados["total_itens"] >= 1
    assert len(dados.get("criterio_bloqueio", "").strip()) > 0


@pytest.mark.parametrize(
    ("nome_tool", "argumentos", "prompt", "checar_json"),
    [
        (
            "analisar_complexidade_codigo",
            {"codigo": "def avaliar(x, y):\n    if x > 0 and y > 0:\n        return x + y\n    return 0\n"},
            "Avalie a complexidade da função avaliar.",
            _checar_lint_complexidade,
        ),
        (
            "detectar_antipadroes_python",
            {"codigo": "def f(acc=[]):\n    try:\n        eval('1')\n    except:\n        pass\n"},
            "Revise este código com default mutável, eval e except pass.",
            _checar_lint_sujo,
        ),
        (
            "detectar_antipadroes_python",
            {"codigo": "def dobrar(n: int) -> int:\n    return n * 2\n"},
            "Revise este código limpo.",
            _checar_lint_limpo,
        ),
        (
            "gerar_checklist_revisao",
            {"tipo_mudanca": "seguranca"},
            "Gere um checklist de revisão para uma mudança de segurança.",
            _checar_lint_checklist,
        ),
    ],
)
def test_eval_selecao_ferramentas_dominio_lint(
    nome_tool: str,
    argumentos: dict[str, Any],
    prompt: str,
    checar_json: Any,
    mock_openai: Any,
    criar_resposta_mock: Any,
    criar_tool_call_mock: Any,
) -> None:
    """EVAL D1.4: Lint seleciona análise de complexidade, antipadrões e checklist."""
    modulo = agent_core.obter_modulo_perfil("agent-lint.md")
    resposta, historico, kwargs_t1, tool_json = _executar_eval_tool(
        modulo,
        mock_openai,
        criar_resposta_mock,
        criar_tool_call_mock,
        prompt,
        nome_tool,
        argumentos,
        "Conclusão: revisão estática concluída.",
    )

    assert any(t["function"]["name"] == nome_tool for t in kwargs_t1["tools"])
    checar_json(tool_json)
    assert historico[-1] == {"role": "assistant", "content": resposta}


def _checar_val_kb_hit(dados: dict[str, Any]) -> None:
    assert dados["encontrado"] is True
    assert dados["topico"] == "planos"
    assert "Nimbus Telecom" in dados["empresa"]
    assert len(dados["detalhes"]) >= 1


def _checar_val_kb_fora_escopo(dados: dict[str, Any]) -> None:
    assert dados["encontrado"] is False
    assert "internet fixa" in dados["escopo"]


def _checar_val_status_48h(dados: dict[str, Any]) -> None:
    assert dados["encontrado"] is True
    assert dados["horas_em_aberto"] == 60
    assert dados["requer_escalonamento"] is True
    assert dados["motivo_escalonamento_sugerido"] == "acima_48h"


def _checar_val_escalonamento(dados: dict[str, Any]) -> None:
    assert dados["registrado"] is True
    assert dados["status"] == "escalonado"
    assert dados["promessa_sla_ou_desconto"] is False
    assert len(dados.get("area_destino", "").strip()) > 0


@pytest.mark.parametrize(
    ("nome_tool", "argumentos", "prompt", "checar_json"),
    [
        (
            "consultar_base_conhecimento",
            {"topico": "planos"},
            "Quais são os planos de internet fixa disponíveis?",
            _checar_val_kb_hit,
        ),
        (
            "consultar_base_conhecimento",
            {"topico": "telefonia movel"},
            "Vocês têm planos de telefonia móvel?",
            _checar_val_kb_fora_escopo,
        ),
        (
            "verificar_status_chamado",
            {"protocolo": "NT-2026-100"},
            "Qual o status do meu chamado NT-2026-100?",
            _checar_val_status_48h,
        ),
        (
            "registrar_escalonamento",
            {"motivo": "cancelamento", "resumo": "Solicita cancelamento.", "protocolo": "NT-0001"},
            "Quero cancelar meu plano (protocolo NT-0001).",
            _checar_val_escalonamento,
        ),
    ],
)
def test_eval_selecao_ferramentas_dominio_val(
    nome_tool: str,
    argumentos: dict[str, Any],
    prompt: str,
    checar_json: Any,
    mock_openai: Any,
    criar_resposta_mock: Any,
    criar_tool_call_mock: Any,
) -> None:
    """EVAL D1.5: Val seleciona KB Nimbus Telecom, status SLA >48h e escalonamento."""
    modulo = agent_core.obter_modulo_perfil("agent-val.md")
    resposta, historico, kwargs_t1, tool_json = _executar_eval_tool(
        modulo,
        mock_openai,
        criar_resposta_mock,
        criar_tool_call_mock,
        prompt,
        nome_tool,
        argumentos,
        "Bom dia, sou a Val, da Nimbus Telecom. Atendimento atualizado.",
    )

    assert any(t["function"]["name"] == nome_tool for t in kwargs_t1["tools"])
    checar_json(tool_json)
    assert historico[-1] == {"role": "assistant", "content": resposta}


@pytest.mark.parametrize(
    "caso",
    [
        "obter_pastas_padrao",
        "listar_arquivos",
        "ler_conteudo_ou_resumo",
        "criar_pasta",
        "mover_arquivo",
    ],
)
def test_eval_selecao_ferramentas_organizador_sandbox(
    caso: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_openai: Any,
    criar_resposta_mock: Any,
    criar_tool_call_mock: Any,
) -> None:
    """EVAL D1.6: Organizador executa todas as 5 ferramentas de arquivo em sandbox hermética."""
    modulo = agent_core.obter_modulo_perfil("agent-organizador.md")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    arq_txt = tmp_path / "nota.txt"
    arq_txt.write_text("Comprovante de pagamento de outubro.", encoding="utf-8")
    pasta_destino = tmp_path / "2025" / "Boletos e Comprovantes" / "10" / "08"

    args_por_caso: dict[str, dict[str, Any]] = {
        "obter_pastas_padrao": {},
        "listar_arquivos": {"diretorio": str(tmp_path)},
        "ler_conteudo_ou_resumo": {"caminho_arquivo": str(arq_txt)},
        "criar_pasta": {"caminho": str(pasta_destino)},
        "mover_arquivo": {"origem": str(arq_txt), "destino": str(pasta_destino)},
    }
    if caso == "mover_arquivo":
        pasta_destino.mkdir(parents=True)

    _, _, kwargs_t1, tool_json = _executar_eval_tool(
        modulo,
        mock_openai,
        criar_resposta_mock,
        criar_tool_call_mock,
        f"Execute a ação {caso} na pasta de trabalho.",
        caso,
        args_por_caso[caso],
        "Operação concluída na sandbox.",
    )

    assert any(t["function"]["name"] == caso for t in kwargs_t1["tools"])
    if caso == "obter_pastas_padrao":
        assert {"downloads", "documentos", "desktop"} <= set(tool_json.keys())
    elif caso == "listar_arquivos":
        assert isinstance(tool_json["arquivos"], list) and tool_json["total_encontrados"] == 1
    elif caso == "ler_conteudo_ou_resumo":
        assert tool_json["tipo"] == "texto" and "Comprovante de pagamento" in tool_json["amostra"]
    elif caso == "criar_pasta":
        assert tool_json["sucesso"] is True and pasta_destino.is_dir()
    else:
        assert tool_json["sucesso"] is True and (pasta_destino / "nota.txt").exists()


# ==============================================================================
# DIMENSÃO 2: STRICT PROFILE TOOL & MEMORY ISOLATION
# ==============================================================================


@pytest.mark.parametrize("perfil", list(PERFIL_SPECS))
def test_eval_isolamento_estrito_ferramentas_por_perfil(
    perfil: str,
    mock_openai: Any,
    criar_resposta_mock: Any,
) -> None:
    """EVAL D2.1: Paridade estrita Markdown == EXECUTORES == payload OpenAI sem vazamentos."""
    modulo = agent_core.obter_modulo_perfil(perfil)
    spec = PERFIL_SPECS[perfil]
    mock_openai.chat.completions.create.return_value = criar_resposta_mock(content="OK.")

    historico: list[dict[str, Any]] = [
        {"role": "system", "content": modulo.carregar_contexto()},
        {"role": "user", "content": "Olá."},
    ]
    agent_core.responder_perfil(perfil, historico)

    kwargs = mock_openai.chat.completions.create.call_args.kwargs
    nomes_payload = {t["function"]["name"] for t in kwargs["tools"]}
    nomes_markdown = _extrair_ferramentas_markdown(modulo.AGENT_MD)

    assert nomes_payload == spec["tools"] == set(modulo.EXECUTORES.keys()) == nomes_markdown
    assert nomes_payload.isdisjoint(TODAS_FERRAMENTAS - spec["tools"])
    if perfil == "agent-organizador.md":
        assert "somar" not in nomes_payload
    else:
        assert "somar" in nomes_payload


@pytest.mark.parametrize("perfil", list(PERFIL_SPECS))
def test_eval_bloqueio_ferramenta_estrangeira_em_runtime(
    perfil: str,
    mock_openai: Any,
    criar_resposta_mock: Any,
    criar_tool_call_mock: Any,
) -> None:
    """EVAL D2.2: Alucinação de ferramenta de outro perfil retorna erro JSON seguro."""
    modulo = agent_core.obter_modulo_perfil(perfil)
    nome_estrangeira, args_estrangeiros = PERFIL_SPECS[perfil]["ferramenta_estrangeira"]

    historico: list[dict[str, Any]] = [
        {"role": "system", "content": modulo.carregar_contexto()},
        {"role": "user", "content": "Execute uma ferramenta fora do seu perfil."},
    ]
    mock_openai.chat.completions.create.side_effect = [
        criar_resposta_mock(
            tool_calls=[criar_tool_call_mock("call_foreign", nome_estrangeira, json.dumps(args_estrangeiros))]
        ),
        criar_resposta_mock(content="Ferramenta indisponível neste perfil."),
    ]

    resposta = agent_core.responder_perfil(perfil, historico)

    assert resposta == "Ferramenta indisponível neste perfil."
    tool_msgs = [m for m in historico if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    erro = json.loads(tool_msgs[0]["content"])
    assert "erro" in erro and "não existe" in erro["erro"]


@pytest.mark.parametrize("perfil", list(PERFIL_SPECS))
def test_eval_isolamento_memoria_por_perfil(perfil: str) -> None:
    """EVAL D2.3: `memory.md` é injetada exclusivamente no Organizador e isolada nos demais."""
    modulo = agent_core.obter_modulo_perfil(perfil)
    spec = PERFIL_SPECS[perfil]

    ctx = modulo.carregar_contexto()
    assert "# Memória" in ctx
    if spec["usa_memory_md"]:
        for marcador in MARCADORES_MEMORIA_ORGANIZADOR:
            assert marcador in ctx
    else:
        assert modulo.MEMORIA_PADRAO in ctx
        for marcador in MARCADORES_MEMORIA_ORGANIZADOR:
            assert marcador not in ctx


# ==============================================================================
# DIMENSÃO 3: PERSONA ADHERENCE WITHOUT SPURIOUS TOOL CALLS
# ==============================================================================


@pytest.mark.parametrize(
    ("perfil", "tipo_prompt", "prompt_usuario", "resposta_esperada"),
    [
        ("agent.md", "saudacao", "Olá, quem é você?", "Sou o assistente base em português."),
        (
            "agent.md",
            "conceitual",
            "Explique brevemente o que é um endpoint REST.",
            "É uma URL que recebe requisições HTTP para um recurso.",
        ),
        (
            "agent-ada.md",
            "pedido_codigo_pronto",
            "Oi Ada, me dê o código pronto do exercício de fatorial!",
            "Posso te guiar até lá. O que precisa acontecer em cada repetição do cálculo?",
        ),
        (
            "agent-ada.md",
            "conceitual",
            "Qual a diferença conceitual entre for e while?",
            "Você já usou `for` quando sabe quantas repetições quer; quando acha que `while` faz mais sentido?",
        ),
        (
            "agent-lint.md",
            "identidade",
            "Quem é você e como funciona sua revisão?",
            "Sou o Lint. Aponto o veredito primeiro e listo achados por gravidade.",
        ),
        (
            "agent-lint.md",
            "decisao_tecnica",
            "Vale a pena usar variável global para cache em API?",
            "Não para API concorrente: gera corrida entre requisições e vaza estado entre testes.",
        ),
        (
            "agent-val.md",
            "saudacao",
            "Bom dia, quem está me atendendo?",
            "Bom dia, sou a Val, do atendimento da Nimbus Telecom. Como posso ajudar?",
        ),
        (
            "agent-val.md",
            "fora_de_escopo",
            "Vocês vendem chip de celular ou têm receita de bolo?",
            "Atendo apenas internet fixa da Nimbus Telecom. Para telefonia móvel, procure uma operadora móvel.",
        ),
        (
            "agent-organizador.md",
            "identidade",
            "Quem é você e o que você faz?",
            "Sou o Org, especialista em organizar arquivos em Downloads, Documentos e Desktop.",
        ),
        (
            "agent-organizador.md",
            "conceitual",
            "Como funciona a hierarquia de pastas que você adota?",
            "Sigo a estrutura [Ano]/[Categoria]/[Mês]/[Dia] antes de mover qualquer arquivo.",
        ),
    ],
)
def test_eval_aderencia_persona_sem_tools_spurious(
    perfil: str,
    tipo_prompt: str,
    prompt_usuario: str,
    resposta_esperada: str,
    mock_openai: Any,
    criar_resposta_mock: Any,
) -> None:
    """EVAL D3.1: Saudações, dúvidas conceituais e fora de escopo não acionam tools (`tools == []`)."""
    assert tipo_prompt
    modulo = agent_core.obter_modulo_perfil(perfil)
    spec = PERFIL_SPECS[perfil]
    mock_openai.chat.completions.create.return_value = criar_resposta_mock(content=resposta_esperada)

    historico: list[dict[str, Any]] = [
        {"role": "system", "content": modulo.carregar_contexto()},
        {"role": "user", "content": prompt_usuario},
    ]
    resposta = agent_core.responder_perfil(perfil, historico)

    assert mock_openai.chat.completions.create.call_count == 1
    system_prompt = mock_openai.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    for marcador in spec["marcadores_persona"]:
        assert marcador in system_prompt
    tools_chamadas = [m for m in historico if m.get("role") == "tool"]
    assert tools_chamadas == []
    assert historico[-1] == {"role": "assistant", "content": resposta}
    assert len(resposta.strip()) > 0


def test_eval_contrato_guardrails_especificos_persona() -> None:
    """EVAL D3.2: Invariantes críticos de guardrails (Ada, Lint, Val, Org e Base)."""
    ctx_ada = agent_ada.carregar_contexto()
    assert "Nunca dê o código pronto de um exercício." in ctx_ada
    res_ada = agent_ada.analisar_logica_codigo("x = 0\nwhile x < 5:\n    print(x)")
    assert len(res_ada["perguntas_guia"]) >= 1
    assert "x += 1" not in " ".join(res_ada["perguntas_guia"])

    ctx_lint = agent_lint.carregar_contexto()
    assert "Conclusão primeiro." in ctx_lint and "ordenados por gravidade" in ctx_lint
    res_lint = agent_lint.detectar_antipadroes_python("import os\ndef f(x):\n    return eval('1')\n")
    ordem = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}
    niveis = [ordem[item["gravidade"]] for item in res_lint["achados"]]
    assert niveis == sorted(niveis) and res_lint["achados"][0]["gravidade"] == "alta"
    assert agent_lint.detectar_antipadroes_python("def ok(x: int) -> int:\n    return x + 1\n")["achados"] == []

    ctx_val = agent_val.carregar_contexto()
    assert "Não peça dados sensíveis." in ctx_val
    assert "Nunca prometa prazo, desconto, isenção ou reembolso." in ctx_val
    res_val = agent_val.registrar_escalonamento(
        "cancelamento",
        "Cliente enviou senha: 123456, cvv 999 e foto do rg.",
        "NT-0001",
    )
    assert res_val["dado_sensivel_removido"] is True
    assert res_val["promessa_sla_ou_desconto"] is False
    assert "123456" not in res_val["resumo"] and "999" not in res_val["resumo"]

    ctx_org = agent_core.obter_modulo_perfil("agent-organizador.md").carregar_contexto()
    assert "[Ano]/[Categoria]/[Mês]/[Dia]" in ctx_org
    assert "Nunca sobrescreva ou apague arquivos do usuário." in ctx_org

    ctx_base = agent_core.obter_modulo_perfil("agent.md").carregar_contexto()
    assert "Direto ao ponto." in ctx_base and "Não invente." in ctx_base


# ==============================================================================
# DIMENSÃO 4: CIRCUIT BREAKER RESILIENCE (`MAX_ITERACOES`)
# ==============================================================================


@pytest.mark.parametrize("perfil", list(PERFIL_SPECS))
def test_eval_circuit_breaker_direto_modulo(
    perfil: str,
    mock_openai: Any,
    monkeypatch: pytest.MonkeyPatch,
    criar_resposta_mock: Any,
    criar_tool_call_mock: Any,
) -> None:
    """EVAL D4.1: Loop infinito direto em `<modulo>.responder()` para em `agent_core.MAX_ITERACOES`."""
    limite = 3
    monkeypatch.setattr(agent_core, "MAX_ITERACOES", limite)
    modulo = agent_core.obter_modulo_perfil(perfil)
    nome_tool, args_tool = PERFIL_SPECS[perfil]["tool_segura_loop"]
    monkeypatch.setitem(modulo.EXECUTORES, nome_tool, lambda **_kw: {"status": "loop_eval"})

    mock_openai.chat.completions.create.return_value = criar_resposta_mock(
        tool_calls=[criar_tool_call_mock("loop_1", nome_tool, json.dumps(args_tool))]
    )
    historico: list[dict[str, Any]] = [
        {"role": "system", "content": modulo.carregar_contexto()},
        {"role": "user", "content": "Execute em loop eterno."},
    ]

    resposta = modulo.responder(historico)

    assert mock_openai.chat.completions.create.call_count == limite
    assert len([m for m in historico if m.get("role") == "tool"]) == limite
    assert "limite de iterações sem concluir" in resposta.lower()
    assert "reformular" in resposta.lower()


@pytest.mark.parametrize("perfil", list(PERFIL_SPECS))
def test_eval_circuit_breaker_via_responder_perfil(
    perfil: str,
    mock_openai: Any,
    monkeypatch: pytest.MonkeyPatch,
    criar_resposta_mock: Any,
    criar_tool_call_mock: Any,
) -> None:
    """EVAL D4.2: Loop infinito via `agent_core.responder_perfil()` respeita `agent.MAX_ITERACOES`."""
    limite = 2
    monkeypatch.setattr(agent, "MAX_ITERACOES", limite)
    modulo = agent_core.obter_modulo_perfil(perfil)
    nome_tool, args_tool = PERFIL_SPECS[perfil]["tool_segura_loop"]
    monkeypatch.setitem(modulo.EXECUTORES, nome_tool, lambda **_kw: {"status": "loop_eval"})

    mock_openai.chat.completions.create.return_value = criar_resposta_mock(
        tool_calls=[criar_tool_call_mock("loop_2", nome_tool, json.dumps(args_tool))]
    )
    historico: list[dict[str, Any]] = [
        {"role": "system", "content": modulo.carregar_contexto()},
        {"role": "user", "content": "Execute em loop eterno."},
    ]

    resposta = agent_core.responder_perfil(perfil, historico)

    assert mock_openai.chat.completions.create.call_count == limite
    assert resposta == "Atingi o limite de iterações sem concluir. Tente reformular o pedido."
