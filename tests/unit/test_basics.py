"""Testes Unitários para as Funções Básicas e Ferramentas do Agente.

Conceito Didático para CI/CD:
Valida as operações fundamentais do sistema de arquivos e funções utilitárias puras
de forma hermética, utilizando fixtures nativas do Pytest (`tmp_path` e `monkeypatch`),
sem tocar no sistema de arquivos real do host nem depender da disponibilidade da API OpenAI.
"""

from datetime import datetime
import json
from pathlib import Path
import pytest
import agent


def test_carregar_contexto_com_arquivos(monkeypatch, tmp_path):
    """Valida carregamento de contexto com arquivos agent.md e memory.md mockados.

    Conceito Didático (CI/CD para Agentes):
    Testes unitários devem ser herméticos. Não devem depender de arquivos de
    documentação voláteis do repositório, que podem ser editados por copywriters
    ou engenheiros de prompt a qualquer instante.
    """
    # [ARRANGE] Criação de arquivos de contexto isolados em diretório temporário
    fake_agent = tmp_path / "agent.md"
    fake_memory = tmp_path / "memory.md"
    fake_agent.write_text("Identidade: Organizador de Arquivos Especialista", encoding="utf-8")
    fake_memory.write_text("Preferência: Manter subpastas de ano e mês", encoding="utf-8")

    monkeypatch.setattr(agent, "AGENT_MD", fake_agent)
    monkeypatch.setattr(agent, "MEMORY_MD", fake_memory)

    # [ACT] Execução da montagem do prompt de sistema
    contexto = agent.carregar_contexto()

    # [ASSERT] Verificação precisa sem operadores lógicos ambíguos ('or')
    assert "Identidade: Organizador de Arquivos Especialista" in contexto
    assert "Preferência: Manter subpastas de ano e mês" in contexto
    assert "# Memória" in contexto


def test_carregar_contexto_fallback_sem_arquivos(monkeypatch, tmp_path):
    """Garante o fallback defensivo padrão quando os arquivos Markdown não existem.

    Conceito Didático:
    Testa a resiliência do agente caso os arquivos de prompt sejam apagados ou
    movidos acidentalmente durante o deploy.
    """
    # [ARRANGE] Aponta caminhos para arquivos inexistentes
    monkeypatch.setattr(agent, "AGENT_MD", tmp_path / "inexistente_agent.md")
    monkeypatch.setattr(agent, "MEMORY_MD", tmp_path / "inexistente_memory.md")

    # [ACT] Execução
    contexto = agent.carregar_contexto()

    # [ASSERT] Fallback documentado no agent.py
    assert "Você é um assistente." in contexto
    assert "# Memória" in contexto


def test_obter_pastas_padrao(monkeypatch, tmp_path):
    """Valida se retorna as 3 pastas padrão do usuário isoladas via mock de Path.home.

    Conceito Didático:
    Evita acessar o filesystem real do sistema operacional do desenvolvedor ou
    servidor de CI, garantindo determinismo entre Windows, Linux e macOS.
    """
    # [ARRANGE] Criação de pasta home simulada
    fake_home = tmp_path / "fake_user_home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # [ACT] Chamada da ferramenta
    pastas = agent.obter_pastas_padrao()

    # [ASSERT] Validação estrita do conjunto exato de chaves e dos caminhos gerados
    assert set(pastas.keys()) == {"downloads", "documentos", "desktop"}
    assert pastas["downloads"] == str(fake_home / "Downloads")
    assert pastas["documentos"] == str(fake_home / "Documents")
    assert pastas["desktop"] == str(fake_home / "Desktop")


def test_criar_pasta(tmp_path):
    """Valida a criação atômica de pastas e hierarquias profundas pelo agente.

    Conceito Didático (Princípio da Responsabilidade Única - SRP):
    A criação de diretórios deve ser testada independentemente de ferramentas
    de leitura para facilitar o isolamento de falhas no pipeline de CI.
    """
    # [ARRANGE] Define caminho de pasta hierárquica no padrão [Ano]/[Categoria]/[Mes]/[Dia]
    pasta_destino = tmp_path / "2026" / "Documentos" / "02" / "10"

    # [ACT] Executa criação da pasta
    resultado = agent.criar_pasta(str(pasta_destino))

    # [ASSERT] Valida contrato de retorno e criação física
    assert resultado["sucesso"] is True
    assert pasta_destino.is_dir()
    assert Path(resultado["pasta_criada"]) == pasta_destino.resolve()


def test_listar_arquivos_metadados(tmp_path):
    """Valida a extração completa de metadados temporais e estruturais dos arquivos.

    Conceito Didático (Engenharia de Decisão para LLM):
    O modelo de IA necessita de metadados íntegros para decidir a pasta destino.
    O teste deve validar o formato de ano (4 dígitos), mês (2 dígitos), dia (2 dígitos)
    e tipos numéricos para evitar alucinações de classificação.
    """
    # [ARRANGE] Criação de pasta isolada com arquivo representativo
    pasta_teste = tmp_path / "downloads_simulados"
    pasta_teste.mkdir()
    arquivo_teste = pasta_teste / "fatura_internet.pdf"
    arquivo_teste.write_text("Fatura paga", encoding="utf-8")

    # [ACT] Listagem dos arquivos pela ferramenta do agente
    resultado = agent.listar_arquivos(str(pasta_teste))

    # [ASSERT] Validação quantitativa e estrutural
    assert resultado["total_encontrados"] == 1
    assert Path(resultado["diretorio"]) == pasta_teste.resolve()

    item = resultado["arquivos"][0]
    assert item["nome"] == "fatura_internet.pdf"
    assert item["extensao"] == ".pdf"

    # Validação semântica de metadados temporais para o LLM
    assert item["ano"].isdigit() and len(item["ano"]) == 4, "Ano deve conter 4 dígitos numéricos"
    assert item["mes"].isdigit() and len(item["mes"]) == 2, "Mês deve conter 2 dígitos numéricos"
    assert item["dia"].isdigit() and len(item["dia"]) == 2, "Dia deve conter 2 dígitos numéricos"

    # Validação de metadados físicos adicionais
    assert isinstance(item["tamanho_kb"], float) and item["tamanho_kb"] >= 0.0
    assert Path(item["caminho_completo"]).is_file()
    assert datetime.strptime(item["data_modificacao"], "%Y-%m-%d %H:%M:%S")


def test_mover_arquivo(tmp_path):
    """Testa a movimentação atômica de um arquivo e criação automática de subpastas.

    Conceito Didático:
    Valida se a ferramenta não apenas move o arquivo físico, mas também devolve
    as chaves contratuais 'de' e 'para' com caminhos canônicos resolvidos.
    """
    # [ARRANGE] Cria arquivo de origem e pasta destino
    origem = tmp_path / "foto.jpg"
    origem.write_text("dados da imagem", encoding="utf-8")
    destino_pasta = tmp_path / "2025" / "Fotos da viagem" / "07" / "15"

    # [ACT] Executa movimentação
    res_mover = agent.mover_arquivo(str(origem), str(destino_pasta))
    destino_esperado = destino_pasta / "foto.jpg"

    # [ASSERT] Valida contrato e estado do disco
    assert res_mover["sucesso"] is True
    assert res_mover["de"] == str(origem)
    assert res_mover["para"] == str(destino_esperado.resolve())
    assert not origem.exists()
    assert destino_esperado.is_file()


def test_executar_ferramenta_inexistente():
    """Garante que ferramenta inexistente retorna erro serializado em JSON válido.

    Conceito Didático (Integridade do Protocolo de Tool-Calling):
    A função `executar_ferramenta` deve SEMPRE retornar um JSON parseável para
    que o loop do agente consiga repassar a mensagem ao LLM sem travar a aplicação.
    """
    # [ACT] Executa chamada de ferramenta desconhecida
    res_json = agent.executar_ferramenta("ferramenta_fantasma", {})

    # [ASSERT] Valida parsing de JSON e presença da mensagem de erro estruturada
    dados = json.loads(res_json)
    assert isinstance(dados, dict)
    assert "erro" in dados
    assert "não existe" in dados["erro"]


@pytest.mark.parametrize(
    "arquivo_ignorado",
    [
        ".DS_Store",
        ".env",
        ".gitignore",
        "desktop.ini",
        "DESKTOP.INI",
        "config.Ini",
    ],
)
def test_ignorar_arquivos_ocultos_e_sistema(tmp_path, arquivo_ignorado):
    """Garante que arquivos ocultos (iniciados com .) e arquivos .ini (case-insensitive) são ignorados.

    Conceito Didático (CI/CD para Agentes):
    O agente não deve manipular arquivos de sistema operacional ou metadados de repositório.
    A regra atual de agent.py filtra:
      1. Arquivos iniciados por '.' (item.name.startswith('.'))
      2. Arquivos terminados em '.ini' independentemente de caixa (item.name.lower().endswith('.ini'))
    Nota: 'Thumbs.db' não é filtrado pelo agent.py atual, logo não deve constar nesta parametrização.
    """
    # [ARRANGE] Cria diretório com um arquivo legítimo e um arquivo que deve ser ignorado
    pasta = tmp_path / "teste_ignorar"
    pasta.mkdir()
    (pasta / "documento_valido.pdf").write_text("conteúdo legítimo", encoding="utf-8")
    (pasta / arquivo_ignorado).write_text("deve ser ignorado", encoding="utf-8")

    # [ACT] Executa listagem
    resultado = agent.listar_arquivos(str(pasta))

    # [ASSERT] Apenas o arquivo legítimo deve ser retornado
    assert resultado["total_encontrados"] == 1
    assert len(resultado["arquivos"]) == 1
    assert resultado["arquivos"][0]["nome"] == "documento_valido.pdf"


def test_ler_conteudo_ou_resumo_texto(tmp_path):
    """Testa leitura de arquivos de texto puro dentro do limite."""
    # [ARRANGE]
    txt = tmp_path / "relatorio.txt"
    txt.write_text("Relatório financeiro do mês de Julho.", encoding="utf-8")

    # [ACT]
    resultado = agent.ler_conteudo_ou_resumo(str(txt))

    # [ASSERT]
    assert resultado["tipo"] == "texto"
    assert "Relatório financeiro" in resultado["amostra"]


def test_ler_conteudo_texto_truncamento_limite(tmp_path):
    """Garante proteção da janela de contexto cortando arquivos longos no limite de caracteres.

    Conceito Didático (Engenharia de Agentes e FinOps):
    Injetar arquivos extensos sem controle na memória do LLM ocasiona estouro de tokens
    (ContextWindowExceeded) e aumento drástico de custos de API. O parâmetro limite_caracteres
    é a barreira de proteção orçamentária e operacional do agente.
    """
    # [ARRANGE] Cria arquivo de texto extenso superando o limite estabelecido
    limite = 300
    arquivo_longo = tmp_path / "documento_extenso.txt"
    arquivo_longo.write_text("A" * 1500, encoding="utf-8")

    # [ACT] Lê o arquivo definindo limite explícito
    resultado = agent.ler_conteudo_ou_resumo(str(arquivo_longo), limite_caracteres=limite)

    # [ASSERT] Valida se o truncamento respeita estritamente o limite estabelecido
    assert resultado["tipo"] == "texto"
    assert len(resultado["amostra"]) <= limite
    assert len(resultado["amostra"]) == limite
    assert resultado["amostra"] == "A" * limite


def test_ler_conteudo_ou_resumo_binario(tmp_path):
    """Garante que formatos não suportados recebem aviso amigável sem quebrar.

    Conceito Didático (Integridade Pedagógica):
    No agente atual, a decisão sobre formatos binários/não suportados é realizada
    puramente com base na extensão do arquivo (p.suffix.lower()), sem inspecionar
    cabeçalhos binários ou 'magic bytes' (MIME). Logo, criar bytes falsos de PNG
    induziria estudantes a acreditar em uma inspeção que o código não executa.
    """
    # [ARRANGE] Cria arquivo com extensão não textual (ex: .png)
    img = tmp_path / "foto.png"
    img.write_bytes(b"conteudo_binario_simulado")

    # [ACT] Executa ferramenta
    resultado = agent.ler_conteudo_ou_resumo(str(img))

    # [ASSERT] Valida contrato de aviso amigável
    assert "aviso" in resultado
    assert resultado["extensao"] == ".png"
    assert "não possui extrator de texto configurado" in resultado["aviso"]
