"""
Interface web mínima, em Streamlit.

Este arquivo é SÓ interface. Toda a lógica está no agent.py.
A regra que vale a pena manter enquanto o projeto cresce:

    agent.py = o agente        (terminal, teste, servidor)
    app.py   = uma das caras   (Streamlit hoje; amanhã uma API)

Rode com:  streamlit run app.py
"""

import streamlit as st
from streamlit.runtime import exists as st_runtime_ativo

import agent
import agent_core

OPCOES_PERFIL: dict[str, str | None] = {
    "Padrão (agent.py)": None,
    "Base (agent.md)": "agent.md",
    "Ada (agent-ada.md)": "agent-ada.md",
    "Lint (agent-lint.md)": "agent-lint.md",
    "Val (agent-val.md)": "agent-val.md",
    "Organizador (agent-organizador.md)": "agent-organizador.md",
}


def _resolver_modulo_perfil(rotulo: str):
    """Resolve o módulo do perfil selecionado, com fallback seguro para `agent`."""
    arquivo_perfil = OPCOES_PERFIL.get(rotulo)
    if arquivo_perfil is None:
        return rotulo, agent, None
    try:
        modulo = agent_core.obter_modulo_perfil(arquivo_perfil)
        return rotulo, modulo, None
    except (ImportError, ValueError) as exc:
        aviso = f"Perfil '{rotulo}' indisponível no momento ({exc}). Usando 'Padrão (agent.py)'."
        return "Padrão (agent.py)", agent, aviso


# Um app Streamlit precisa ser iniciado pelo comando `streamlit run`. Com
# `python app.py` o script roda sem o runtime: nada aparece na tela e o
# terminal vira uma parede de "missing ScriptRunContext".
if not st_runtime_ativo():
    print("\nEste arquivo é um app Streamlit — não rode com `python app.py`.\n")
    print("Use:\n    streamlit run app.py\n")
    print("Para a versão de terminal, rode:  python agent.py\n")
    raise SystemExit(1)

st.set_page_config(page_title="Agente base", page_icon="🤖")
st.title("🤖 Agente base")

# A chave é checada aqui. get_cliente() é preguiçoso justamente para que
# este arquivo possa mostrar um erro na tela em vez de uma stack trace.
try:
    agent.get_cliente()
except RuntimeError as erro:
    st.error(str(erro))
    st.stop()

# --------------------------------------------------------------------------
# ESTADO
# --------------------------------------------------------------------------
# O Streamlit re-executa este arquivo INTEIRO a cada interação. Tudo que
# precisa sobreviver a isso mora em st.session_state.
#
# São duas listas, de propósito:
#   mensagens -> histórico no formato da API (inclui as chamadas de ferramenta)
#   tela      -> o que o usuário vê (não mostramos JSON de ferramenta na tela)

with st.sidebar:
    perfil_escolhido = st.selectbox(
        "Perfil do agente",
        list(OPCOES_PERFIL.keys()),
        index=0,
        key="perfil_selecionado",
    )
    perfil_efetivo, modulo_ativo, aviso_perfil = _resolver_modulo_perfil(perfil_escolhido)
    if aviso_perfil:
        st.warning(aviso_perfil)
    st.caption(f"Modelo: `{agent.MODELO}`")

if "mensagens" not in st.session_state or st.session_state.get("perfil_ativo") != perfil_efetivo:
    st.session_state.perfil_ativo = perfil_efetivo
    st.session_state.mensagens = [{"role": "system", "content": modulo_ativo.carregar_contexto()}]
    st.session_state.tela = []

with st.sidebar:
    if st.button("Nova conversa", use_container_width=True):
        st.session_state.mensagens = [{"role": "system", "content": modulo_ativo.carregar_contexto()}]
        st.session_state.tela = []
        st.rerun()

# --------------------------------------------------------------------------
# HISTÓRICO
# --------------------------------------------------------------------------

for papel, texto in st.session_state.tela:
    with st.chat_message(papel):
        st.markdown(texto)

# --------------------------------------------------------------------------
# NOVO TURNO
# --------------------------------------------------------------------------

pergunta = st.chat_input("Escreva sua mensagem")

if pergunta:
    st.session_state.tela.append(("user", pergunta))
    st.session_state.mensagens.append({"role": "user", "content": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)

    # Marca onde a resposta começa. Se der erro no meio, tudo daqui para a
    # frente é descartado — senão sobraria uma chamada de ferramenta sem
    # resultado no histórico, e a PRÓXIMA chamada quebraria por causa disso.
    marca = len(st.session_state.mensagens)

    with st.chat_message("assistant"), st.spinner("Pensando..."):
        try:
            resposta = modulo_ativo.responder(st.session_state.mensagens)
            st.markdown(resposta)
            st.session_state.tela.append(("assistant", resposta))
        except Exception as erro:
            del st.session_state.mensagens[marca:]
            st.error(f"Erro ao chamar o modelo: {erro}")
