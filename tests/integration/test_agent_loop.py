"""Testes de Integração do Loop do Agente e Protocolo OpenAI Function Calling.

Conceito Didático para CI/CD:
Valida o orquestrador do agente (`agent.responder`) garantindo que as chamadas à API da OpenAI
ocorram com os hiperparâmetros corretos e que o ciclo ReAct (Reasoning + Acting) execute
corretamente a transição de múltiplos turnos entre solicitações de ferramentas e resposta final.
"""

import agent


def test_responder_texto_simples(mock_openai, criar_resposta_mock):
    """Testa o caso em que o LLM responde diretamente com texto, sem solicitar ferramentas."""
    # [ARRANGE] Prepara a resposta mockada do modelo para turno único
    mock_resposta = criar_resposta_mock(content="Olá, eu sou o Organizador de Arquivos!")
    mock_openai.chat.completions.create.return_value = mock_resposta

    mensagens = [{"role": "user", "content": "Oi"}]

    # [ACT] Invoca o orquestrador do loop do agente
    resultado = agent.responder(mensagens)

    # [ASSERT] Validações contratuais e de integridade do histórico
    assert resultado == "Olá, eu sou o Organizador de Arquivos!"
    assert len(mensagens) == 2
    assert mensagens[0] == {"role": "user", "content": "Oi"}
    assert mensagens[1] == {"role": "assistant", "content": "Olá, eu sou o Organizador de Arquivos!"}

    # Validação estrita dos argumentos passados para a API da OpenAI
    mock_openai.chat.completions.create.assert_called_once_with(
        model=agent.MODELO,
        messages=mensagens,
        tools=agent.FERRAMENTAS,
        temperature=agent.TEMPERATURA,
    )


def test_responder_com_ferramenta(mock_openai, monkeypatch, criar_resposta_mock, criar_tool_call_mock):
    """Testa o ciclo ReAct de 2 turnos:
    modelo solicita ferramenta -> agente executa localmente -> modelo sintetiza resposta final.

    Dinâmica dos Turnos:
    - Turno 1 (Reasoning / Tool Request): O LLM decide que precisa de dados do mundo real.
      Devolve content=None e emite tool_calls com a função a executar ('obter_pastas_padrao').
    - Ação Local (Acting): O orquestrador detecta tool_calls, executa deterministamente a função
      e anexa a mensagem de retorno com role='tool' e o respectivo tool_call_id.
    - Turno 2 (Synthesis / Final Text): O histórico completo é reenviado ao LLM, que sintetiza a resposta final.
    """
    # [ARRANGE]
    # 1. Isola a ferramenta real no dicionário EXECUTORES evitando chamadas ao Path.home real
    fake_pastas = {
        "downloads": "/sandbox/Downloads",
        "documentos": "/sandbox/Documents",
        "desktop": "/sandbox/Desktop",
    }
    monkeypatch.setitem(agent.EXECUTORES, "obter_pastas_padrao", lambda: fake_pastas)

    # 2. Configura o Turno 1: LLM solicita a execução de 'obter_pastas_padrao'
    mock_tc = criar_tool_call_mock(call_id="call_123", name="obter_pastas_padrao", arguments="{}")
    mock_resposta_1 = criar_resposta_mock(tool_calls=[mock_tc])

    # 3. Configura o Turno 2: LLM sintetiza a resposta final após ler os dados da ferramenta
    mock_resposta_2 = criar_resposta_mock(content="Identifiquei sua pasta Downloads com sucesso.")

    mock_openai.chat.completions.create.side_effect = [mock_resposta_1, mock_resposta_2]

    mensagens = [{"role": "user", "content": "Onde ficam meus downloads?"}]

    # [ACT]
    resultado = agent.responder(mensagens)

    # [ASSERT]
    assert resultado == "Identifiquei sua pasta Downloads com sucesso."

    # Validação da contagem de chamadas à OpenAI (exatamente 2 turnos)
    assert mock_openai.chat.completions.create.call_count == 2

    # Validação dos argumentos da 1ª chamada (Turno 1)
    chamada_1 = mock_openai.chat.completions.create.call_args_list[0]
    assert chamada_1.kwargs["model"] == agent.MODELO
    assert chamada_1.kwargs["tools"] == agent.FERRAMENTAS
    assert chamada_1.kwargs["temperature"] == agent.TEMPERATURA

    # Validação dos argumentos da 2ª chamada (Turno 2)
    chamada_2 = mock_openai.chat.completions.create.call_args_list[1]
    assert chamada_2.kwargs["model"] == agent.MODELO
    assert chamada_2.kwargs["tools"] == agent.FERRAMENTAS
    assert chamada_2.kwargs["temperature"] == agent.TEMPERATURA

    # Validação da estrutura sequencial e contratual do histórico de mensagens:
    # [0] user -> [1] assistant (tool_call) -> [2] tool (resultado com tool_call_id) -> [3] assistant (final)
    assert len(mensagens) == 4
    assert mensagens[0] == {"role": "user", "content": "Onde ficam meus downloads?"}
    assert mensagens[1]["role"] == "assistant"
    assert mensagens[2]["role"] == "tool"
    assert mensagens[2]["tool_call_id"] == "call_123"  # Contrato indispensável do protocolo OpenAI
    assert "downloads" in mensagens[2]["content"].lower()
    assert mensagens[3]["role"] == "assistant"
    assert mensagens[3]["content"] == "Identifiquei sua pasta Downloads com sucesso."
