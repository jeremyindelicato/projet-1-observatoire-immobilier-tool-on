import plotly.express as px
import streamlit as st

from app.components.ui import (
    apply_custom_css,
    get_plotly_template,
    initialize_session_state,
    kpi_card,
    page_header,
    section_title,
    sidebar_logo,
    topbar,
)
from app.services.data_provider import get_listings, get_listings_metadata, get_sales
from app.services.metrics import (
    build_listing_market_summary,
    build_listing_trend,
    compute_opportunity_scores,
    compute_trend_insights,
    filter_by_period,
    get_data_status,
    get_kpis,
)

st.set_page_config(page_title="Accueil - ToolOn", layout="wide", initial_sidebar_state="expanded")

initialize_session_state()
apply_custom_css()
sidebar_logo()
topbar("Vue d'ensemble")

period = st.session_state.get("periode", "12 derniers mois")
sales_df = get_sales()
base_listings = get_listings()
trend_df = build_listing_trend(base_listings)
meta = get_listings_metadata()
listings_df = filter_by_period(base_listings, "date_ajout", period)
status = get_data_status(listings_df, sales_df, trends_df=trend_df, listings_metadata=meta)
scored_listings = compute_opportunity_scores(listings_df, sales_df, status=status)
kpis = get_kpis(period, listings_metadata=meta, trends_df=trend_df)

page_header(export_df=scored_listings, export_filename="accueil_annonces.csv")

if not status["has_real_listings"]:
    st.info("Mode fallback: le CSV réel n'est pas reconnu, les métriques dépendent encore des mock internes.")

status_items = [
    ("Listings", status["has_real_listings"], "CSV réel détecté" if status["has_real_listings"] else "Manquant"),
    ("Quartiers", status["has_quartier"], "OK" if status["has_quartier"] else "Partiel"),
    ("Dates", status["has_dates"], "OK" if status["has_dates"] else "Manquant"),
    ("DVF", status["has_dvf"], "Non connecté"),
    (
        "Score opp.",
        status["score_ready"],
        "Calculable" if status["score_ready"] else "N/A - Quartier/Dates",
    ),
]
with st.container():
    st.markdown("<div class='section-title'>Qualité des données</div>", unsafe_allow_html=True)
    cols = st.columns(len(status_items))
    for col, (label, ok, note) in zip(cols, status_items):
        state = "OK" if ok else "Manquant"
        col.markdown(
            f"""
        <div class='data-status-card'>
            <div class='status-chip'>{label}</div>
            <div class='status-value'>{state}</div>
            <div class='status-note'>{note}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

col1, col2, col3, col4 = st.columns(4)
with col1:
    kpi_card("Annonces actives", f"{kpis['annonces_actives']}", kpis["trend_annonces"], note="Listings - mise à jour csv")
with col2:
    price_note = f"Source: {kpis.get('prix_source', 'Listings')}"
    kpi_card("Prix médian / m²", f"{kpis['prix_median']} €", kpis.get("trend_prix"), note=price_note)
with col3:
    avg_score = None
    if status["score_ready"]:
        non_null_scores = scored_listings["score_opportunite"].dropna()
        if not non_null_scores.empty:
            avg_score = round(float(non_null_scores.mean()), 1)
    score_value = f"{avg_score}/100" if avg_score is not None else "N/A"
    score_note = (
        "Calculé (DVF)" if status["has_dvf"] else "Calculé (Listings)"
        if status["score_ready"]
        else "À connecter: quartiers + dates"
    )
    kpi_card("Score opportunité moyen", score_value, note=score_note)
with col4:
    delay_value = f"{kpis['delai_vente']} j" if kpis.get("delai_vente") else "N/A"
    delay_note = None if kpis.get("delai_vente") else "À connecter: DVF"
    kpi_card("Délai de vente estimé", delay_value, note=delay_note)

st.markdown("<div style='height: 0.6rem;'></div>", unsafe_allow_html=True)

col_chart1, col_chart2 = st.columns(2)
with col_chart1:
    section_title("Prix moyen par quartier (€/m²)")
    if scored_listings.empty or "quartier" not in scored_listings.columns:
        st.info("Aucune donnée exploitable pour le graphique par quartier.")
    else:
        avg_price = (
            scored_listings.groupby("quartier")["prix_m2"]
            .mean()
            .reset_index()
            .sort_values("prix_m2", ascending=True)
        )
        fig = px.bar(
            avg_price,
            x="prix_m2",
            y="quartier",
            orientation="h",
            color_discrete_sequence=["#0ea5e9"],
            labels={"prix_m2": "Prix/m²", "quartier": "Quartier"},
            template=get_plotly_template(),
        )
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis_title="",
            yaxis_title="",
            height=320,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with col_chart2:
    section_title("Tendance prix annonces")
    if not status["has_dates"] or trend_df.empty:
        st.info("Données insuffisantes pour afficher les tendances annuelles.")
    else:
        insight = compute_trend_insights(trend_df, "Prix m² médian")
        st.caption(
            f"Dernier niveau: {insight['latest']} €/m² | Variation annuelle: {insight['yoy_pct']}% "
            f"({insight['delta_abs']} €/m²)"
        )
        fig2 = px.line(
            trend_df,
            x="Date",
            y="Prix m² médian",
            color_discrete_sequence=["#10b981"],
            template=get_plotly_template(),
        )
        fig2.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis_title="",
            yaxis_title="",
            height=320,
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

col_bottom_1, col_bottom_2 = st.columns([1.1, 1.2])
with col_bottom_1:
    section_title("Top 5 biens sous-évalués")
    top_opps = scored_listings.sort_values("score_opportunite", ascending=False).head(5).copy()
    if top_opps.empty:
        st.info("Aucune annonce disponible.")
    else:
        display = top_opps[["quartier", "surface_m2", "pieces", "prix_eur", "prix_m2", "score_opportunite"]].copy()
        display = display.rename(
            columns={
                "quartier": "Quartier",
                "surface_m2": "Surface (m²)",
                "pieces": "Pièces",
                "prix_eur": "Prix (€)",
                "prix_m2": "Prix/m²",
                "score_opportunite": "Score Opportunité",
            }
        )
        st.dataframe(display, use_container_width=True, hide_index=True)

with col_bottom_2:
    section_title("Résumé marché par quartier")
    summary = build_listing_market_summary(scored_listings).head(8)
    if summary.empty:
        st.info("Aucune donnée quartier disponible.")
    else:
        st.dataframe(summary, use_container_width=True, hide_index=True)
