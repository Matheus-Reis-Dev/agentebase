"""Tier 5 E2E: Hardening Adversarial Caixa-Branca (Core, Base, Organizador, Facade, UI, Ada, Lint, Val)."""

from __future__ import annotations

import ast
import builtins
import json
from pathlib import Path
import runpy
import sys
from unittest.mock import MagicMock

import docx
import openpyxl
import pypdf
import pytest

import agent
import agent_core
import agent_organizador
from tests.e2e.conftest import (
    APP_PATH,
    criar_mock_resposta_texto,
    importar_modulo,
)


# ==============================================================================
# 1. CORE, ORGANIZER, FACADE & UI — Cobertura caixa-branca e regressões
# ==============================================================================


def test_t5_core_get_cliente_instancia_singleton_em_agent_e_base_url(monkeypatch):
    """Cobre criação lazy em `agent._cliente` e suporte a `OPENAI_BASE_URL`."""
    chamadas_openai = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            chamadas_openai.append(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-t5")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.exemplo.local/v1")
    monkeypatch.setattr(agent, "_cliente", None)
    monkeypatch.setattr(agent_core, "_cliente", None)
    monkeypatch.setattr(agent_core, "OpenAI", FakeOpenAI)

    cli1 = agent_core.get_cliente()
    cli2 = agent_core.get_cliente()

    assert cli1 is cli2
    assert agent._cliente is cli1
    assert chamadas_openai == [
        {"api_key": "sk-test-t5", "base_url": "https://api.exemplo.local/v1"}
    ]


def test_t5_core_get_cliente_standalone_sem_modulo_agent(monkeypatch):
    """Cobre fallback singleton de `agent_core._cliente` quando `agent` não está em `sys.modules`."""
    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setenv("OPENAI_API_KEY", "sk-standalone")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setattr(agent_core, "_cliente", None)
    monkeypatch.setattr(agent_core, "OpenAI", FakeOpenAI)
    monkeypatch.delitem(sys.modules, "agent", raising=False)

    cli1 = agent_core.get_cliente()
    cli2 = agent_core.get_cliente()

    assert cli1 is cli2
    assert agent_core._cliente is cli1
    assert cli1.kwargs == {"api_key": "sk-standalone"}


@pytest.mark.parametrize("valor_str", ["nan", "NaN", "inf", "-inf", "  +Infinity  "])
def test_t5_core_somar_rejeita_strings_nao_finitas(valor_str):
    """Cobre rejeição de strings não finitas (`nan`, `inf`, `-inf`) em `_converter_numero`."""
    res = agent_core.somar(valor_str, 1)
    assert "erro" in res
    assert "finito" in res["erro"]


def test_t5_core_loop_verboso_e_argumentos_json_nao_dict(capsys):
    """Cobre `verboso=True` e JSON válido não-objeto (`null`) em `tool_calls`."""
    tc_null = MagicMock()
    tc_null.id = "call_null"
    tc_null.function.name = "somar"
    tc_null.function.arguments = "null"

    resp_1 = MagicMock()
    resp_1.choices[0].message.content = None
    resp_1.choices[0].message.tool_calls = [tc_null]
    resp_1.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "tool_calls": [
            {"id": "call_null", "function": {"name": "somar", "arguments": "null"}}
        ],
    }

    resp_2 = criar_mock_resposta_texto("Finalizado")
    cliente = MagicMock()
    cliente.chat.completions.create.side_effect = [resp_1, resp_2]
    mensagens = [{"role": "user", "content": "Teste verboso"}]

    saida = agent_core.executar_loop_react(
        mensagens,
        [agent_core.SOMAR_TOOL_SCHEMA],
        {"somar": agent_core.somar},
        cliente=cliente,
        verboso=True,
    )

    assert saida == "Finalizado"
    stdout = capsys.readouterr().out
    assert "[ferramenta] somar(None)" in stdout
    tool_msg = next(m for m in mensagens if m.get("role") == "tool")
    assert "erro" in json.loads(tool_msg["content"])


def test_t5_org_ler_conteudo_pdf_valido_truncado_e_corrompido(monkeypatch, tmp_path):
    """Cobre `_ler_pdf` com PDF real multipágina (truncamento/break) e PDF corrompido."""
    pdf_ok = tmp_path / "valido.pdf"
    writer = pypdf.PdfWriter()
    for _ in range(4):
        writer.add_blank_page(width=72, height=72)
    with open(pdf_ok, "wb") as fh:
        writer.write(fh)

    res_ok = agent_organizador.ler_conteudo_ou_resumo(str(pdf_ok), limite_caracteres=50)
    assert res_ok["tipo"] == "pdf"
    assert res_ok["total_paginas"] == 4
    assert isinstance(res_ok["amostra"], str)

    pagina_mock = MagicMock()
    pagina_mock.extract_text.return_value = "ConteudoExtensoDePagina" * 3
    leitor_mock = MagicMock()
    leitor_mock.pages = [pagina_mock, pagina_mock, pagina_mock]
    with monkeypatch.context() as m:
        m.setattr(pypdf, "PdfReader", lambda _path: leitor_mock)
        res_trunc = agent_organizador.ler_conteudo_ou_resumo(str(pdf_ok), limite_caracteres=20)
        assert res_trunc["tipo"] == "pdf"
        assert res_trunc["total_paginas"] == 3
        assert len(res_trunc["amostra"]) == 20
        assert pagina_mock.extract_text.call_count == 1

    pdf_bad = tmp_path / "corrompido.pdf"
    pdf_bad.write_bytes(b"%PDF-corrompido")
    res_bad = agent_organizador.ler_conteudo_ou_resumo(str(pdf_bad))
    assert "aviso" in res_bad
    assert "Falha ao ler PDF" in res_bad["aviso"]


def test_t5_org_ler_conteudo_docx_valido_e_corrompido(tmp_path):
    """Cobre `_ler_docx` com documento Word válido e arquivo `.docx` corrompido."""
    docx_ok = tmp_path / "contrato.docx"
    documento = docx.Document()
    documento.add_paragraph("   ")
    documento.add_paragraph("Contrato de Prestação de Serviços 2026")
    documento.add_paragraph("Cláusula segunda com detalhes adicionais.")
    documento.save(str(docx_ok))

    res_ok = agent_organizador.ler_conteudo_ou_resumo(str(docx_ok), limite_caracteres=30)
    assert res_ok["tipo"] == "docx"
    assert res_ok["amostra"] == "Contrato de Prestação de Servi"

    docx_bad = tmp_path / "corrompido.docx"
    docx_bad.write_bytes(b"nao-e-zip-docx")
    res_bad = agent_organizador.ler_conteudo_ou_resumo(str(docx_bad))
    assert "aviso" in res_bad
    assert "Falha ao ler DOCX" in res_bad["aviso"]


def test_t5_org_ler_conteudo_xlsx_valido_com_abas_e_celulas(tmp_path):
    """Cobre caminho feliz de `_ler_xlsx` extraindo abas e linhas formatadas."""
    xlsx_ok = tmp_path / "financeiro.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resumo"
    ws.append(["Categoria", None, "Valor"])
    ws.append(["Internet", None, 129.9])
    wb.create_sheet("Detalhes")
    wb.save(str(xlsx_ok))
    wb.close()

    res = agent_organizador.ler_conteudo_ou_resumo(str(xlsx_ok), limite_caracteres=200)
    assert res["tipo"] == "xlsx"
    assert res["planilhas"] == ["Resumo", "Detalhes"]
    assert "Categoria | Valor" in res["amostra"]
    assert "Internet | 129.9" in res["amostra"]


def test_t5_org_ler_texto_erro_io_retorna_erro_estruturado(monkeypatch, tmp_path):
    """Cobre fallback `except Exception` em `_ler_texto` quando a leitura falha."""
    txt = tmp_path / "bloqueado.txt"
    txt.write_text("segredo", encoding="utf-8")

    def falhar_leitura(self, *args, **kwargs):
        raise PermissionError("Acesso negado simulado")

    monkeypatch.setattr(Path, "read_text", falhar_leitura)
    res = agent_organizador.ler_conteudo_ou_resumo(str(txt))
    assert "erro" in res
    assert "Não foi possível ler texto puro" in res["erro"]


def test_t5_org_mover_pasta_e_renomear_arquivo(tmp_path):
    """Cobre `mover_arquivo` para diretório (`src.is_dir()`) e destino com nome explícito."""
    pasta_origem = tmp_path / "lote_fotos"
    pasta_origem.mkdir()
    (pasta_origem / "img.jpg").write_bytes(b"jpg")
    destino_pai = tmp_path / "2026" / "Fotos"

    res_dir = agent_organizador.mover_arquivo(str(pasta_origem), str(destino_pai))
    assert res_dir["sucesso"] is True
    assert not pasta_origem.exists()
    assert (destino_pai / "lote_fotos" / "img.jpg").is_file()

    arq_origem = tmp_path / "rascunho.txt"
    arq_origem.write_text("conteudo", encoding="utf-8")
    destino_arquivo = tmp_path / "arquivo_final" / "documento_renomeado.txt"

    res_arq = agent_organizador.mover_arquivo(str(arq_origem), str(destino_arquivo))
    assert res_arq["sucesso"] is True
    assert not arq_origem.exists()
    assert destino_arquivo.is_file()


def test_t5_org_mover_arquivo_nao_sobrescreve_nem_move_pasta_para_si(tmp_path):
    """Regressão Bug 1: `mover_arquivo` recusa sobrescrita, mesmo caminho e pasta dentro de si."""
    src = tmp_path / "fatura.pdf"
    src.write_text("novo", encoding="utf-8")
    dst_dir = tmp_path / "destino"
    dst_dir.mkdir()
    existente = dst_dir / "fatura.pdf"
    existente.write_text("original", encoding="utf-8")

    res_colisao = agent_organizador.mover_arquivo(str(src), str(dst_dir))
    assert "erro" in res_colisao
    assert src.is_file()
    assert existente.read_text(encoding="utf-8") == "original"

    res_mesmo = agent_organizador.mover_arquivo(str(src), str(tmp_path))
    assert "erro" in res_mesmo
    assert src.is_file()

    pasta = tmp_path / "pasta"
    pasta.mkdir()
    res_loop = agent_organizador.mover_arquivo(str(pasta), str(pasta / "sub"))
    assert "erro" in res_loop
    assert pasta.is_dir()
    assert not (pasta / "sub").exists()


@pytest.mark.parametrize("origem_invalida", ["", "   ", ".", "./", None])
def test_t5_org_mover_arquivo_rejeita_origem_vazia_ou_ponto(tmp_path, monkeypatch, origem_invalida):
    """Regressão T5-ORG-1: `origem` vazia/`.`/`None` é rejeitada sem mutar CWD nem criar destino."""
    cwd = tmp_path / "sandbox_cwd"
    cwd.mkdir()
    (cwd / "important.txt").write_text("stay", encoding="utf-8")
    outside_dst = tmp_path / "outside_target"
    monkeypatch.chdir(cwd)

    res = agent_organizador.mover_arquivo(origem_invalida, str(outside_dst))  # type: ignore[arg-type]
    assert "erro" in res
    assert not outside_dst.exists()
    assert (cwd / "important.txt").read_text(encoding="utf-8") == "stay"


@pytest.mark.parametrize("destino_invalido", ["", "   ", None])
def test_t5_org_mover_arquivo_rejeita_destino_vazio(tmp_path, monkeypatch, destino_invalido):
    """Regressão T5-ORG-1: `destino` vazio/`None` é rejeitado sem mover arquivo para o CWD."""
    cwd = tmp_path / "sandbox_cwd"
    cwd.mkdir()
    src = tmp_path / "origem.txt"
    src.write_text("conteudo", encoding="utf-8")
    monkeypatch.chdir(cwd)

    res = agent_organizador.mover_arquivo(str(src), destino_invalido)  # type: ignore[arg-type]
    assert "erro" in res
    assert src.is_file()
    assert not (cwd / "origem.txt").exists()


@pytest.mark.parametrize("origem_parent", ["..", "../", "sub/..", "a/../..", " .. "])
def test_t5_org_mover_arquivo_rejeita_origem_parent_traversal(tmp_path, monkeypatch, origem_parent):
    """Regressão T5-ORG-3: `origem` com `..` (ou `' .. '`) é rejeitada sem criar destino."""
    sandbox = tmp_path / "sandbox"
    sub = sandbox / "sub"
    (sub / "a").mkdir(parents=True)
    keep = sandbox / "keep.txt"
    keep.write_text("stay", encoding="utf-8")
    deep = tmp_path / "nonexistent_a" / "nonexistent_b"
    monkeypatch.chdir(sub)

    res = agent_organizador.mover_arquivo(origem_parent, str(deep))
    assert "erro" in res
    assert not (tmp_path / "nonexistent_a").exists()
    assert keep.read_text(encoding="utf-8") == "stay"

    res_trailing = agent_organizador.mover_arquivo(origem_parent, f"{deep}/")
    assert "erro" in res_trailing
    assert not (tmp_path / "nonexistent_a").exists()


def test_t5_org_mover_arquivo_normaliza_espacos_origem_e_destino(tmp_path):
    """Regressão T5-ORG-3: espaços laterais em `origem` e `destino` válidos são normalizados."""
    src = tmp_path / "nota.txt"
    src.write_text("ok", encoding="utf-8")
    dst_dir = tmp_path / "destino_limpo"

    res = agent_organizador.mover_arquivo(f"  {src}  ", f"  {dst_dir}  ")
    assert res["sucesso"] is True
    assert not src.exists()
    assert (dst_dir / "nota.txt").read_text(encoding="utf-8") == "ok"


def test_t5_org_mover_arquivo_rejeita_arquivo_existente_ancestro_e_symlink_quebrado(tmp_path, monkeypatch):
    """Regressão T5-ORG-2: arquivo sem extensão, ancestral arquivo e symlink quebrado retornam `erro`."""
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    blocker = tmp_path / "existing_file"
    blocker.write_text("blocker", encoding="utf-8")

    res_extless = agent_organizador.mover_arquivo(str(src), str(blocker))
    assert "erro" in res_extless
    assert src.is_file()
    assert blocker.read_text(encoding="utf-8") == "blocker"

    res_trailing = agent_organizador.mover_arquivo(str(src), f"{blocker}/")
    assert "erro" in res_trailing
    assert src.is_file()

    res_nested = agent_organizador.mover_arquivo(str(src), str(blocker / "sub" / "b.txt"))
    assert "erro" in res_nested
    assert src.is_file()

    pasta = tmp_path / "minha_pasta"
    pasta.mkdir()
    blocker_txt = tmp_path / "blocker.txt"
    blocker_txt.write_text("x", encoding="utf-8")
    res_dir = agent_organizador.mover_arquivo(str(pasta), str(blocker_txt))
    assert "erro" in res_dir
    assert pasta.is_dir()

    symlink_quebrado = tmp_path / "atalho_quebrado.txt"
    pasta_dst = tmp_path / "pasta_dst"
    pasta_dst.mkdir()
    symlink_em_dir = pasta_dst / src.name
    orig_is_symlink = Path.is_symlink

    def fake_is_symlink(self: Path) -> bool:
        if self in (symlink_quebrado, symlink_em_dir):
            return True
        return orig_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    res_sym_direto = agent_organizador.mover_arquivo(str(src), str(symlink_quebrado))
    assert "erro" in res_sym_direto
    assert "sobrescrito" in res_sym_direto["erro"]
    assert src.is_file()

    res_sym_dir = agent_organizador.mover_arquivo(str(src), str(pasta_dst))
    assert "erro" in res_sym_dir
    assert "sobrescrito" in res_sym_dir["erro"]
    assert src.is_file()

    destino_valido = tmp_path / "destino_valido" / "movido.txt"
    res_ok = agent_organizador.mover_arquivo(str(src), str(destino_valido))
    assert res_ok["sucesso"] is True
    assert destino_valido.is_file()


def test_t5_org_ler_conteudo_limite_negativo_nao_vaza_arquivo_inteiro(tmp_path):
    """Regressão Bug 2: `limite_caracteres <= 0` retorna amostra vazia (proteção FinOps)."""
    txt = tmp_path / "grande.txt"
    txt.write_text("0123456789ABCDEF", encoding="utf-8")

    res = agent_organizador.ler_conteudo_ou_resumo(str(txt), limite_caracteres=-1)
    assert res["tipo"] == "texto"
    assert res["amostra"] == ""


def test_t5_org_listar_arquivos_inclui_subpasta_nao_anual(tmp_path):
    """Cobre listagem de subdiretório comum (não-4-dígitos) com `tipo == 'pasta'`."""
    (tmp_path / "2025").mkdir()
    (tmp_path / "projetos").mkdir()

    res = agent_organizador.listar_arquivos(str(tmp_path))
    assert res["total_encontrados"] == 1
    assert res["arquivos"][0]["nome"] == "projetos"
    assert res["arquivos"][0]["tipo"] == "pasta"
    assert res["arquivos"][0]["tamanho_kb"] == 0.0


def test_t5_agent_main_sem_api_key_encerra_com_exit_1(monkeypatch, capsys):
    """Cobre `agent.main()` abortando com código 1 quando falta `OPENAI_API_KEY`."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(agent, "_cliente", None)

    with pytest.raises(SystemExit) as exc:
        agent.main()

    assert exc.value.code == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().out


@pytest.mark.parametrize("excecao_interrupcao", [KeyboardInterrupt(), EOFError()])
def test_t5_agent_main_entrada_vazia_e_interrupcao(
    monkeypatch, mock_openai, capsys, excecao_interrupcao
):
    """Cobre `continue` em entrada vazia e saída limpa em `KeyboardInterrupt` / `EOFError`."""
    monkeypatch.setenv("AGENTE_PERFIL", "")
    eventos = iter(["   ", excecao_interrupcao])

    def fake_input(_prompt=""):
        item = next(eventos)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(builtins, "input", fake_input)
    agent.main()

    saida = capsys.readouterr().out
    assert "Até logo!" in saida
    assert mock_openai.chat.completions.create.call_count == 0


def test_t5_agent_main_recupera_erro_de_api_sem_cair(monkeypatch, mock_openai, capsys):
    """Regressão Bug 3: erro transitório em `fn_responder` não derruba `main()` e faz rollback."""
    monkeypatch.setenv("AGENTE_PERFIL", "")
    snapshots_payload = []

    def fake_create(**kwargs):
        snapshots_payload.append([dict(m) for m in kwargs["messages"]])
        if len(snapshots_payload) == 1:
            raise RuntimeError("Erro 503 temporário")
        return criar_mock_resposta_texto("Recuperado")

    mock_openai.chat.completions.create.side_effect = fake_create
    entradas = iter(["Primeira pergunta", "Segunda pergunta", "sair"])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(entradas))

    agent.main()
    saida = capsys.readouterr().out
    assert "Erro 503 temporário" in saida
    assert "Recuperado" in saida
    assert len(snapshots_payload) == 2
    assert [m["content"] for m in snapshots_payload[0] if m["role"] == "user"] == ["Primeira pergunta"]
    assert [m["content"] for m in snapshots_payload[1] if m["role"] == "user"] == ["Segunda pergunta"]


def test_t5_agent_entrypoint_module_main(monkeypatch, mock_openai, capsys):
    """Cobre execução via `python -m agent` (`if __name__ == '__main__': main()`)."""
    entradas = iter(["quit"])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(entradas))
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")

    runpy.run_module("agent", run_name="__main__")
    assert "Até logo!" in capsys.readouterr().out


def test_t5_ui_aviso_fallback_quando_perfil_indisponivel(
    monkeypatch, e2e_app_factory, e2e_cliente_mock
):
    """Cobre `_resolver_modulo_perfil` com `ImportError` exibindo `st.warning` e fallback seguro."""
    e2e_cliente_mock.chat.completions.create.return_value = criar_mock_resposta_texto("Fallback OK")
    orig_obter = agent_core.obter_modulo_perfil

    def obter_com_falha(perfil):
        if perfil == "agent-val.md":
            raise ImportError("módulo Val indisponível")
        return orig_obter(perfil)

    monkeypatch.setattr(agent_core, "obter_modulo_perfil", obter_com_falha)

    at = e2e_app_factory().run()
    at.sidebar.selectbox[0].set_value("Val (agent-val.md)").run()

    assert len(at.warning) == 1
    assert "indisponível" in at.warning[0].value
    assert at.session_state["perfil_ativo"] == "Padrão (agent.py)"

    at.sidebar.selectbox[0].set_value("Ada (agent-ada.md)").run()
    assert at.session_state["perfil_ativo"] == "Ada (agent-ada.md)"


def test_t5_ui_troca_de_perfil_e_nova_conversa_preserva_perfil_ativo(
    e2e_app_factory, e2e_cliente_mock
):
    """Cobre troca de perfil limpando `tela` e `Nova conversa` preservando perfil Ada."""
    e2e_cliente_mock.chat.completions.create.return_value = criar_mock_resposta_texto("OK")
    at = e2e_app_factory().run()

    at.sidebar.selectbox[0].set_value("Ada (agent-ada.md)").run()
    assert "Ada" in at.session_state["mensagens"][0]["content"]

    at.chat_input[0].set_value("Oi Ada").run()
    assert len(at.session_state["tela"]) == 2

    btn_nova = [b for b in at.button if b.label == "Nova conversa"][0]
    btn_nova.click().run()
    assert at.session_state["tela"] == []
    assert "Ada" in at.session_state["mensagens"][0]["content"]

    at.sidebar.selectbox[0].set_value("Lint (agent-lint.md)").run()
    assert "Lint" in at.session_state["mensagens"][0]["content"]
    assert at.session_state["tela"] == []


def test_t5_ui_execucao_direta_sem_streamlit_runtime_sai_com_erro(capsys):
    """Cobre guarda `if not st_runtime_ativo(): raise SystemExit(1)` em `app.py`."""
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(APP_PATH, run_name="__main__")

    assert exc.value.code == 1
    saida = capsys.readouterr().out
    assert "streamlit run app.py" in saida


# ==============================================================================
# 2. ADA — Cobertura de ramos AST & regressões de escopo `while`
# ==============================================================================


def test_t5_ada_while_com_atualizacao_e_break_nao_gera_falso_positivo():
    """Cobre Tuple/List target, Assign, AugAssign, For e Break em `_nomes_modificados_no_bloco`."""
    mod = importar_modulo("agent_ada")
    codigo = (
        "a, b = 0, 1\n"
        "[c, d] = [1, 2]\n"
        "obj.x = 1\n"
        "while a < 5:\n"
        "    a = a + 1\n"
        "    b += 1\n"
        "    for k in range(2):\n"
        "        pass\n"
        "    if a == 3:\n"
        "        break\n"
    )
    res = mod.analisar_logica_codigo(codigo)
    assert res["analisavel"] is True
    assert not any("while" in obs.lower() for obs in res["observacoes_logicas"])
    assert {"a", "b", "c", "d", "k"}.issubset(set(res["resumo_estrutural"]["variaveis"]))


def test_t5_ada_while_true_com_return_em_def_interna_ainda_alerta():
    """Cobre `_tem_saida_laco` ignorando `_ESCOPOS_ISOLADOS` (`def` aninhada)."""
    mod = importar_modulo("agent_ada")
    codigo = (
        "while True:\n"
        "    def inner():\n"
        "        return 1\n"
        "    inner()\n"
    )
    res = mod.analisar_logica_codigo(codigo)
    assert res["analisavel"] is True
    assert any("while" in obs.lower() for obs in res["observacoes_logicas"])


def test_t5_ada_async_recursiva_sem_caso_base_alerta():
    """Garante detecção de recursão sem caso base em `async def`."""
    mod = importar_modulo("agent_ada")
    codigo = "async def poll(n):\n    return await poll(n - 1)\n"
    res = mod.analisar_logica_codigo(codigo)
    assert res["resumo_estrutural"]["recursao_detectada"] == ["poll"]
    assert any("caso base" in obs.lower() for obs in res["observacoes_logicas"])


def test_t5_ada_verificar_sintaxe_trata_value_error_ast_parse(monkeypatch):
    """Cobre `except ValueError:` (disparado por null bytes no Python 3.10)."""
    mod = importar_modulo("agent_ada")

    def _falha_value_error(_codigo):
        raise ValueError("source code string cannot contain null bytes")

    monkeypatch.setattr(ast, "parse", _falha_value_error)
    res = mod.verificar_sintaxe_python("x = 1")
    assert res["sintaxe_valida"] is False
    assert res["tipo_erro"] == "ValueError"


def test_t5_ada_while_break_interno_nao_mascara_laco_externo_sem_atualizacao():
    """BUG-ADA-1: `break` em laço `for` interno não encerra o `while` externo."""
    mod = importar_modulo("agent_ada")
    codigo = "i = 0\nwhile i < 5:\n    for j in range(3):\n        break\n"
    res = mod.analisar_logica_codigo(codigo)
    assert any("while" in obs.lower() for obs in res["observacoes_logicas"])


def test_t5_ada_while_assign_em_def_interna_nao_mascara_laco_externo():
    """BUG-ADA-1: atribuição em `def` interna não atualiza a condição do `while` externo."""
    mod = importar_modulo("agent_ada")
    codigo = (
        "i = 0\n"
        "while i < 5:\n"
        "    def helper():\n"
        "        i = 10\n"
        "    helper()\n"
    )
    res = mod.analisar_logica_codigo(codigo)
    assert any("while" in obs.lower() for obs in res["observacoes_logicas"])


def test_t5_ada_while_com_return_direto_walrus_e_call_func_nao_geram_falso_positivo():
    """BUG-ADA-2: `while` com `return`, `NamedExpr` (`:=`) ou chamada `len(...)` trata nomes corretamente."""
    mod = importar_modulo("agent_ada")
    res_ret = mod.analisar_logica_codigo("def f(i):\n    while i < 5:\n        return i\n")
    assert not any("while" in obs.lower() for obs in res_ret["observacoes_logicas"])

    res_walrus = mod.analisar_logica_codigo("while (line := input()) != '':\n    print(line)\n")
    assert not any("while" in obs.lower() for obs in res_walrus["observacoes_logicas"])
    assert "line" in res_walrus["resumo_estrutural"]["variaveis"]

    res_len = mod.analisar_logica_codigo("fila = [1, 2]\nwhile len(fila) > 0:\n    print(fila)\n")
    obs_while = [o for o in res_len["observacoes_logicas"] if "while" in o.lower()]
    assert obs_while and "len" not in obs_while[0]


@pytest.mark.parametrize(
    "codigo",
    [
        "items = [1, 2, 3]\nwhile items:\n    head, *items = items\n",
        "estado = {'i': 0}\nwhile estado['i'] < 5:\n    estado['i'] += 1\n",
        "while obj.ativo:\n    obj.ativo = False\n",
        "fila = [1, 2]\nwhile len(fila) > 0:\n    fila.pop()\n",
        "i = 0\nwhile i < 5:\n    for j in range(3):\n        pass\n    else:\n        break\n",
        "while True:\n    for j in range(3):\n        pass\n    else:\n        break\n",
        "i = 0\nwhile i < 5:\n    with ctx() as i:\n        pass\n",
        "async def f(ctx):\n    i = 0\n    while i < 5:\n        async with ctx() as i:\n            pass\n",
        "i = 0\nwhile i < 5:\n    i: int = i + 1\n",
    ],
)
def test_t5_ada_while_alvos_compostos_with_orelse_e_metodos_mutacao_sem_falso_positivo(codigo):
    """Regressão T5-ADA-1: `Starred`, `Subscript`, `Attribute`, `pop()`, `for...else: break` e `with`."""
    mod = importar_modulo("agent_ada")
    res = mod.analisar_logica_codigo(codigo)
    assert res["analisavel"] is True
    assert not any("while" in obs.lower() for obs in res["observacoes_logicas"])


def test_t5_ada_while_annassign_sem_valor_e_with_sem_as_ainda_alertam():
    """Regressão T5-ADA-2: `i: int`, `with ctx():` e `fabrica().x = 1` não atualizam `while`."""
    mod = importar_modulo("agent_ada")
    res_ann = mod.analisar_logica_codigo("i = 0\nwhile i < 5:\n    i: int\n    print(i)\n")
    assert any("while" in obs.lower() for obs in res_ann["observacoes_logicas"])

    res_with = mod.analisar_logica_codigo("i = 0\nwhile i < 5:\n    with ctx():\n        pass\n")
    assert any("while" in obs.lower() for obs in res_with["observacoes_logicas"])

    res_call_attr = mod.analisar_logica_codigo("i = 0\nwhile i < 5:\n    fabrica().x = 1\n")
    assert any("while" in obs.lower() for obs in res_call_attr["observacoes_logicas"])


@pytest.mark.parametrize(
    "codigo",
    [
        "visto = set()\nwhile len(visto) < 5:\n    visto.add(1)\n",
        "xs = []\nwhile len(xs) < 3:\n    xs.insert(0, 1)\n",
        "while fila:\n    fila.popleft()\n",
        "d = {'a': 1}\nwhile d:\n    d.popitem()\n",
        "d = {}\nwhile len(d) < 2:\n    d.setdefault('k', 1)\n",
        "xs = [2, 1]\nwhile xs != [1, 2]:\n    xs.sort()\n",
        "xs = [1, 2]\nwhile xs != [2, 1]:\n    xs.reverse()\n",
        "items = [1, 2, 3]\nwhile items:\n    del items[0]\n",
        "erro = None\nwhile erro is None:\n    try:\n        f()\n    except ValueError as erro:\n        pass\n",
    ],
)
def test_t5_ada_while_metodos_mutacao_delete_e_except_as_sem_falso_positivo(codigo):
    """Regressão T5-ADA-3: `add`/`insert`/`popleft`/`popitem`/`del`/`except as` não geram falso positivo."""
    mod = importar_modulo("agent_ada")
    res = mod.analisar_logica_codigo(codigo)
    assert res["analisavel"] is True
    assert not any("while" in obs.lower() for obs in res["observacoes_logicas"])


def test_t5_ada_while_except_sem_alias_ainda_alerta():
    """Regressão T5-ADA-3: `except ValueError:` sem `as` não atualiza variável de condição."""
    mod = importar_modulo("agent_ada")
    codigo = (
        "erro = None\n"
        "while erro is None:\n"
        "    try:\n"
        "        f()\n"
        "    except ValueError:\n"
        "        pass\n"
    )
    res = mod.analisar_logica_codigo(codigo)
    assert any("while" in obs.lower() for obs in res["observacoes_logicas"])


@pytest.mark.parametrize(
    "codigo",
    [
        "estado = None\nwhile estado is None:\n    match obter():\n        case {'ok': estado}:\n            pass\n",
        "resto = [1]\nwhile resto:\n    match obter():\n        case [_, *resto]:\n            pass\n",
        "resto = {'a': 1}\nwhile resto:\n    match obter():\n        case {'a': 1, **resto}:\n            pass\n",
        "estado = 1\nwhile estado:\n    match obter():\n        case int() as estado:\n            pass\n",
    ],
)
def test_t5_ada_while_match_case_bindings_sem_falso_positivo(codigo):
    """Regressão T5-ADA-4: `MatchAs`, `MatchStar` e `MatchMapping.rest` atualizam `while` sem falso positivo."""
    mod = importar_modulo("agent_ada")
    res = mod.analisar_logica_codigo(codigo)
    assert res["analisavel"] is True
    assert not any("while" in obs.lower() for obs in res["observacoes_logicas"])


@pytest.mark.parametrize(
    "codigo",
    [
        "estado = None\nwhile estado is None:\n    match obter():\n        case _:\n            pass\n",
        (
            "estado = None\n"
            "while estado is None:\n"
            "    def inner(x):\n"
            "        match x:\n"
            "            case {'ok': estado}:\n"
            "                return estado\n"
            "    inner({})\n"
        ),
    ],
)
def test_t5_ada_while_match_wildcard_ou_escopo_isolado_ainda_alerta(codigo):
    """Regressão T5-ADA-4: `case _:` e `match` em `def` aninhada ainda sinalizam `while` sem saída."""
    mod = importar_modulo("agent_ada")
    res = mod.analisar_logica_codigo(codigo)
    assert any("while" in obs.lower() for obs in res["observacoes_logicas"])


# ==============================================================================
# 3. LINT — Cobertura AST (3.10 match/comprehension/escopo) & `mutacao_global`
# ==============================================================================


def test_t5_lint_complexidade_match_case_comprehension_e_escopo_aninhado():
    """Cobre `match/case`, `comprehension` com `if`, `_ESCOPOS_ISOLADOS` e `complexidade_elevada`."""
    mod = importar_modulo("agent_lint")
    codigo = (
        "def outer(x):\n"
        "    def inner():\n"
        "        return 1\n"
        "    match x:\n"
        "        case 1:\n"
        "            return [i for i in range(3) if i > 0]\n"
        "        case _:\n"
        "            return inner()\n"
    )
    res = mod.analisar_complexidade_codigo(codigo)
    por_nome = {f["nome"]: f for f in res["funcoes"]}
    assert por_nome["outer"]["complexidade_ciclomatica"] == 5
    assert por_nome["outer"]["profundidade_aninhamento"] == 1
    assert por_nome["outer.inner"]["complexidade_ciclomatica"] == 1

    ramos = "\n".join(f"    if x == {i}:\n        return {i}" for i in range(11))
    res_med = mod.analisar_complexidade_codigo(f"def med(x):\n{ramos}\n    return -1\n")
    assert any(a["tipo"] == "complexidade_elevada" for a in res_med["alertas"])


def test_t5_lint_antipadroes_ramos_kwonly_except_multilinhas_import_star_e_retorno_str():
    """Cobre kwonly sem default, except multilinhas, `Assign`/`Subscript`/`Delete` global e `import *`."""
    mod = importar_modulo("agent_lint")
    codigo = (
        "from math import *\n"
        "from typing import Any\n\n"
        "g = 0\n"
        "cfg = {'k': 0}\n\n"
        "def fn(a, *, sem_padrao) -> 'Any':\n"
        "    global g, cfg\n"
        "    g = 1\n"
        "    cfg['k'] = 2\n"
        "    del g\n"
        "    try:\n"
        "        return sem_padrao\n"
        "    except ValueError:\n"
        "        x = 1\n"
        "        return x\n"
    )
    res = mod.detectar_antipadroes_python(codigo)
    tipos = [a["tipo"] for a in res["achados"]]
    assert tipos.count("mutacao_global") == 3
    assert "import_nao_utilizado" not in tipos
    assert "except_silenciado" not in tipos


@pytest.mark.parametrize(
    "corpo_mutacao",
    [
        "    _, g = 1, 2\n",
        "    [_, g] = [1, 2]\n",
        "    *_, g = [1, 2, 3]\n",
        "    for g in range(2):\n        pass\n",
        "    with ctx() as g:\n        pass\n",
        "    if (g := 1):\n        pass\n",
    ],
)
def test_t5_lint_mutacao_global_unpacking_e_alvos_compostos(corpo_mutacao):
    """BUG-LINT-1: `mutacao_global` deve detectar unpacking, `Starred`, `for`, `with` e `NamedExpr`."""
    mod = importar_modulo("agent_lint")
    codigo = f"g = 0\ndef f(ctx=None):\n    global g\n{corpo_mutacao}"
    res = mod.detectar_antipadroes_python(codigo)
    assert any(a["tipo"] == "mutacao_global" for a in res["achados"])


def test_t5_lint_mutacao_global_encadeado_e_alvos_nao_nome():
    """BUG-LINT-1: atribuição encadeada reporta todas as globais e chamada em retorno ignora alvo."""
    mod = importar_modulo("agent_lint")
    codigo = (
        "a = b = 0\n"
        "def f(fabrica):\n"
        "    global a, b\n"
        "    a = b = 1\n"
        "    fabrica().x = 2\n"
    )
    res = mod.detectar_antipadroes_python(codigo)
    mutacoes = [a for a in res["achados"] if a["tipo"] == "mutacao_global"]
    assert len(mutacoes) == 2


def test_t5_lint_mutacao_global_metodo_em_subscrito_ou_atributo():
    """BUG-LINT-1: `cfg['items'].append(1)` e `state.items.append(1)` devem gerar `mutacao_global`."""
    mod = importar_modulo("agent_lint")
    codigo_sub = (
        "cfg = {'items': []}\n"
        "def f():\n"
        "    global cfg\n"
        "    cfg['items'].append(1)\n"
    )
    res_sub = mod.detectar_antipadroes_python(codigo_sub)
    assert any(a["tipo"] == "mutacao_global" for a in res_sub["achados"])

    codigo_attr = (
        "def f():\n"
        "    global state\n"
        "    state.items.append(1)\n"
    )
    res_attr = mod.detectar_antipadroes_python(codigo_attr)
    assert any(a["tipo"] == "mutacao_global" for a in res_attr["achados"])


@pytest.mark.parametrize(
    "corpo_vinculo",
    [
        "    try:\n        1 / 0\n    except Exception as g:\n        pass\n",
        "    import math as g\n",
        "    from math import sin as g\n",
        "    match x:\n        case g:\n            pass\n",
        "    match x:\n        case [_, *g]:\n            pass\n",
        "    match x:\n        case {**g}:\n            pass\n",
    ],
)
def test_t5_lint_mutacao_global_except_import_e_match_case(corpo_vinculo):
    """Regressão T5-LINT-1: `except ... as g`, `import ... as g` e `match/case` detectam `mutacao_global`."""
    mod = importar_modulo("agent_lint")
    codigo = f"g = 0\ndef f(x=None):\n    global g\n{corpo_vinculo}"
    res = mod.detectar_antipadroes_python(codigo)
    mutacoes = [a for a in res["achados"] if a["tipo"] == "mutacao_global"]
    assert len(mutacoes) == 1
    assert "`g`" in mutacoes[0]["o_que"]


def test_t5_lint_mutacao_global_lambda_param_shadow_e_escopo_externo():
    """Regressão T5-LINT-2: parâmetros de `lambda` sombreiam global no corpo, mas não em defaults/outros."""
    mod = importar_modulo("agent_lint")
    codigo_sombreado = (
        "g = []\n"
        "def f():\n"
        "    global g\n"
        "    fn1 = lambda g: g.append(1)\n"
        "    fn2 = lambda *g: g.clear()\n"
        "    fn3 = lambda **g: g.update({})\n"
        "    return fn1, fn2, fn3\n"
    )
    res_sombreado = mod.detectar_antipadroes_python(codigo_sombreado)
    assert not any(a["tipo"] == "mutacao_global" for a in res_sombreado["achados"])

    codigo_misto = (
        "g = []\n"
        "h = []\n"
        "def f():\n"
        "    global g, h\n"
        "    return lambda g, *, x=1, y=None: (h.append(x), g.append(y))\n"
    )
    res_misto = mod.detectar_antipadroes_python(codigo_misto)
    mutacoes_misto = [a for a in res_misto["achados"] if a["tipo"] == "mutacao_global"]
    assert len(mutacoes_misto) == 1
    assert "`h`" in mutacoes_misto[0]["o_que"]

    codigo_default = (
        "g = []\n"
        "def f():\n"
        "    global g\n"
        "    return lambda x=g.append(1): x\n"
    )
    res_default = mod.detectar_antipadroes_python(codigo_default)
    assert any(a["tipo"] == "mutacao_global" and "`g`" in a["o_que"] for a in res_default["achados"])

    codigo_def_interna = (
        "g = 0\n"
        "def outer():\n"
        "    global g\n"
        "    def inner():\n"
        "        g = 1\n"
        "        return g\n"
        "    return inner()\n"
    )
    res_def_interna = mod.detectar_antipadroes_python(codigo_def_interna)
    assert not any(a["tipo"] == "mutacao_global" for a in res_def_interna["achados"])


@pytest.mark.parametrize(
    "expressao",
    [
        "[g.append(1) for g in [[], []]]",
        "{g.pop() for g in [[1], [2]]}",
        "{i: g.append(i) for i, g in enumerate([[], []])}",
        "list(g.append(1) for g in [[], []])",
        "[x for g in [[[1]]] if g for x in g if g.pop()]",
    ],
)
def test_t5_lint_mutacao_global_comprehension_shadowing_sem_falso_positivo(expressao):
    """Regressão T5-LINT-3: alvos de `ListComp`/`SetComp`/`DictComp`/`GeneratorExp` sombreiam global."""
    mod = importar_modulo("agent_lint")
    codigo = f"g = []\ndef f():\n    global g\n    return {expressao}\n"
    res = mod.detectar_antipadroes_python(codigo)
    assert not any(a["tipo"] == "mutacao_global" for a in res["achados"])


@pytest.mark.parametrize(
    "expressao",
    [
        "[g := i for i in range(3)]",
        "[x for x in g.pop()]",
        "[x for x in [1] if g.pop()]",
        "{x: 1 for x in g.pop()}",
    ],
)
def test_t5_lint_mutacao_global_comprehension_walrus_e_iter_externo(expressao):
    """Regressão T5-LINT-3: `NamedExpr` (`:=`) e `generators[0].iter` mantêm detecção de `mutacao_global`."""
    mod = importar_modulo("agent_lint")
    codigo = f"g = []\ndef f():\n    global g\n    return {expressao}\n"
    res = mod.detectar_antipadroes_python(codigo)
    mutacoes = [a for a in res["achados"] if a["tipo"] == "mutacao_global"]
    assert len(mutacoes) == 1
    assert "`g`" in mutacoes[0]["o_que"]


@pytest.mark.parametrize(
    "expressao",
    [
        "[0 for g['x'] in [1, 2]]",
        "[0 for g.x in [1, 2]]",
        "[g['items'].append(1) for g['x'] in [1, 2]]",
        "[0 for k, g['x'] in [(1, 2)]]",
        "[0 for *_, g['x'] in [(1, 2)]]",
        "[0 for g[0] in [1] if g.pop()]",
    ],
)
def test_t5_lint_mutacao_global_comprehension_alvo_subscrito_ou_atributo(expressao):
    """Regressão T5-LINT-4: alvos `Subscript`/`Attribute` em compreensões detectam `mutacao_global` sem sombrear."""
    mod = importar_modulo("agent_lint")
    codigo = f"g = {{'items': [], 'x': 0}}\ndef f():\n    global g\n    return {expressao}\n"
    res = mod.detectar_antipadroes_python(codigo)
    mutacoes = [a for a in res["achados"] if a["tipo"] == "mutacao_global"]
    assert len(mutacoes) == 1
    assert "`g`" in mutacoes[0]["o_que"]


def test_t5_lint_mutacao_global_comprehension_alvo_starred_e_sombreado():
    """Regressão T5-LINT-4: `*g` sombreia em `gen[0]`, `g` sombreado protege `gen[1]`, e slice propaga mutação."""
    mod = importar_modulo("agent_lint")
    codigo_starred = "g = []\ndef f():\n    global g\n    return [g.append(1) for *g, _ in [[[1], 2]]]\n"
    assert not any(a["tipo"] == "mutacao_global" for a in mod.detectar_antipadroes_python(codigo_starred)["achados"])

    codigo_duplo = "g = {}\ndef f():\n    global g\n    return [0 for g in [{}] for g['x'] in [1]]\n"
    assert not any(a["tipo"] == "mutacao_global" for a in mod.detectar_antipadroes_python(codigo_duplo)["achados"])

    codigo_slice = "g = {'x': 0}\nh = []\ndef f():\n    global g, h\n    return [0 for g[h.pop()] in [1]]\n"
    muts = [a for a in mod.detectar_antipadroes_python(codigo_slice)["achados"] if a["tipo"] == "mutacao_global"]
    assert len(muts) == 2


# ==============================================================================
# 4. VAL — Colisões de substring na KB & tokens sensíveis acentuados
# ==============================================================================


@pytest.mark.parametrize(
    ("consulta", "topico_esperado"),
    [
        ("o que significa o simbolo vermelho no modem?", "suporte_modem"),
        ("modelos de planos de fibra", "planos"),
        ("escalonamento de protocolos", "escalonamento"),
        ("prazos e protocolos de atendimento", "prazos"),
        ("segunda via de boletos vencidos", "fatura"),
    ],
)
def test_t5_val_kb_sem_colisao_substring_bolo_e_los(consulta, topico_esperado):
    """BUG-VAL-1: Fronteira de palavra evita que 'bolo' ou 'los' sequestrem consultas válidas."""
    mod = importar_modulo("agent_val")
    res = mod.consultar_base_conhecimento(consulta)
    assert res["encontrado"] is True
    assert res["topico"] == topico_esperado


@pytest.mark.parametrize("consulta_nao_encontrada", ["atendimento excepcional", "legislacao da anatel"])
def test_t5_val_kb_sem_falso_acerto_cep_ou_sla_em_substrings(consulta_nao_encontrada):
    """BUG-VAL-1: 'cep' em 'excepcional' e 'sla' em 'legislacao' não causam acerto espúrio."""
    mod = importar_modulo("agent_val")
    res = mod.consultar_base_conhecimento(consulta_nao_encontrada)
    assert res["encontrado"] is False
    assert res["topico"] is None


@pytest.mark.parametrize(
    ("payload", "segredo_proibido"),
    [
        ("senha: café123", "café123"),
        ("senha: ação", "ação"),
        ("senha: é123", "é123"),
        ("password: naïve1", "naïve1"),
        ("código 2fa: café1", "café1"),
        ('senha: "abc 123"', "abc 123"),
        ("senha='meu segredo 1'", "meu segredo 1"),
        ('código 2fa: "123 456"', "123 456"),
        ('código 2fa "123 456"', "123 456"),
        ('senha: "minha frase secreta"', "minha frase secreta"),
        ("senha: cafe\u0301123", "123"),
        ("senha: e\u0301123", "123"),
        ("co\u0301digo de dois fatores: 123456", "123456"),
        ("senha: \u010dau123", "\u010dau123"),
        ("fotos do meu rg", "fotos do meu rg"),
    ],
)
def test_t5_val_sanitizacao_tokens_unicode_acentuados(payload, segredo_proibido):
    """BUG-VAL-2 / T5-VAL-2: Sanitiza acentos NFC/NFD, Unicode estendido, aspas com espaços e `fotos`."""
    mod = importar_modulo("agent_val")
    res_kb = mod.consultar_base_conhecimento(payload)
    assert res_kb["dado_sensivel_removido"] is True
    assert segredo_proibido not in res_kb["consulta_original"].lower()
    assert "\u0301123" not in res_kb["consulta_original"]

    res_st = mod.verificar_status_chamado(payload)
    assert res_st["dado_sensivel_removido"] is True
    assert segredo_proibido not in res_st["protocolo"].lower()

    res_esc = mod.registrar_escalonamento("cancelamento", payload, payload)
    assert res_esc["registrado"] is True
    assert res_esc["dado_sensivel_removido"] is True
    assert segredo_proibido not in res_esc["resumo"].lower()


@pytest.mark.parametrize(
    ("motivo_plural", "motivo_esperado"),
    [
        ("cobrancas contestadas", "cobranca_contestada"),
        ("cancelamentos", "cancelamento"),
        ("faturas e estornos", "cobranca_contestada"),
        ("excecoes as politicas", "excecao_politica"),
    ],
)
def test_t5_val_plurais_motivo_escalonamento(motivo_plural, motivo_esperado):
    """Regressão T5-VAL-1: plurais em `_ALIASES_MOTIVO` não sofrem regressão com `_contem_termo`."""
    mod = importar_modulo("agent_val")
    res = mod.registrar_escalonamento(motivo_plural, "Resumo operacional válido.")
    assert res["registrado"] is True
    assert res["motivo"] == motivo_esperado


@pytest.mark.parametrize(
    ("consulta_kb", "topico_esperado"),
    [
        ("wi fi", "suporte_modem"),
        ("oscilacoes na conexao", "suporte_modem"),
        ("lentidoes no roteador", "suporte_modem"),
    ],
)
def test_t5_val_aliases_kb_wi_fi_e_plurais(consulta_kb, topico_esperado):
    """Regressão T5-VAL-1: `wi fi`, `oscilacoes` e `lentidoes` resolvem para `suporte_modem`."""
    mod = importar_modulo("agent_val")
    res = mod.consultar_base_conhecimento(consulta_kb)
    assert res["encontrado"] is True
    assert res["topico"] == topico_esperado


@pytest.mark.parametrize("prosa_segura", ["esqueci minha senha 'hoje'", "cafe\u0301 e modem"])
def test_t5_val_prosa_segura_com_aspas_ou_nfd_nao_sofre_over_redaction(prosa_segura):
    """Regressão T5-VAL-2: prosa sem segredo com aspas ou NFD é preservada intacta."""
    mod = importar_modulo("agent_val")
    res = mod.consultar_base_conhecimento(prosa_segura)
    assert res["dado_sensivel_removido"] is False
    assert res["consulta_original"] == prosa_segura


@pytest.mark.parametrize(
    ("payload", "segredo_proibido"),
    [
        ("senha do wifi: abc123", "abc123"),
        ("senha do wifi é segredo123", "segredo123"),
        ("senha do roteador: admin123", "admin123"),
        ("senha de acesso: 123456", "123456"),
        ("cvv do cartao: 999", "999"),
        ("cvv do cartão 999", "999"),
        ("fotos das minhas identidades", "fotos das minhas identidades"),
    ],
)
def test_t5_val_sanitizacao_credenciais_qualificadas_e_identidades(payload, segredo_proibido):
    """Regressão T5-VAL-3: credenciais com qualificadores de domínio e `identidades` são sanitizadas."""
    mod = importar_modulo("agent_val")
    res_kb = mod.consultar_base_conhecimento(payload)
    assert res_kb["dado_sensivel_removido"] is True
    assert segredo_proibido not in res_kb["consulta_original"].lower()

    res_esc = mod.registrar_escalonamento("cancelamento", payload, payload)
    assert res_esc["registrado"] is True
    assert res_esc["dado_sensivel_removido"] is True
    assert segredo_proibido not in res_esc["resumo"].lower()


@pytest.mark.parametrize(
    "prosa_segura",
    [
        "esqueci a senha do wifi",
        "nao sei a senha do roteador",
        "esqueci minha senha do wifi e preciso de ajuda",
        "posso mandar fotos do modem?",
        'esqueci minha senha "hoje"',
    ],
)
def test_t5_val_prosa_segura_credenciais_qualificadas_nao_sofre_over_redaction(prosa_segura):
    """Regressão T5-VAL-3: prosa segura sobre senha do Wi-Fi/roteador ou foto do modem permanece intacta."""
    mod = importar_modulo("agent_val")
    res = mod.consultar_base_conhecimento(prosa_segura)
    assert res["dado_sensivel_removido"] is False
    assert res["consulta_original"] == prosa_segura
