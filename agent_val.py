"""
Perfil Val — Atendimento Nimbus Telecom (`agent-val.md`).

Fornece ferramentas determinísticas de base de conhecimento, consulta de status
de chamados e registro de escalonamento para internet fixa, mantendo isolamento
estrito de ferramentas e memória.
"""

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

import agent_core
from agent_core import SOMAR_TOOL_SCHEMA, somar

PERFIL_NOME: str = "agent-val.md"
AGENT_MD: Path = agent_core.RAIZ / PERFIL_NOME
MEMORIA_PADRAO: str = "Nenhuma preferência ou histórico específico registrado para este perfil."

LIMITE_HORAS_ESCALONAMENTO: int = 48

_PADRAO_PROTOCOLO = re.compile(r"^NT-\d{3,4}(?:-\d{3,4})?$")
_TOKEN_SEGREDO_EXPLICITO = (
    r"[!@#$%&*._+/()?~^-]*[^\W_]"
    r"(?:[\w@#$%&*+/=~^-]|[.!()?]+[\w@#$%&*+/=~^-])*(?!\w)"
)
_TOKEN_SEGREDO_DIGITO = (
    r"(?=[\w!@#$%&*._+/=~^-]*\d)"
    r"[!@#$%&*._+/~^-]*[^\W_]"
    r"(?:[\w@#$%&*+/=~^-]|[.!]+[\w@#$%&*+/=~^-])*(?!\w)"
)
_QUALIFICADOR_CREDENCIAL = (
    r"(?:\s+d[aeo]s?\s+"
    r"(?:(?:meu|minha|seu|sua)\s+)?"
    r"(?:wi-?fi|rede|roteador|modem|acesso|cart[aã]o|conta|cliente|"
    r"app|aplicativo|portal|seguran[cç]a|verifica[cç][aã]o|usu[aá]rio))?"
)
_PADRAO_CREDENCIAL_SENSIVEL = re.compile(
    r"(?i)\b(?:senha|password|cvv|cvc|token|pin|"
    r"c[oó]digo\s+(?:(?:de|do)\s+)?(?:2fa|dois\s+fatores)|2fa)\b"
    rf"{_QUALIFICADOR_CREDENCIAL}"
    r"(?:"
    r"\s*(?:[:=]|\bé\b(?:\s*[:=])?)\s*"
    rf'(?:"[^"\r\n]+"|\'[^\'\r\n]+\'|{_TOKEN_SEGREDO_EXPLICITO})'
    r"|"
    rf'\s+(?:"[^"\r\n]*\d[^"\r\n]*"|\'[^\'\r\n]*\d[^\'\r\n]*\'|{_TOKEN_SEGREDO_DIGITO})'
    r")"
)
_PADRAO_FOTO_DOCUMENTO = re.compile(
    r"(?i)\b(?:fotos?\s+(?:de|do|da|dos|das)\s+"
    r"(?:(?:meu|minha|meus|minhas|seu|sua|seus|suas|um|uma)\s+)?"
    r"(?:documentos?|rg|cnh|cpf|identidades?))\b"
)

_TERMOS_FORA_ESCOPO: tuple[str, ...] = (
    "telefonia movel",
    "internet movel",
    "celular",
    "celulares",
    "chip",
    "chips",
    "receita",
    "receitas",
    "bolo",
    "bolos",
    "opiniao politica",
    "tv por assinatura",
)

BASE_CONHECIMENTO: dict[str, dict[str, Any]] = {
    "planos": {
        "titulo": "Planos de Internet Fixa (Fibra Óptica)",
        "resumo": (
            "A Nimbus Telecom oferece planos de internet fixa em fibra óptica "
            "com franquia ilimitada e roteador Wi-Fi em comodato."
        ),
        "detalhes": [
            "Nimbus Fibra 300 Mega: 300 Mbps de download e 150 Mbps de upload.",
            "Nimbus Fibra 600 Mega: 600 Mbps de download e 300 Mbps de upload.",
            "Nimbus Fibra 1 Giga: 1000 Mbps de download e 500 Mbps de upload.",
            "Atendimento exclusivo para internet fixa; não há planos de telefonia móvel.",
        ],
        "orientacao_atendimento": (
            "Apresente uma informação por vez e confirme se o cliente deseja consultar preços ou cobertura."
        ),
    },
    "precos": {
        "titulo": "Preços Mensais dos Planos (Fictício)",
        "resumo": "Valores mensais vigentes dos planos de internet fixa da Nimbus Telecom.",
        "detalhes": [
            "Nimbus Fibra 300 Mega: R$ 99,90/mês.",
            "Nimbus Fibra 600 Mega: R$ 129,90/mês.",
            "Nimbus Fibra 1 Giga: R$ 179,90/mês.",
            "Instalação padrão sem custo adicional em endereços com viabilidade técnica confirmada.",
        ],
        "orientacao_atendimento": (
            "Nunca prometa descontos, isenções fora da tabela ou condições não registradas na base."
        ),
    },
    "sla": {
        "titulo": "SLA e Critérios de Prioridade",
        "resumo": "Regras de acompanhamento de chamados técnicos e limite de 48 horas em aberto.",
        "detalhes": [
            "Chamados técnicos recebem protocolo para acompanhamento desde a abertura.",
            "Qualquer chamado aberto há mais de 48 horas requer escalonamento obrigatório.",
            "O atendimento não pode prometer horário exato de normalização sem confirmação técnica.",
        ],
        "orientacao_atendimento": (
            "Se verificar horas_em_aberto > 48, acione registrar_escalonamento com motivo 'acima_48h'."
        ),
    },
    "prazos": {
        "titulo": "Prazos de Referência Operacional",
        "resumo": "Referências operacionais da Nimbus Telecom sujeitas à confirmação de agenda técnica.",
        "detalhes": [
            "Instalação em área viável: referência operacional de 3 a 5 dias úteis após agendamento.",
            "Atendimentos acima de 48 horas em aberto devem ser escalonados para análise prioritária.",
            "Não prometa prazos garantidos nem 'deve ser rápido' ao cliente.",
        ],
        "orientacao_atendimento": (
            "Informe apenas que a equipe responsável dará sequência, sem assumir compromisso de prazo."
        ),
    },
    "cobertura": {
        "titulo": "Cobertura e Viabilidade Técnica",
        "resumo": "Internet fixa por fibra óptica sujeita à viabilidade técnica no endereço.",
        "detalhes": [
            "Cobertura exclusiva para internet fixa residencial e comercial leve em fibra óptica.",
            "A confirmação depende de consulta de viabilidade pelo CEP e número do imóvel.",
            "Não solicite foto de comprovante de residência ou documento pessoal pelo chat.",
        ],
        "orientacao_atendimento": (
            "Se não houver confirmação de viabilidade na base, informe claramente que depende de verificação."
        ),
    },
    "cancelamento": {
        "titulo": "Política de Cancelamento",
        "resumo": "Pedidos de cancelamento exigem escalonamento obrigatório para a equipe responsável.",
        "detalhes": [
            "Todo pedido de cancelamento deve ser registrado via registrar_escalonamento(motivo='cancelamento').",
            "Não prometa isenção de valores, descontos de retenção ou estorno diretamente no chat.",
            "Confirme o pedido com respeito e informe que a equipe responsável fará a tratativa.",
        ],
        "orientacao_atendimento": (
            "Use uma etapa por vez, repita a solicitação com suas palavras e registre o escalonamento."
        ),
    },
    "suporte_modem": {
        "titulo": "Suporte Básico de Modem e Conexão",
        "resumo": "Verificações iniciais para lentidão, oscilação ou queda de internet fixa.",
        "detalhes": [
            "Verifique se os cabos de energia e de fibra óptica estão conectados sem dobras.",
            "Luz vermelha piscando (LOS) no modem indica falha de sinal óptico e exige chamado técnico.",
            "Se todas as luzes estiverem acesas e houver lentidão, reinicie o modem por 30 segundos.",
            "Nunca peça senha de Wi-Fi, senha de acesso do roteador, CVV, código 2FA ou foto de documento.",
        ],
        "orientacao_atendimento": (
            "Passe uma instrução por vez e peça confirmação do estado das luzes do modem antes de avançar."
        ),
    },
    "fatura": {
        "titulo": "Fatura e Cobrança Contestada",
        "resumo": "Orientações sobre segunda via de fatura e encaminhamento de cobranças contestadas.",
        "detalhes": [
            "A segunda via de fatura fica disponível na Área do Cliente do site oficial da Nimbus Telecom.",
            "Nunca solicite senha de acesso, CVV de cartão, código 2FA ou foto de documento no chat.",
            "Cobrança contestada deve ser escalonada com motivo 'cobranca_contestada', sem prometer estorno.",
        ],
        "orientacao_atendimento": (
            "Se o cliente contestar valor, registre escalonamento sem prometer desconto, isenção ou reembolso."
        ),
    },
    "escalonamento": {
        "titulo": "Critérios de Escalonamento",
        "resumo": "Situações que exigem transferência formal via registrar_escalonamento.",
        "detalhes": [
            "Motivos obrigatórios: cancelamento, cobranca_contestada, acima_48h e excecao_politica.",
            "Registre sempre motivo, resumo objetivo sem dados sensíveis e protocolo quando disponível.",
            "Explique ao cliente qual equipe receberá o caso sem inventar prazos ou benefícios.",
        ],
        "orientacao_atendimento": (
            "Nunca inclua senhas, CVV, códigos 2FA ou fotos de documentos no resumo do escalonamento."
        ),
    },
}

_ALIASES_KB: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cancelamento", ("cancelamento", "cancelamentos", "cancelar", "rescisao", "encerrar contrato")),
    ("fatura", (
        "fatura", "faturas", "boleto", "boletos", "pagamento", "cobranca",
        "cobrancas", "segunda via", "2a via", "vencimento", "vencimentos",
    )),
    ("suporte_modem", (
        "suporte_modem", "modem", "modems", "roteador", "roteadores", "wifi", "wi-fi", "wi fi",
        "sem conexao", "sem internet", "internet lenta", "internet caiu", "queda",
        "quedas", "caiu", "lentidao", "lentidoes", "lenta", "oscilacao", "oscilacoes",
        "luz vermelha", "los",
    )),
    ("sla", ("sla", "48h", "48 horas", "nivel de servico")),
    ("prazos", ("prazo", "prazos", "quanto tempo", "dias uteis", "demora")),
    ("precos", (
        "preco", "precos", "valor", "valores", "mensalidade", "mensalidades",
        "quanto custa", "instalacao", "instalacoes",
    )),
    ("cobertura", (
        "cobertura", "cep", "viabilidade", "disponibilidade", "endereco",
        "enderecos", "regiao", "regioes",
    )),
    ("escalonamento", (
        "escalonamento", "escalonamentos", "escalar", "excecao", "excecoes",
        "supervisor", "supervisores", "ouvidoria",
    )),
    ("planos", ("plano", "planos", "mega", "giga", "fibra", "velocidade", "velocidades", "internet", "banda larga")),
)

CHAMADOS_SIMULADOS: dict[str, dict[str, Any]] = {
    "NT-0001": {
        "protocolo": "NT-0001",
        "status": "em_andamento",
        "categoria": "lentidao_conexao",
        "horas_em_aberto": 14,
        "resumo_tecnico": "Análise remota de estabilidade do sinal óptico em andamento.",
        "equipe_responsavel": "Suporte N1",
    },
    "NT-101": {
        "protocolo": "NT-101",
        "status": "aberto",
        "categoria": "oscilacao_wifi",
        "horas_em_aberto": 36,
        "resumo_tecnico": "Aguardando retorno de diagnóstico remoto do roteador.",
        "equipe_responsavel": "Suporte N1",
    },
    "NT-2026-048": {
        "protocolo": "NT-2026-048",
        "status": "aberto",
        "categoria": "queda_total",
        "horas_em_aberto": 48,
        "resumo_tecnico": "Chamado no limite de 48h em acompanhamento técnico.",
        "equipe_responsavel": "Suporte N2",
    },
    "NT-2026-100": {
        "protocolo": "NT-2026-100",
        "status": "aberto",
        "categoria": "sem_conexao",
        "horas_em_aberto": 60,
        "resumo_tecnico": "Sem conexão com luz vermelha no modem (LOS) acima de 48 horas.",
        "equipe_responsavel": "Suporte N2",
    },
    "NT-2026-205": {
        "protocolo": "NT-2026-205",
        "status": "aberto",
        "categoria": "cobranca_contestada",
        "horas_em_aberto": 72,
        "resumo_tecnico": "Contestação de cobrança em fatura pendente de auditoria.",
        "equipe_responsavel": "Faturamento",
    },
    "NT-2026-300": {
        "protocolo": "NT-2026-300",
        "status": "concluido",
        "categoria": "instalacao",
        "horas_em_aberto": 20,
        "resumo_tecnico": "Instalação concluída e sinal validado.",
        "equipe_responsavel": "Ativação",
    },
}

MOTIVOS_ESCALONAMENTO: dict[str, dict[str, str]] = {
    "cancelamento": {
        "area_destino": "Equipe de Retenção e Cancelamento",
        "proximo_passo": (
            "A solicitação foi encaminhada para a equipe de retenção e cancelamento "
            "dar continuidade ao atendimento pelos canais oficiais."
        ),
    },
    "cobranca_contestada": {
        "area_destino": "Equipe de Faturamento e Contestação",
        "proximo_passo": (
            "A contestação foi encaminhada para análise técnica do faturamento, "
            "sem promessa prévia de abatimento ou devolução."
        ),
    },
    "acima_48h": {
        "area_destino": "Suporte Técnico Especializado N2",
        "proximo_passo": (
            "O atendimento foi encaminhado com prioridade para a equipe técnica N2 "
            "por superar 48 horas em aberto."
        ),
    },
    "excecao_politica": {
        "area_destino": "Supervisão Operacional",
        "proximo_passo": (
            "O pedido de exceção foi encaminhado para avaliação da supervisão operacional, "
            "sem garantia prévia de aprovação."
        ),
    },
}

_ALIASES_MOTIVO: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cancelamento", ("cancelamento", "cancelamentos", "cancelar", "rescisao")),
    ("cobranca_contestada", (
        "cobranca_contestada", "cobranca", "cobrancas", "contestada", "contestadas",
        "contestacao", "contestacoes", "fatura", "faturas", "estorno", "estornos",
    )),
    ("acima_48h", ("acima_48h", "48h", "48 horas", "mais de 48", "acima de 48", "sla")),
    ("excecao_politica", (
        "excecao_politica", "excecao", "excecoes", "politica", "politicas", "excecao a regra",
    )),
)


def _normalizar_texto(texto: str) -> str:
    """Remove acentos, converte para minúsculas e normaliza espaços."""
    sem_acentos = "".join(
        ch for ch in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(ch)
    )
    return " ".join(sem_acentos.lower().strip().split())


def _sanitizar_dados_sensiveis(texto: str) -> tuple[str, bool]:
    """Remove eventuais credenciais, CVV, 2FA ou menções a fotos de documento."""
    texto_nfc = unicodedata.normalize("NFC", texto)
    limpo = _PADRAO_CREDENCIAL_SENSIVEL.sub("[DADO SENSÍVEL REMOVIDO]", texto_nfc)
    limpo = _PADRAO_FOTO_DOCUMENTO.sub("[DOCUMENTO REMOVIDO]", limpo)
    if limpo == texto_nfc:
        return texto, False
    return limpo, True


def _contem_termo(texto_norm: str, termo: str) -> bool:
    """Verifica ocorrência de termo completo com fronteiras alfanuméricas."""
    return re.search(rf"(?<![a-z0-9]){re.escape(termo)}(?![a-z0-9])", texto_norm) is not None


def _resolver_topico_kb(consulta_norm: str) -> str | None:
    """Resolve uma consulta normalizada para chave da KB ou None se fora de escopo."""
    if not consulta_norm:
        return None
    if any(_contem_termo(consulta_norm, termo) for termo in _TERMOS_FORA_ESCOPO):
        return None
    chave_direta = consulta_norm.replace(" ", "_").replace("-", "_")
    if chave_direta in BASE_CONHECIMENTO:
        return chave_direta
    for chave, termos in _ALIASES_KB:
        if any(_contem_termo(consulta_norm, termo) for termo in termos):
            return chave
    return None


def _resolver_motivo_escalonamento(motivo_norm: str) -> str | None:
    """Resolve um motivo normalizado para um dos 4 códigos oficiais ou None."""
    if not motivo_norm:
        return None
    chave_direta = motivo_norm.replace(" ", "_").replace("-", "_")
    if chave_direta in MOTIVOS_ESCALONAMENTO:
        return chave_direta
    for chave, termos in _ALIASES_MOTIVO:
        if any(_contem_termo(motivo_norm, termo) for termo in termos):
            return chave
    return None


def consultar_base_conhecimento(topico: str) -> dict:
    """Consulta a base de conhecimento oficial (fictícia) da Nimbus Telecom."""
    if not isinstance(topico, str):
        return {
            "encontrado": False,
            "topico": None,
            "mensagem": "Informe o tópico da consulta em texto.",
            "topicos_disponiveis": list(BASE_CONHECIMENTO.keys()),
        }

    consulta_sanitizada, dado_sensivel = _sanitizar_dados_sensiveis(topico.strip())
    consulta_norm = _normalizar_texto(consulta_sanitizada)
    chave = _resolver_topico_kb(consulta_norm)

    if chave is None:
        return {
            "encontrado": False,
            "topico": None,
            "consulta_original": consulta_sanitizada,
            "escopo": "internet fixa (Nimbus Telecom)",
            "mensagem": (
                "Informação não localizada na base de conhecimento de internet fixa da Nimbus Telecom. "
                "Não improvise preços, prazos, cobertura ou políticas."
            ),
            "topicos_disponiveis": list(BASE_CONHECIMENTO.keys()),
            "dado_sensivel_removido": dado_sensivel,
        }

    entrada = BASE_CONHECIMENTO[chave]
    return {
        "encontrado": True,
        "topico": chave,
        "consulta_original": consulta_sanitizada,
        "titulo": entrada["titulo"],
        "resumo": entrada["resumo"],
        "detalhes": list(entrada["detalhes"]),
        "orientacao_atendimento": entrada["orientacao_atendimento"],
        "empresa": "Nimbus Telecom (fictícia)",
        "dado_sensivel_removido": dado_sensivel,
    }


def verificar_status_chamado(protocolo: str) -> dict:
    """Verifica o status de um chamado técnico simulado e sinaliza escalonamento acima de 48h."""
    if not isinstance(protocolo, str) or not protocolo.strip():
        return {
            "encontrado": False,
            "protocolo": "",
            "horas_em_aberto": 0,
            "requer_escalonamento": False,
            "mensagem": "Protocolo não informado. Solicite o número no padrão NT-XXXX.",
        }

    protocolo_sanitizado, dado_sensivel = _sanitizar_dados_sensiveis(protocolo.strip())
    codigo = protocolo_sanitizado.upper()
    chamado = CHAMADOS_SIMULADOS.get(codigo)

    if chamado is None:
        formato_valido = bool(_PADRAO_PROTOCOLO.match(codigo))
        return {
            "encontrado": False,
            "formato_valido": formato_valido,
            "protocolo": codigo,
            "horas_em_aberto": 0,
            "requer_escalonamento": False,
            "mensagem": (
                "Chamado não localizado na base da Nimbus Telecom."
                if formato_valido
                else "Formato de protocolo inválido ou não localizado (esperado padrão NT-XXXX)."
            ),
            "dado_sensivel_removido": dado_sensivel,
        }

    horas = int(chamado["horas_em_aberto"])
    requer_escalonamento = chamado["status"] != "concluido" and horas > LIMITE_HORAS_ESCALONAMENTO
    return {
        "encontrado": True,
        "protocolo": chamado["protocolo"],
        "status": chamado["status"],
        "categoria": chamado["categoria"],
        "horas_em_aberto": horas,
        "limite_sla_horas": LIMITE_HORAS_ESCALONAMENTO,
        "requer_escalonamento": requer_escalonamento,
        "motivo_escalonamento_sugerido": "acima_48h" if requer_escalonamento else None,
        "equipe_responsavel": chamado["equipe_responsavel"],
        "resumo_tecnico": chamado["resumo_tecnico"],
        "orientacao": (
            "Chamado acima de 48 horas em aberto: registre escalonamento imediato com registrar_escalonamento."
            if requer_escalonamento
            else "Chamado dentro da janela regular; não prometa prazo fechado ao cliente."
        ),
        "dado_sensivel_removido": dado_sensivel,
    }


def registrar_escalonamento(motivo: str, resumo: str, protocolo: str = "") -> dict:
    """Valida motivo e registra escalonamento estruturado sem prometer prazo, desconto ou reembolso."""
    motivo_txt = motivo.strip() if isinstance(motivo, str) else ""
    resumo_txt = resumo.strip() if isinstance(resumo, str) else ""
    protocolo_txt = protocolo.strip() if isinstance(protocolo, str) else ""

    motivo_limpo, sensivel_motivo = _sanitizar_dados_sensiveis(motivo_txt)
    motivo_canonico = _resolver_motivo_escalonamento(_normalizar_texto(motivo_limpo))
    if motivo_canonico is None:
        return {
            "registrado": False,
            "erro": (
                "Motivo de escalonamento inválido ou ausente. "
                "Informe um dos motivos válidos: cancelamento, cobranca_contestada, acima_48h, excecao_politica."
            ),
            "motivos_validos": list(MOTIVOS_ESCALONAMENTO.keys()),
        }

    resumo_limpo, sensivel_resumo = _sanitizar_dados_sensiveis(resumo_txt)
    if not resumo_limpo:
        return {
            "registrado": False,
            "erro": "Informe um resumo objetivo do atendimento para registrar o escalonamento.",
            "motivo": motivo_canonico,
            "motivos_validos": list(MOTIVOS_ESCALONAMENTO.keys()),
        }

    protocolo_limpo, sensivel_proto = _sanitizar_dados_sensiveis(protocolo_txt)
    protocolo_final = protocolo_limpo.upper() if protocolo_limpo else "NÃO INFORMADO"
    info_motivo = MOTIVOS_ESCALONAMENTO[motivo_canonico]

    digest = hashlib.sha256(
        f"{motivo_canonico}|{protocolo_final}|{resumo_limpo}".encode("utf-8")
    ).hexdigest()[:6].upper()

    return {
        "registrado": True,
        "id_escalonamento": f"ESC-{digest}",
        "status": "escalonado",
        "motivo": motivo_canonico,
        "motivo_informado": motivo_limpo,
        "protocolo": protocolo_final,
        "area_destino": info_motivo["area_destino"],
        "resumo": resumo_limpo,
        "proximo_passo": info_motivo["proximo_passo"],
        "promessa_sla_ou_desconto": False,
        "aviso_politica": (
            "Não assuma compromissos de prazo fechado, desconto, isenção ou reembolso."
        ),
        "dado_sensivel_removido": sensivel_motivo or sensivel_resumo or sensivel_proto,
    }


FERRAMENTAS: list[ChatCompletionToolParam] = [
    SOMAR_TOOL_SCHEMA,
    {
        "type": "function",
        "function": {
            "name": "consultar_base_conhecimento",
            "description": (
                "Consulta a base de conhecimento oficial da Nimbus Telecom (internet fixa) "
                "sobre planos, preços, SLA, prazos, cobertura, cancelamento, suporte de modem, "
                "fatura e regras de escalonamento."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topico": {
                        "type": "string",
                        "description": (
                            "Tópico ou palavra-chave da consulta (ex.: planos, precos, sla, "
                            "prazos, cobertura, cancelamento, suporte_modem, fatura, escalonamento)."
                        ),
                    },
                },
                "required": ["topico"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verificar_status_chamado",
            "description": (
                "Consulta o status de um chamado técnico pelo número de protocolo da Nimbus Telecom, "
                "retornando horas em aberto e se requer escalonamento (acima de 48 horas)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "protocolo": {
                        "type": "string",
                        "description": "Número de protocolo do chamado (ex.: NT-0001 ou NT-2026-100).",
                    },
                },
                "required": ["protocolo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_escalonamento",
            "description": (
                "Registra o escalonamento do atendimento para equipe especialista quando o caso envolver "
                "cancelamento, cobrança contestada, chamado acima de 48 horas ou exceção à regra, "
                "sem prometer descontos, reembolsos ou prazos fechados."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "motivo": {
                        "type": "string",
                        "description": (
                            "Motivo do escalonamento: cancelamento, cobranca_contestada, "
                            "acima_48h ou excecao_politica."
                        ),
                    },
                    "resumo": {
                        "type": "string",
                        "description": (
                            "Resumo objetivo do atendimento sem senhas, CVV, códigos 2FA ou fotos de documento."
                        ),
                    },
                    "protocolo": {
                        "type": "string",
                        "description": "Número de protocolo associado, quando houver.",
                    },
                },
                "required": ["motivo", "resumo"],
            },
        },
    },
]

EXECUTORES: dict[str, Callable[..., Any]] = {
    "somar": somar,
    "consultar_base_conhecimento": consultar_base_conhecimento,
    "verificar_status_chamado": verificar_status_chamado,
    "registrar_escalonamento": registrar_escalonamento,
}


def carregar_contexto() -> str:
    """Carrega `agent-val.md` com `# Memória` neutra, sem vazar `memory.md` do Organizador."""
    return agent_core.carregar_contexto(
        AGENT_MD,
        memory_md=None,
        memoria_padrao=MEMORIA_PADRAO,
    )


def executar_ferramenta(nome: str, argumentos: dict) -> str:
    """Executa apenas ferramentas permitidas ao perfil Val."""
    return agent_core.executar_ferramenta(nome, argumentos, EXECUTORES)


def responder(mensagens: list[ChatCompletionMessageParam], verboso: bool = False) -> str:
    """Executa o loop ReAct compartilhado com isolamento estrito das ferramentas da Val."""
    return agent_core.executar_loop_react(
        mensagens,
        FERRAMENTAS,
        EXECUTORES,
        verboso=verboso,
    )
