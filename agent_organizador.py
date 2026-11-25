"""
Agente Organizador de Arquivos (`agent-organizador.md`).

Fornece as 5 ferramentas de inspeção e organização de arquivos em disco,
mantendo isolamento estrito (sem ferramentas de outros perfis).
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

import agent_core

PERFIL_NOME: str = "agent-organizador.md"
AGENT_MD: Path = agent_core.RAIZ / PERFIL_NOME
MEMORY_MD: Path = agent_core.RAIZ / "memory.md"

_EXTENSOES_TEXTO = {
    ".txt", ".md", ".csv", ".json", ".log",
    ".py", ".html", ".xml", ".yaml", ".yml", ".ini",
}


def obter_pastas_padrao() -> dict:
    """Retorna os caminhos das pastas padrão do usuário (Downloads, Documentos, Desktop)."""
    home = Path.home()
    return {
        "downloads": str(home / "Downloads"),
        "documentos": str(home / "Documents"),
        "desktop": str(home / "Desktop"),
    }


def listar_arquivos(diretorio: str, limite: int = 8) -> dict:
    """Lista arquivos e pastas em um diretório com metadados temporais (ano, mês, dia), extensão e tamanho."""
    caminho = Path(diretorio)
    if not caminho.exists() or not caminho.is_dir():
        return {"erro": f"Diretório não encontrado: {diretorio}"}

    # Trava de FinOps/Context Window: limita a 8 itens por chamada para caber no limite de 8.000 TPM da Groq
    limite_seguro = max(0, min(int(limite), 8))
    if limite_seguro == 0:
        return {
            "diretorio": str(caminho.resolve()),
            "total_encontrados": 0,
            "arquivos": [],
        }

    arquivos = []
    for item in caminho.iterdir():
        if item.name.startswith(".") or item.name.lower().endswith(".ini"):
            continue
        if item.is_dir() and item.name.isdigit() and len(item.name) == 4:
            continue

        if item.is_file() or item.is_dir():
            stat = item.stat()
            dt_mod = datetime.fromtimestamp(stat.st_mtime)
            arquivos.append({
                "nome": item.name,
                "tipo": "pasta" if item.is_dir() else "arquivo",
                "caminho_completo": str(item.resolve()),
                "extensao": "pasta" if item.is_dir() else item.suffix.lower(),
                "tamanho_kb": 0.0 if item.is_dir() else round(stat.st_size / 1024, 2),
                "data_modificacao": dt_mod.strftime("%Y-%m-%d %H:%M:%S"),
                "ano": dt_mod.strftime("%Y"),
                "mes": dt_mod.strftime("%m"),
                "dia": dt_mod.strftime("%d"),
            })
            if len(arquivos) >= limite_seguro:
                break

    return {
        "diretorio": str(caminho.resolve()),
        "total_encontrados": len(arquivos),
        "arquivos": arquivos,
    }


def criar_pasta(caminho: str) -> dict:
    """Cria uma nova pasta ou estrutura hierárquica de pastas (ex.: 2025/Fotos/07/15)."""
    p = Path(caminho)
    p.mkdir(parents=True, exist_ok=True)
    return {"sucesso": True, "pasta_criada": str(p.resolve())}


def _resolver_destino_movimentacao(src: Path, dst: Path, destino: str) -> tuple[Path, Path] | dict:
    """Resolve `(destino_final, pai_destino)` ou retorna erro se destino for incompatível."""
    if (dst.exists() or dst.is_symlink()) and not dst.is_dir():
        if src.is_dir() or destino.endswith(("/", "\\")):
            return {"erro": f"Destino não é um diretório válido: {destino}"}
        return dst, dst.parent
    if src.is_dir() or dst.is_dir() or destino.endswith(("/", "\\")) or not dst.suffix:
        return dst / src.name, dst
    return dst, dst.parent


def mover_arquivo(origem: str, destino: str) -> dict:
    """Move um arquivo ou pasta da origem para o destino. Cria a pasta de destino caso não exista."""
    if not isinstance(origem, str) or not origem.strip():
        return {"erro": f"Caminho de origem inválido: {origem!r}"}
    origem_limpa = origem.strip()
    if Path(origem_limpa).name in {"", ".", ".."}:
        return {"erro": f"Caminho de origem inválido: {origem!r}"}
    if not isinstance(destino, str) or not destino.strip():
        return {"erro": f"Caminho de destino inválido: {destino!r}"}
    destino_limpa = destino.strip()

    src = Path(origem_limpa)
    dst = Path(destino_limpa)

    if not src.exists():
        return {"erro": f"Arquivo ou pasta de origem não existe: {origem_limpa}"}

    resolucao = _resolver_destino_movimentacao(src, dst, destino_limpa)
    if isinstance(resolucao, dict):
        return resolucao
    destino_final, pai_destino = resolucao

    src_resolvido = src.resolve()
    dst_resolvido = destino_final.resolve()

    if src.is_dir() and dst_resolvido.is_relative_to(src_resolvido):
        return {"erro": f"Não é possível mover uma pasta para dentro de si mesma: {destino_limpa}"}
    if src_resolvido == dst_resolvido:
        return {"erro": f"Origem e destino são o mesmo caminho: {destino_final}"}
    if destino_final.exists() or destino_final.is_symlink():
        return {"erro": f"Destino já existe e não será sobrescrito: {destino_final}"}

    try:
        pai_destino.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, NotADirectoryError, OSError) as exc:
        return {"erro": f"Não foi possível preparar diretório de destino: {exc}"}

    shutil.move(str(src), str(destino_final))
    return {
        "sucesso": True,
        "de": str(src),
        "para": str(destino_final.resolve()),
    }


def _ler_texto(p: Path, ext: str, limite_caracteres: int) -> dict:
    """Lê trecho inicial de arquivos textuais puros."""
    try:
        conteudo = p.read_text(encoding="utf-8", errors="ignore")[:limite_caracteres]
        return {
            "tipo": "texto",
            "extensao": ext,
            "amostra": conteudo.strip(),
        }
    except Exception as exc:
        return {"erro": f"Não foi possível ler texto puro: {exc}"}


def _ler_pdf(p: Path, limite_caracteres: int) -> dict:
    """Extrai amostra de texto das primeiras páginas de um arquivo PDF."""
    try:
        import pypdf

        leitor = pypdf.PdfReader(str(p))
        texto_extraido = ""
        for pagina in leitor.pages[:3]:
            texto_extraido += (pagina.extract_text() or "") + "\n"
            if len(texto_extraido) >= limite_caracteres:
                break
        return {
            "tipo": "pdf",
            "total_paginas": len(leitor.pages),
            "amostra": texto_extraido[:limite_caracteres].strip(),
        }
    except Exception as exc:
        return {"aviso": f"Falha ao ler PDF ({exc}). Use os metadados para classificar."}


def _ler_docx(p: Path, limite_caracteres: int) -> dict:
    """Extrai amostra de texto dos parágrafos iniciais de um documento Word."""
    try:
        import docx

        doc = docx.Document(str(p))
        paragrafos = [par.text for par in doc.paragraphs if par.text.strip()]
        texto_unido = "\n".join(paragrafos)[:limite_caracteres]
        return {
            "tipo": "docx",
            "amostra": texto_unido.strip(),
        }
    except Exception as exc:
        return {"aviso": f"Falha ao ler DOCX ({exc}). Use os metadados para classificar."}


def _ler_xlsx(p: Path, limite_caracteres: int) -> dict:
    """Extrai nomes das abas e amostra inicial de linhas de uma planilha Excel."""
    try:
        import openpyxl

        wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
        try:
            planilhas = wb.sheetnames
            primeira_aba = wb[planilhas[0]]
            linhas = []
            for row in primeira_aba.iter_rows(max_row=10, max_col=10, values_only=True):
                linha_filtrada = [str(cell) for cell in row if cell is not None]
                if linha_filtrada:
                    linhas.append(" | ".join(linha_filtrada))
        finally:
            wb.close()
        return {
            "tipo": "xlsx",
            "planilhas": planilhas,
            "amostra": "\n".join(linhas)[:limite_caracteres].strip(),
        }
    except Exception as exc:
        return {"aviso": f"Falha ao ler XLSX ({exc}). Use os metadados para classificar."}


def ler_conteudo_ou_resumo(caminho_arquivo: str, limite_caracteres: int = 1500) -> dict:
    """Lê os primeiros caracteres ou trecho inicial de um documento para classificação temática."""
    p = Path(caminho_arquivo)
    if not p.exists() or not p.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho_arquivo}"}

    limite_seguro = max(0, int(limite_caracteres))
    ext = p.suffix.lower()
    if ext in _EXTENSOES_TEXTO:
        return _ler_texto(p, ext, limite_seguro)

    leitores = {
        ".pdf": _ler_pdf,
        ".docx": _ler_docx,
        ".xlsx": _ler_xlsx,
    }
    leitor = leitores.get(ext)
    if leitor is not None:
        return leitor(p, limite_seguro)

    return {
        "aviso": (
            f"Arquivo de formato '{ext}' não possui extrator de texto configurado. "
            "Classifique pelo nome, data e extensão."
        ),
        "extensao": ext,
    }


FERRAMENTAS: list[ChatCompletionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "obter_pastas_padrao",
            "description": (
                "Retorna os caminhos absolutos das pastas principais do usuário no Windows: "
                "Downloads, Documentos e Área de Trabalho (Desktop)."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_arquivos",
            "description": (
                "Lista os arquivos de um diretório com metadados: "
                "ano, mês, dia, extensão, tamanho e nome."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "diretorio": {
                        "type": "string",
                        "description": (
                            "Caminho do diretório a ser listado "
                            "(ex: caminho de Downloads ou pasta específica)."
                        ),
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Limite máximo de arquivos ou pastas a listar (padrão 8, máximo 8).",
                    },
                },
                "required": ["diretorio"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "criar_pasta",
            "description": (
                "Cria um diretório ou uma estrutura hierárquica de pastas "
                "no formato [Ano]/[Categoria]/[Mes]/[Dia]."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho": {
                        "type": "string",
                        "description": "Caminho completo da pasta ou pastas a serem criadas.",
                    },
                },
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mover_arquivo",
            "description": "Move um arquivo para sua pasta de destino final na estrutura organizada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origem": {
                        "type": "string",
                        "description": "Caminho completo do arquivo de origem.",
                    },
                    "destino": {
                        "type": "string",
                        "description": "Caminho da pasta de destino ou caminho completo do arquivo no destino.",
                    },
                },
                "required": ["origem", "destino"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ler_conteudo_ou_resumo",
            "description": (
                "Lê uma amostra do conteúdo inicial de um arquivo (texto, PDF, DOCX, XLSX) "
                "para auxiliar na classificação temática sem extrapolar a janela de contexto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho_arquivo": {
                        "type": "string",
                        "description": "Caminho completo do arquivo a ser inspecionado.",
                    },
                    "limite_caracteres": {
                        "type": "integer",
                        "description": "Limite máximo de caracteres a extrair (padrão 1500).",
                    },
                },
                "required": ["caminho_arquivo"],
            },
        },
    },
]

EXECUTORES: dict[str, Callable[..., Any]] = {
    "obter_pastas_padrao": obter_pastas_padrao,
    "listar_arquivos": listar_arquivos,
    "criar_pasta": criar_pasta,
    "mover_arquivo": mover_arquivo,
    "ler_conteudo_ou_resumo": ler_conteudo_ou_resumo,
}


def carregar_contexto() -> str:
    """Carrega o prompt de sistema do organizador junto à memória persistida."""
    return agent_core.carregar_contexto(AGENT_MD, MEMORY_MD)


def executar_ferramenta(nome: str, argumentos: dict) -> str:
    """Executa uma ferramenta do perfil organizador."""
    return agent_core.executar_ferramenta(nome, argumentos, EXECUTORES)


def responder(mensagens: list[ChatCompletionMessageParam], verboso: bool = False) -> str:
    """Executa o loop ReAct isolado com as ferramentas do organizador."""
    return agent_core.executar_loop_react(
        mensagens=mensagens,
        ferramentas=FERRAMENTAS,
        executores=EXECUTORES,
        verboso=verboso,
    )
