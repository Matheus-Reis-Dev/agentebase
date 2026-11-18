"""
Agente base — esqueleto mínimo.

Este é o núcleo do agente. Ele não sabe nada sobre interface: pode ser
usado pelo terminal (o `main()` no fim do arquivo), pelo `app.py`
(Streamlit), por um teste ou por uma API.

Estrutura, na ordem em que as coisas acontecem:

    1. CONFIGURAÇÃO   — chave e modelo, vindos do .env
    2. CONTEXTO       — agent.md (quem ele é) + memory.md (o que sabe)
    3. FERRAMENTAS    — o que ele consegue FAZER além de falar
    4. O LOOP         — o coração do agente
    5. O TERMINAL     — a interface mais simples possível

Rode com:  python agent.py
"""

import json
import os
import sys
import shutil
from datetime import datetime
from typing import cast
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

# ==========================================================================
# 1. CONFIGURAÇÃO
# ==========================================================================

load_dotenv()

RAIZ = Path(__file__).resolve().parent
AGENT_MD = RAIZ / "agent.md"
MEMORY_MD = RAIZ / "memory.md"

MODELO = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TEMPERATURA = float(os.getenv("AGENTE_TEMPERATURA", "0.6"))
MAX_ITERACOES = int(os.getenv("AGENTE_MAX_ITERACOES", "8"))

_cliente = None


def get_cliente() -> OpenAI:
    """Instancia o cliente da OpenAI — uma vez só, na primeira chamada.

    AQUI que o modelo entra no projeto. Trocar de provedor começa por aqui.
    """
    global _cliente
    if _cliente is None:
        chave = os.getenv("OPENAI_API_KEY")
        if not chave:
            raise RuntimeError(
                "OPENAI_API_KEY não encontrada. Copie .env.example para .env e coloque sua chave."
            )
        base_url = os.getenv("OPENAI_BASE_URL")
        _cliente = OpenAI(api_key=chave, base_url=base_url) if base_url else OpenAI(api_key=chave)
    return _cliente


# ==========================================================================
# 2. CONTEXTO
# ==========================================================================


def carregar_contexto() -> str:
    """Monta o prompt de sistema a partir dos dois arquivos de contexto.

    agent.md  = identidade e regras do agente
    memory.md = o que ele sabe sobre o usuário (persiste entre execuções)

    Editar esses arquivos muda o comportamento sem tocar em Python.
    """
    identidade = AGENT_MD.read_text(encoding="utf-8") if AGENT_MD.exists() else "Você é um assistente."
    memoria = MEMORY_MD.read_text(encoding="utf-8") if MEMORY_MD.exists() else ""
    return f"{identidade}\n\n---\n\n# Memória\n\n{memoria}"


# ==========================================================================
# 3. FERRAMENTAS (Organizador de Arquivos)
# ==========================================================================


def obter_pastas_padrao() -> dict:
    """Retorna os caminhos das pastas padrão do usuário (Downloads, Documentos, Desktop)."""
    home = Path.home()
    return {
        "downloads": str(home / "Downloads"),
        "documentos": str(home / "Documents"),
        "desktop": str(home / "Desktop"),
    }


def listar_arquivos(diretorio: str, limite: int = 50) -> dict:
    """Lista arquivos em um diretório com metadados temporais (ano, mês, dia), extensão e tamanho."""
    caminho = Path(diretorio)
    if not caminho.exists() or not caminho.is_dir():
        return {"erro": f"Diretório não encontrado: {diretorio}"}

    arquivos = []
    itens = list(caminho.iterdir())
    for item in itens:
        if item.is_file():
            # Trava de segurança: ignora arquivos ocultos ou de configuração de sistema
            if item.name.startswith(".") or item.name.lower().endswith(".ini"):
                continue

            stat = item.stat()
            dt_mod = datetime.fromtimestamp(stat.st_mtime)
            arquivos.append({
                "nome": item.name,
                "caminho_completo": str(item.resolve()),
                "extensao": item.suffix.lower(),
                "tamanho_kb": round(stat.st_size / 1024, 2),
                "data_modificacao": dt_mod.strftime("%Y-%m-%d %H:%M:%S"),
                "ano": dt_mod.strftime("%Y"),
                "mes": dt_mod.strftime("%m"),
                "dia": dt_mod.strftime("%d"),
            })
            if len(arquivos) >= limite:
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


def mover_arquivo(origem: str, destino: str) -> dict:
    """Move um arquivo da origem para o destino. Cria a pasta de destino caso não exista."""
    src = Path(origem)
    dst = Path(destino)

    if not src.exists() or not src.is_file():
        return {"erro": f"Arquivo de origem não existe: {origem}"}

    # Se o destino já for uma pasta existente, ou não tiver extensão de arquivo
    if dst.is_dir() or destino.endswith(("/", "\\")) or not dst.suffix:
        dst.mkdir(parents=True, exist_ok=True)
        destino_final = dst / src.name
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        destino_final = dst

    shutil.move(str(src), str(destino_final))
    return {
        "sucesso": True,
        "de": str(src),
        "para": str(destino_final.resolve()),
    }


def ler_conteudo_ou_resumo(caminho_arquivo: str, limite_caracteres: int = 1500) -> dict:
    """Lê os primeiros caracteres ou trecho inicial de um documento para ajudar na classificação temática.

    Suporta:
      - Arquivos de texto (.txt, .md, .csv, .json, .log, .py, etc.)
      - PDF (.pdf via pypdf)
      - Word (.docx via python-docx)
      - Planilhas (.xlsx via openpyxl)
    Retorna aviso amigável para formatos binários ou não suportados.
    """
    p = Path(caminho_arquivo)
    if not p.exists() or not p.is_file():
        return {"erro": f"Arquivo não encontrado: {caminho_arquivo}"}

    ext = p.suffix.lower()

    # Formatos textuais puros
    extensoes_texto = {".txt", ".md", ".csv", ".json", ".log", ".py", ".html", ".xml", ".yaml", ".yml", ".ini"}
    if ext in extensoes_texto:
        try:
            conteudo = p.read_text(encoding="utf-8", errors="ignore")[:limite_caracteres]
            return {
                "tipo": "texto",
                "extensao": ext,
                "amostra": conteudo.strip(),
            }
        except Exception as exc:
            return {"erro": f"Não foi possível ler texto puro: {exc}"}

    # Leitura de PDF
    if ext == ".pdf":
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

    # Leitura de Word (.docx)
    if ext == ".docx":
        try:
            import docx
            doc = docx.Document(str(p))
            paragrafos = [p.text for p in doc.paragraphs if p.text.strip()]
            texto_unido = "\n".join(paragrafos)[:limite_caracteres]
            return {
                "tipo": "docx",
                "amostra": texto_unido.strip(),
            }
        except Exception as exc:
            return {"aviso": f"Falha ao ler DOCX ({exc}). Use os metadados para classificar."}

    # Leitura de Excel (.xlsx)
    if ext == ".xlsx":
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
            planilhas = wb.sheetnames
            primeira_aba = wb[planilhas[0]]
            linhas = []
            for row in primeira_aba.iter_rows(max_row=10, max_col=10, values_only=True):
                linha_filtrada = [str(cell) for cell in row if cell is not None]
                if linha_filtrada:
                    linhas.append(" | ".join(linha_filtrada))
            wb.close()
            return {
                "tipo": "xlsx",
                "planilhas": planilhas,
                "amostra": "\n".join(linhas)[:limite_caracteres].strip(),
            }
        except Exception as exc:
            return {"aviso": f"Falha ao ler XLSX ({exc}). Use os metadados para classificar."}

    # Formatos binários (ex: .jpg, .png, .zip, .exe)
    return {
        "aviso": f"Arquivo de formato '{ext}' não possui extrator de texto configurado. Classifique pelo nome, data e extensão.",
        "extensao": ext,
    }


FERRAMENTAS: list[ChatCompletionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "obter_pastas_padrao",
            "description": "Retorna os caminhos absolutos das pastas principais do usuário no Windows: Downloads, Documentos e Área de Trabalho (Desktop).",
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
            "description": "Lista os arquivos de um diretório com metadados: ano, mês, dia, extensão, tamanho e nome.",
            "parameters": {
                "type": "object",
                "properties": {
                    "diretorio": {
                        "type": "string",
                        "description": "Caminho do diretório a ser listado (ex: caminho de Downloads ou pasta específica).",
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Limite máximo de arquivos a listar (padrão 50).",
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
            "description": "Cria um diretório ou uma estrutura hierárquica de pastas no formato [Ano]/[Categoria]/[Mes]/[Dia].",
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
            "description": "Lê uma amostra do conteúdo inicial de um arquivo (texto, PDF, DOCX, XLSX) para auxiliar na classificação temática sem extrapolar a janela de contexto.",
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

EXECUTORES = {
    "obter_pastas_padrao": obter_pastas_padrao,
    "listar_arquivos": listar_arquivos,
    "criar_pasta": criar_pasta,
    "mover_arquivo": mover_arquivo,
    "ler_conteudo_ou_resumo": ler_conteudo_ou_resumo,
}


def executar_ferramenta(nome: str, argumentos: dict) -> str:
    """Executa uma ferramenta e devolve SEMPRE uma string (o modelo só lê texto).

    Erro vira mensagem de erro para o modelo, não crash do programa — assim
    ele consegue tentar outro caminho.
    """
    funcao = EXECUTORES.get(nome)
    if funcao is None:
        return json.dumps({"erro": f"Ferramenta '{nome}' não existe."}, ensure_ascii=False)
    try:
        return json.dumps(funcao(**argumentos), ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"erro": f"Falha em '{nome}': {exc}"}, ensure_ascii=False)


# ==========================================================================
# 4. O LOOP DO AGENTE
# ==========================================================================


def responder(mensagens: list[ChatCompletionMessageParam], verboso: bool = False) -> str:
    """O agente propriamente dito.

    O que diferencia um agente de uma simples chamada de API é ESTE loop:

        manda a conversa + as ferramentas para o modelo
          -> pediu ferramenta? executa, anexa o resultado, repete
          -> respondeu em texto?  acabou, essa é a resposta

    `mensagens` é modificada no lugar, então o histórico (incluindo as
    chamadas de ferramenta) fica preservado entre turnos.
    """
    cliente = get_cliente()

    for _ in range(MAX_ITERACOES):
        resposta = cliente.chat.completions.create(
            model=MODELO,
            messages=mensagens,
            tools=FERRAMENTAS,
            temperature=TEMPERATURA,
        )

        escolha = resposta.choices[0]
        mensagem = escolha.message

        if mensagem.tool_calls:
            mensagens.append(cast(ChatCompletionMessageParam, mensagem.model_dump()))

            for chamada in mensagem.tool_calls:
                nome = chamada.function.name
                try:
                    argumentos = json.loads(chamada.function.arguments)
                except json.JSONDecodeError:
                    argumentos = {}

                if verboso:
                    print(f"  [ferramenta] {nome}({argumentos})")

                resultado = executar_ferramenta(nome, argumentos)

                mensagens.append({
                    "role": "tool",
                    "tool_call_id": chamada.id,
                    "content": resultado,
                })
        else:
            conteudo = mensagem.content or ""
            mensagens.append({"role": "assistant", "content": conteudo})
            return conteudo

    return "Atingi o limite de iterações sem concluir. Tente reformular o pedido."


# ==========================================================================
# 5. O TERMINAL
# ==========================================================================


def main() -> None:
    """Interface de terminal mínima.

    Use para testar rápido, sem subir servidor web.
    """
    try:
        get_cliente()
    except RuntimeError as erro:
        print(f"\nErro: {erro}\n")
        sys.exit(1)

    print("=" * 60)
    print(" Agente Organizador de Arquivos")
    print(f" Modelo: {MODELO} | Digite 'sair' para encerrar")
    print("=" * 60)

    mensagens: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": carregar_contexto()}
    ]

    while True:
        try:
            pergunta = input("\nVocê: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAté logo!")
            break

        if not pergunta:
            continue
        if pergunta.lower() in {"sair", "exit", "quit"}:
            print("Até logo!")
            break

        mensagens.append({"role": "user", "content": pergunta})
        print("\nAgente: ", end="", flush=True)
        resposta = responder(mensagens, verboso=True)
        print(resposta)


if __name__ == "__main__":
    main()
