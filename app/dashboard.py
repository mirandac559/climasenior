# -*- coding: utf-8 -*-
"""
Dashboard ClimaSênior (Streamlit + Plotly + Folium).

Execução:  streamlit run app/dashboard.py
Requer modelo treinado: python -m climasenior.pipeline
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import folium
from streamlit.components.v1 import html as st_html

from climasenior.config import DIR_MODELOS, MUNICIPIOS_RM, FAIXAS_IVC, faixa_ivc

st.set_page_config(page_title="ClimaSênior", page_icon="🌡️", layout="wide")


@st.cache_data
def carregar(versao="v1"):
    ivc = pd.read_parquet(DIR_MODELOS / f"ivc_{versao}.parquet")
    resumo = json.load(open(DIR_MODELOS / f"resumo_{versao}.json", encoding="utf-8"))
    return ivc, resumo


try:
    ivc, resumo = carregar()
except FileNotFoundError:
    st.error("Modelo não treinado. Execute `python -m climasenior.pipeline` e recarregue.")
    st.stop()

# ------------------------------------------------------------------ cabeçalho
st.title("ClimaSênior")
st.caption("Índice de Vulnerabilidade Climática para a saúde da população idosa · Região Metropolitana de São Luís (MA)")
if resumo.get("modo") == "demo":
    st.warning("**Modo de demonstração.** Dados sintéticos; os valores exibidos não constituem resultados científicos.")

# ------------------------------------------------------------------ barra lateral
datas = sorted(ivc["data"].unique())
with st.sidebar:
    st.header("Controles")
    data_ref = st.select_slider("Data de referência", options=datas, value=datas[-1],
                                format_func=lambda d: pd.Timestamp(d).strftime("%d/%m/%Y"))
    limiar = st.slider("Limiar de ação (IVC)", 0, 100, 60, 5,
                       help="Valor a partir do qual o protocolo de resposta é acionado. Pactuável com gestores.")
    st.markdown("---")
    st.markdown("**Faixas do IVC**")
    for a, b, rot, cor, _ in FAIXAS_IVC:
        st.markdown(f'<span style="display:inline-block;width:12px;height:12px;background:{cor};'
                    f'border-radius:2px;margin-right:6px"></span>{rot} ({a}–{min(b,100)})', unsafe_allow_html=True)

hoje = ivc[ivc["data"] == data_ref].copy()
hoje["faixa"] = hoje["IVC"].map(lambda v: faixa_ivc(v)[0])
hoje["cor"] = hoje["IVC"].map(lambda v: faixa_ivc(v)[1])

# ------------------------------------------------------------------ indicadores
c1, c2, c3, c4 = st.columns(4)
c1.metric("Municípios em alerta", int((hoje["IVC"] >= limiar).sum()), f"de {len(hoje)}")
c2.metric("IVC máximo", f"{hoje['IVC'].max():.0f}", hoje.loc[hoje["IVC"].idxmax(), "municipio"])
c3.metric("Tmáx média", f"{hoje['tmax'].mean():.1f} °C")
c4.metric("Demanda prevista D+3", f"{hoje['demanda_prevista_d3'].sum():.0f}", "atendimentos (soma)")

aba1, aba2, aba3, aba4 = st.tabs(["Situação", "Série temporal", "Protocolo", "Validação (Fase 3)"])

# ------------------------------------------------------------------ situação
with aba1:
    col_mapa, col_tab = st.columns([3, 2])
    with col_mapa:
        m = folium.Map(location=[-2.72, -44.20], zoom_start=9, tiles="CartoDB positron")
        for _, r in hoje.iterrows():
            info = MUNICIPIOS_RM[r["cod_ibge"]]
            folium.CircleMarker(
                [info["lat"], info["lon"]], radius=6 + r["IVC"] / 8,
                color=r["cor"], fill=True, fill_color=r["cor"], fill_opacity=0.75,
                tooltip=f"<b>{r['municipio']}</b><br>IVC {r['IVC']:.0f} · {r['faixa']}<br>"
                        f"Tmáx {r['tmax']:.1f} °C · demanda D+3 {r['demanda_prevista_d3']:.0f}",
            ).add_to(m)
        st_html(m._repr_html_(), height=460)
    with col_tab:
        st.markdown(f"**Painel de situação — {pd.Timestamp(data_ref):%d/%m/%Y}**")
        tab = hoje.sort_values("IVC", ascending=False)[
            ["municipio", "IVC", "faixa", "tmax", "dias_consec_calor", "demanda_prevista_d3"]]
        tab.columns = ["Município", "IVC", "Faixa", "Tmáx (°C)", "Dias consec.", "Demanda D+3"]
        st.dataframe(tab, hide_index=True, width='stretch', height=460)

# ------------------------------------------------------------------ série temporal
with aba2:
    mun = st.selectbox("Município", options=list(MUNICIPIOS_RM.keys()),
                       format_func=lambda c: MUNICIPIOS_RM[c]["nome"])
    ini = st.date_input("Início", value=pd.Timestamp("2025-09-01"))
    serie = ivc[(ivc["cod_ibge"] == mun) & (ivc["data"] >= pd.Timestamp(ini))].sort_values("data")

    fig = go.Figure()
    for a, b, rot, cor, _ in FAIXAS_IVC:
        fig.add_hrect(y0=a, y1=min(b, 100), fillcolor=cor, opacity=0.10, line_width=0)
    fig.add_trace(go.Scatter(x=serie["data"], y=serie["IVC"], name="IVC", mode="lines",
                             line=dict(color="#0E5F8A", width=2.5)))
    fig.add_trace(go.Scatter(x=serie["data"], y=serie["tmax"], name="Tmáx (°C)", yaxis="y2",
                             mode="lines", line=dict(color="#E07B2A", width=1.2, dash="dot")))
    fig.add_trace(go.Bar(x=serie["data"], y=serie["atend_idosos"], name="Atendimentos observados",
                         yaxis="y3", marker_color="rgba(120,120,120,0.35)"))
    fig.add_hline(y=limiar, line_dash="dash", line_color="#CF3F38", annotation_text=f"limiar {limiar}")
    fig.update_layout(height=460, margin=dict(l=40, r=40, t=30, b=40), legend_orientation="h",
                      yaxis=dict(title="IVC", range=[0, 100]),
                      yaxis2=dict(title="Tmáx (°C)", overlaying="y", side="right", showgrid=False),
                      yaxis3=dict(overlaying="y", side="right", position=0.98, showgrid=False,
                                  showticklabels=False))
    st.plotly_chart(fig, width='stretch')

# ------------------------------------------------------------------ protocolo
with aba3:
    st.markdown("**Protocolo de resposta graduada**")
    st.caption("Proposta a ser pactuada com gestores de saúde e defesa civil na Fase 3.")
    for a, b, rot, cor, cond in FAIXAS_IVC:
        st.markdown(f'<div style="border-left:6px solid {cor};padding:8px 12px;margin:6px 0;'
                    f'background:#fafafa"><b>{rot}</b> ({a}–{min(b,100)}) — {cond}</div>',
                    unsafe_allow_html=True)
    st.markdown("**Recomendações de hoje**")
    for _, r in hoje.sort_values("IVC", ascending=False).iterrows():
        if r["IVC"] >= limiar:
            rot, cor, cond = faixa_ivc(r["IVC"])
            st.markdown(f'<span style="color:{cor}"><b>{r["municipio"]}</b> (IVC {r["IVC"]:.0f}, {rot})</span>: {cond}',
                        unsafe_allow_html=True)

# ------------------------------------------------------------------ validação
with aba4:
    bt = resumo["backtesting_2025"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Episódios de calor (2025)", bt["n_episodios"])
    c2.metric("Detectados", bt["episodios_detectados"], f"sensibilidade {bt['sensibilidade_episodios']:.0%}")
    c3.metric("Antecedência média", f"{bt['antecedencia_media_dias']} d")
    c4.metric("Taxa de falso alarme", f"{bt['taxa_falso_alarme']:.1%}")

    st.markdown("**Curva de limiares — sensibilidade × falso alarme**")
    st.caption("Cada ponto é um limiar de ação possível. A escolha é normativa: errar para menos custa vidas, errar para mais custa recursos e confiança.")
    cl = pd.DataFrame(resumo["curva_limiares"])
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=cl["limiar"], y=cl["sensibilidade"], name="Sensibilidade",
                              mode="lines+markers", line=dict(color="#0E5F8A", width=2.5)))
    fig2.add_trace(go.Scatter(x=cl["limiar"], y=cl["taxa_falso_alarme"], name="Taxa de falso alarme",
                              mode="lines+markers", line=dict(color="#CF3F38", width=2.5)))
    fig2.update_layout(height=340, xaxis_title="Limiar de ação (IVC)", yaxis=dict(range=[0, 1.05]),
                       legend_orientation="h", margin=dict(l=40, r=20, t=20, b=40))
    st.plotly_chart(fig2, width='stretch')

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Métricas por período**")
        st.dataframe(pd.DataFrame({k: v for k, v in resumo["metricas"].items()
                                   if k in ("validacao", "teste_2025")}), width='stretch')
    with col_b:
        st.markdown("**Importância das variáveis (Random Forest)**")
        imp = pd.DataFrame(resumo["metricas"]["importancia_variaveis"]).head(8)
        st.bar_chart(imp.set_index("variavel"))
    d = resumo["drift"]
    if d["retreinar"]:
        st.warning(f"**Deriva detectada** em: {', '.join(d['variaveis_com_deriva'])} (PSI > {d['limite_psi']}). Retreinamento recomendado.")
    else:
        st.success("Sem deriva relevante nos atributos.")
    st.caption(resumo.get("_aviso", ""))
