"""
Teste de Validação Prática de Organização (Sandbox).
Simula o agente organizando arquivos em lote de acordo com as regras de agent.md e memory.md:
Hierarquia: [Ano] / [Categoria] / [Mes] / [Dia]
"""

from datetime import datetime
import json
import os
from unittest.mock import MagicMock
import agent


def test_cenario_completo_organizacao_sandbox(tmp_path, monkeypatch):
    """
    Simula uma pasta desorganizada (como Downloads) e valida a execução
    do loop do agente organizando os arquivos na estrutura obrigatória.
    """
    downloads_fake = tmp_path / "Downloads_Simulado"
    downloads_fake.mkdir()

    # Criação de arquivos com datas simuladas
    arquivos_simulados = [
        ("foto_torre_eiffel.jpg", 2025, 7, 14),
        ("comprovante_hotel_roma.pdf", 2025, 7, 18),
        ("relatorio_trabalho_q1.docx", 2026, 2, 10),
    ]

    for nome, ano, mes, dia in arquivos_simulados:
        p = downloads_fake / nome
        p.write_text("conteúdo fake", encoding="utf-8")
        dt = datetime(ano, mes, dia, 12, 0, 0)
        ts = dt.timestamp()
        os.utime(p, (ts, ts))

    # Mock do cliente OpenAI simulando as tomadas de decisão da IA
    mock_cliente = MagicMock()
    monkeypatch.setattr(agent, "_cliente", mock_cliente)

    # 1º Passo da IA: Listar os arquivos da pasta
    call_listar = MagicMock()
    call_listar.id = "call_1"
    call_listar.function.name = "listar_arquivos"
    call_listar.function.arguments = json.dumps({"diretorio": str(downloads_fake)})

    resp_1 = MagicMock()
    resp_1.choices[0].message.content = None
    resp_1.choices[0].message.tool_calls = [call_listar]
    resp_1.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "tool_calls": [{"id": "call_1", "function": {"name": "listar_arquivos", "arguments": call_listar.function.arguments}}]
    }

    # 2º Passo da IA: Mover os arquivos para a estrutura [Ano]/[Categoria]/[Mes]/[Dia]
    call_mover_1 = MagicMock()
    call_mover_1.id = "call_2"
    call_mover_1.function.name = "mover_arquivo"
    call_mover_1.function.arguments = json.dumps({
        "origem": str(downloads_fake / "foto_torre_eiffel.jpg"),
        "destino": str(tmp_path / "Organizados" / "2025" / "Fotos da viagem para europa" / "07" / "14")
    })

    call_mover_2 = MagicMock()
    call_mover_2.id = "call_3"
    call_mover_2.function.name = "mover_arquivo"
    call_mover_2.function.arguments = json.dumps({
        "origem": str(downloads_fake / "relatorio_trabalho_q1.docx"),
        "destino": str(tmp_path / "Organizados" / "2026" / "Documentos do trabalho" / "02" / "10")
    })

    resp_2 = MagicMock()
    resp_2.choices[0].message.content = None
    resp_2.choices[0].message.tool_calls = [call_mover_1, call_mover_2]
    resp_2.choices[0].message.model_dump.return_value = {
        "role": "assistant",
        "tool_calls": [
            {"id": "call_2", "function": {"name": "mover_arquivo", "arguments": call_mover_1.function.arguments}},
            {"id": "call_3", "function": {"name": "mover_arquivo", "arguments": call_mover_2.function.arguments}},
        ]
    }

    # 3º Passo da IA: Resposta final em texto
    resp_3 = MagicMock()
    resp_3.choices[0].message.tool_calls = None
    resp_3.choices[0].message.content = "Organização concluída com sucesso nas pastas de 2025 e 2026."

    mock_cliente.chat.completions.create.side_effect = [resp_1, resp_2, resp_3]

    # Execução do agente
    mensagens = [
        {"role": "system", "content": agent.carregar_contexto()},
        {"role": "user", "content": f"Por favor, organize os arquivos de {downloads_fake} na pasta {tmp_path / 'Organizados'}"}
    ]

    resposta_final = agent.responder(mensagens)

    # Asserções de Engenharia de Confiabilidade:
    # 1. Os arquivos de fato foram movidos no disco?
    assert (tmp_path / "Organizados" / "2025" / "Fotos da viagem para europa" / "07" / "14" / "foto_torre_eiffel.jpg").exists()
    assert (tmp_path / "Organizados" / "2026" / "Documentos do trabalho" / "02" / "10" / "relatorio_trabalho_q1.docx").exists()

    # 2. Não sobraram arquivos nas posições originais?
    assert not (downloads_fake / "foto_torre_eiffel.jpg").exists()
    assert not (downloads_fake / "relatorio_trabalho_q1.docx").exists()

    # 3. Resposta coerente com o encerramento?
    assert "concluída" in resposta_final.lower()
