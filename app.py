import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Data Collection — Exam",
    page_icon="📊",
    layout="wide"
)

DB_PATH = "data_collection.db"
CSV_BOOKS_RAW = "books-toscrape-com-2026-08-06-3.csv"
CSV_GAARAAS_RAW = "gaaraas-com-2026-08-07.csv"

KOBO_URL   = "https://ee.kobotoolbox.org/x/Xir2zltq"
GFORMS_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdbbp5jmSU-WZ-WO4nfWmdZa6evxXOt3xNqP8kQBcB7HVdcLQ/viewform"

# ─────────────────────────────────────────────
# BASE DE DONNÉES
# ─────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS books (
        titre TEXT, prix REAL, disponibilite TEXT,
        nb_produits_page INTEGER, note INTEGER,
        nb_reviews INTEGER, description TEXT, categorie TEXT, tax REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS voitures (
        marque TEXT, modele TEXT, annee INTEGER,
        prix REAL, kilometrage INTEGER, boite_vitesses TEXT, region TEXT)''')
    conn.commit(); conn.close()

def get_db_count(table):
    try:
        conn = sqlite3.connect(DB_PATH)
        count = pd.read_sql_query(f"SELECT COUNT(*) as n FROM {table}", conn).iloc[0]['n']
        conn.close(); return count
    except: return 0

def load_table(table):
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        conn.close(); return df
    except: return pd.DataFrame()

def insert_books(rows):
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().executemany("INSERT INTO books VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit(); conn.close()

def insert_voitures(rows):
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().executemany("INSERT INTO voitures VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit(); conn.close()

# ─────────────────────────────────────────────
# SELENIUM
# ─────────────────────────────────────────────
def get_driver():
    options = Options()
    for arg in ["--headless","--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--window-size=1920,1080"]:
        options.add_argument(arg)
    return webdriver.Chrome(options=options)

# ─────────────────────────────────────────────
# NETTOYAGE
# ─────────────────────────────────────────────
note_map = {'One':1,'Two':2,'Three':3,'Four':4,'Five':5}

def nettoyer_prix(v):
    try: return float(re.sub(r'[^0-9.]','',v))
    except: return None

def nettoyer_tax(v):
    try: return float(re.sub(r'[^0-9.]','',v))
    except: return None

def nettoyer_note(v):
    for mot,n in note_map.items():
        if mot in v: return n
    return None

def nettoyer_dispo(v):
    if 'In stock' in v: return 'In stock'
    if 'Out of stock' in v: return 'Out of stock'
    return v.strip()

# ─────────────────────────────────────────────
# SCRAPING — BOOKS
# ─────────────────────────────────────────────
def scrape_books(nb_pages, progress_bar, status_text):
    driver = get_driver()
    book_urls, rows = [], []
    nb_erreurs = 0
    status_text.text("Collecte des URLs...")
    for page in range(1, nb_pages+1):
        driver.get(f"https://books.toscrape.com/catalogue/page-{page}.html")
        time.sleep(1)
        for l in driver.find_elements(By.CSS_SELECTOR,'article.product_pod h3 a'):
            book_urls.append(l.get_attribute('href'))
        progress_bar.progress(int(page/nb_pages*40))
    status_text.text(f"{len(book_urls)} livres trouvés. Scraping des détails...")
    total = len(book_urls)
    for idx, url in enumerate(book_urls):
        try:
            driver.get(url); time.sleep(0.5)
            titre = driver.find_element(By.CSS_SELECTOR,'div.product_main h1').text
            prix  = nettoyer_prix(driver.find_element(By.CSS_SELECTOR,'p.price_color').text)
            dispo = nettoyer_dispo(driver.find_element(By.CSS_SELECTOR,'p.availability').text)
            note  = nettoyer_note(driver.find_element(By.CSS_SELECTOR,'p.star-rating').get_attribute('class'))
            table_data = {}
            for ligne in driver.find_elements(By.CSS_SELECTOR,'table.table tr'):
                try:
                    k = ligne.find_element(By.TAG_NAME,'th').text.strip()
                    v = ligne.find_element(By.TAG_NAME,'td').text.strip()
                    table_data[k] = v
                except: pass
            nb_reviews = int(table_data.get('Number of reviews','0')) if table_data.get('Number of reviews','0').isdigit() else 0
            tax = nettoyer_tax(table_data.get('Tax','£0.00'))
            try: desc = driver.find_element(By.CSS_SELECTOR,'article.product_page > p').text
            except: desc = 'N/A'
            try:
                bc = driver.find_elements(By.CSS_SELECTOR,'ul.breadcrumb li')
                cat = bc[2].text.strip() if len(bc)>=3 else 'N/A'
            except: cat = 'N/A'
            rows.append((titre,prix,dispo,20,note,nb_reviews,desc,cat,tax))
        except: nb_erreurs += 1
        progress_bar.progress(40+int((idx+1)/total*55))
        if (idx+1)%20==0: status_text.text(f"{idx+1}/{total} livres traités...")
    driver.quit()
    insert_books(rows)
    progress_bar.progress(100)
    status_text.text(f"Terminé — {len(rows)} livres insérés ({nb_erreurs} erreurs)")
    return len(rows), nb_erreurs

# ─────────────────────────────────────────────
# SCRAPING — GAARAAS
# ─────────────────────────────────────────────
def scrape_gaaraas(nb_pages, progress_bar, status_text):
    driver = get_driver()
    rows = []; nb_erreurs = 0
    for page in range(1, nb_pages+1):
        try:
            driver.get(f"https://www.gaaraas.com/fr/users/dakar-auto?page={page}")
            time.sleep(2)
            annonces = driver.find_elements(By.CSS_SELECTOR,'div.ad-specification')
            if not annonces:
                status_text.text(f"Page {page} vide — arrêt."); break
            for annonce in annonces:
                try:
                    mots = annonce.find_element(By.CSS_SELECTOR,'h4').text.strip().split()
                    annee  = int(mots[0]) if mots and mots[0].isdigit() and len(mots[0])==4 else None
                    marque = mots[1] if len(mots)>1 else 'N/A'
                    modele = ' '.join(mots[2:]) if len(mots)>2 else 'N/A'
                    try: region = re.sub(r'\s+',' ',annonce.find_element(By.CSS_SELECTOR,'div.location').text).strip()
                    except: region='N/A'
                    try: prix = int(re.sub(r'[^0-9]','',annonce.find_element(By.CSS_SELECTOR,'span.price').text))
                    except: prix=None
                    try: km = int(re.sub(r'[^0-9]','',annonce.find_element(By.CSS_SELECTOR,'div.ad-vehicle-mileage div.value').text))
                    except: km=None
                    try: boite = annonce.find_element(By.CSS_SELECTOR,'div.transmission span:last-child').text.strip()
                    except: boite='N/A'
                    rows.append((marque,modele,annee,prix,km,boite,region))
                except: nb_erreurs+=1
        except Exception as e: status_text.text(f"Erreur page {page} : {e}")
        progress_bar.progress(int(page/nb_pages*95))
        if page%10==0: status_text.text(f"Page {page}/{nb_pages} — {len(rows)} annonces")
    driver.quit()
    insert_voitures(rows)
    progress_bar.progress(100)
    status_text.text(f"Terminé — {len(rows)} annonces insérées ({nb_erreurs} erreurs)")
    return len(rows), nb_erreurs

# ─────────────────────────────────────────────
# INIT DB
# ─────────────────────────────────────────────
init_db()
n_books    = get_db_count('books')
n_voitures = get_db_count('voitures')

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }

/* Fond */
.stApp { background: #0a0c10; }

/* Masquer sidebar entièrement */
[data-testid="stSidebar"] { display: none; }

/* Top bar custom */
.topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 0 14px 0;
    border-bottom: 1px solid #1c2030;
    margin-bottom: 28px;
}
.topbar-left {
    display: flex;
    align-items: baseline;
    gap: 12px;
}
.topbar-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 15px;
    font-weight: 600;
    color: #e2e8f0;
    letter-spacing: 0.03em;
}
.topbar-badge {
    font-size: 11px;
    color: #475569;
    font-weight: 500;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.topbar-stats {
    display: flex;
    gap: 20px;
}
.topbar-stat {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #475569;
}
.topbar-stat span { color: #94a3b8; font-weight: 600; }

/* Onglets Streamlit natifs — override */
div[data-testid="stTabs"] > div:first-child {
    border-bottom: 1px solid #1c2030;
    gap: 0;
}
div[data-testid="stTabs"] button[role="tab"] {
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 13px;
    font-weight: 500;
    color: #475569 !important;
    padding: 10px 20px !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
}
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #f1f5f9 !important;
    border-bottom: 2px solid #3b82f6 !important;
}

/* En-tête de section */
.sec-header {
    margin-bottom: 24px;
}
.sec-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 20px;
    font-weight: 600;
    color: #f1f5f9;
    letter-spacing: -0.01em;
}
.sec-sub {
    font-size: 13px;
    color: #475569;
    margin-top: 3px;
}

/* Séparateur */
.sep { border: none; border-top: 1px solid #1c2030; margin: 20px 0; }

/* KPI strip */
.kpi-strip {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: #1c2030;
    border: 1px solid #1c2030;
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 28px;
}
.kpi-cell {
    background: #0f1320;
    padding: 18px 22px;
}
.kpi-cell-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #475569;
    margin-bottom: 8px;
}
.kpi-cell-val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 26px;
    font-weight: 600;
    color: #e2e8f0;
    line-height: 1;
}
.kpi-cell-val.ok { font-size: 13px; color: #22d3ee; margin-top: 4px; }
.kpi-cell-val.ko { font-size: 13px; color: #f87171; margin-top: 4px; }

/* Label de bloc */
.blk-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #334155;
    margin: 24px 0 10px 0;
    display: flex;
    align-items: center;
    gap: 10px;
}
.blk-label::before {
    content: '';
    width: 3px; height: 14px;
    background: #3b82f6;
    border-radius: 2px;
    display: inline-block;
}

/* Info rows */
.irow {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid #1c2030;
    font-size: 13px;
}
.irow:last-child { border-bottom: none; }
.irow-k { color: #64748b; }
.irow-v {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #94a3b8;
    background: #131822;
    padding: 3px 10px;
    border-radius: 4px;
    border: 1px solid #1c2030;
}

/* Scraping card */
.scrape-card {
    background: #0f1320;
    border: 1px solid #1c2030;
    border-radius: 8px;
    padding: 24px;
}

/* Formulaires */
.form-panel {
    background: #0f1320;
    border: 1px solid #1c2030;
    border-radius: 8px;
    padding: 28px 26px 24px;
}
.form-panel-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 15px;
    font-weight: 600;
    color: #e2e8f0;
    margin-bottom: 8px;
}
.form-panel-desc { font-size: 13px; color: #475569; line-height: 1.6; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# TOP BAR (toujours visible)
# ─────────────────────────────────────────────
st.markdown(f"""
<div class="topbar">
    <div class="topbar-left">
        <span class="topbar-title">Data Collection</span>
        <span class="topbar-badge">Master IA · DIT Dakar · Examen 2026</span>
    </div>
    <div class="topbar-stats">
        <span class="topbar-stat">Books &nbsp;<span>{n_books:,}</span></span>
        <span class="topbar-stat">Voitures &nbsp;<span>{n_voitures:,}</span></span>
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# NAVIGATION — ONGLETS HORIZONTAUX
# ─────────────────────────────────────────────
tab_accueil, tab_scraping, tab_csv, tab_dashboard, tab_forms = st.tabs([
    "Accueil",
    "Scraping Live",
    "Données brutes",
    "Dashboard",
    "Formulaires"
])

# ─────────────────────────────────────────────
# ONGLET 1 — ACCUEIL
# ─────────────────────────────────────────────
with tab_accueil:
    books_raw_ok   = os.path.exists(CSV_BOOKS_RAW)
    gaaraas_raw_ok = os.path.exists(CSV_GAARAAS_RAW)

    st.markdown(f"""
    <div class="kpi-strip">
        <div class="kpi-cell">
            <div class="kpi-cell-label">Books en base</div>
            <div class="kpi-cell-val">{n_books:,}</div>
        </div>
        <div class="kpi-cell">
            <div class="kpi-cell-label">Voitures en base</div>
            <div class="kpi-cell-val">{n_voitures:,}</div>
        </div>
        <div class="kpi-cell">
            <div class="kpi-cell-label">CSV Books brut</div>
            <div class="kpi-cell-val ok">{'Présent' if books_raw_ok else 'Absent'}</div>
        </div>
        <div class="kpi-cell">
            <div class="kpi-cell-label">CSV Gaaraas brut</div>
            <div class="kpi-cell-val {'ok' if gaaraas_raw_ok else 'ko'}">{'Présent' if gaaraas_raw_ok else 'Absent'}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="blk-label">Sources de données</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="irow"><span class="irow-k">Books to Scrape</span><span class="irow-v">50 pages · 9 variables · Selenium</span></div>
    <div class="irow"><span class="irow-k">Gaaraas Dakar Auto</span><span class="irow-v">100 pages · 7 variables · Selenium</span></div>
    <div class="irow"><span class="irow-k">Outil no-code</span><span class="irow-v">Web Scraper (extension Chrome)</span></div>
    <div class="irow"><span class="irow-k">Stockage</span><span class="irow-v">SQLite · 2 tables (books, voitures)</span></div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# ONGLET 2 — SCRAPING LIVE
# ─────────────────────────────────────────────
with tab_scraping:
    st.markdown('<div class="sec-sub" style="margin-bottom:20px">Collecte via Selenium — stockage automatique en SQLite</div>', unsafe_allow_html=True)

    st.markdown('<div class="scrape-card">', unsafe_allow_html=True)
    source = st.selectbox("Source", ["Books to Scrape", "Gaaraas"], label_visibility="collapsed")

    if source == "Books to Scrape":
        nb_pages = st.slider("Nombre de pages", 1, 50, 5)
        st.caption(f"{nb_pages} page(s) — ~{nb_pages*20} livres estimés")
        if st.button("Lancer le scraping", type="primary"):
            pb = st.progress(0); st_txt = st.empty()
            with st.spinner("Scraping en cours..."):
                n, err = scrape_books(nb_pages, pb, st_txt)
            st.success(f"{n} livres insérés ({err} erreurs).")
    else:
        nb_pages = st.slider("Nombre de pages", 1, 100, 5)
        st.caption(f"{nb_pages} page(s) — ~{nb_pages*15} annonces estimées")
        if st.button("Lancer le scraping", type="primary"):
            pb = st.progress(0); st_txt = st.empty()
            with st.spinner("Scraping en cours..."):
                n, err = scrape_gaaraas(nb_pages, pb, st_txt)
            st.success(f"{n} annonces insérées ({err} erreurs).")
    st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# ONGLET 3 — DONNÉES BRUTES
# ─────────────────────────────────────────────
with tab_csv:
    st.markdown('<div class="sec-sub" style="margin-bottom:20px">Fichiers collectés via Web Scraper (non nettoyés)</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown('<div class="blk-label">Books to Scrape</div>', unsafe_allow_html=True)
        if os.path.exists(CSV_BOOKS_RAW):
            with open(CSV_BOOKS_RAW,"rb") as f:
                st.download_button("Télécharger le CSV", f, CSV_BOOKS_RAW, "text/csv", use_container_width=True)
            st.dataframe(pd.read_csv(CSV_BOOKS_RAW, nrows=5), use_container_width=True)
        else:
            st.warning(f"Fichier introuvable : `{CSV_BOOKS_RAW}`")

    with col2:
        st.markdown('<div class="blk-label">Gaaraas</div>', unsafe_allow_html=True)
        if os.path.exists(CSV_GAARAAS_RAW):
            with open(CSV_GAARAAS_RAW,"rb") as f:
                st.download_button("Télécharger le CSV", f, CSV_GAARAAS_RAW, "text/csv", use_container_width=True)
            st.dataframe(pd.read_csv(CSV_GAARAAS_RAW, nrows=5), use_container_width=True)
        else:
            st.warning(f"Fichier introuvable : `{CSV_GAARAAS_RAW}`")

# ─────────────────────────────────────────────
# ONGLET 4 — DASHBOARD
# ─────────────────────────────────────────────
with tab_dashboard:
    import plotly.express as px

    BG   = '#0a0c10'
    CARD = '#0f1320'
    GRID = '#1c2030'
    FC   = '#64748b'

    def plot_layout(h=300):
        return dict(
            plot_bgcolor=CARD, paper_bgcolor=BG,
            font_color=FC, height=h,
            margin=dict(l=0,r=0,t=16,b=0),
        )

    st.markdown('<div class="sec-sub" style="margin-bottom:20px">Données nettoyées · SQLite</div>', unsafe_allow_html=True)

    sub1, sub2 = st.tabs(["📚 Books to Scrape", "🚗 Gaaraas"])

    with sub1:
        df_books = load_table('books')
        if df_books.empty:
            st.info("Aucune donnée. Lancez un scraping depuis l'onglet Scraping Live.")
        else:
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Livres", f"{len(df_books):,}")
            c2.metric("Prix moyen", f"£{df_books['prix'].mean():.2f}")
            c3.metric("Note moy.", f"{df_books['note'].mean():.1f}/5")
            c4.metric("Catégories", df_books['categorie'].nunique())

            st.markdown('<div class="blk-label">Top 10 catégories</div>', unsafe_allow_html=True)
            cc = df_books['categorie'].value_counts().head(10).reset_index()
            cc.columns=['Catégorie','Nombre']
            fig1 = px.bar(cc, x='Nombre', y='Catégorie', orientation='h',
                          color_discrete_sequence=['#3b82f6'], height=300)
            fig1.update_layout(**plot_layout(300),
                xaxis=dict(gridcolor=GRID),
                yaxis=dict(gridcolor='rgba(0,0,0,0)', categoryorder='total ascending'))
            st.plotly_chart(fig1, use_container_width=True)

            ca, cb = st.columns(2)
            with ca:
                st.markdown('<div class="blk-label">Distribution des notes</div>', unsafe_allow_html=True)
                nc = df_books['note'].value_counts().sort_index().reset_index()
                nc.columns=['Note','Nombre']; nc['Note']=nc['Note'].astype(str)
                fig2 = px.bar(nc, x='Note', y='Nombre', color_discrete_sequence=['#6366f1'])
                fig2.update_layout(**plot_layout(260),
                    xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                    yaxis=dict(gridcolor=GRID))
                st.plotly_chart(fig2, use_container_width=True)

            with cb:
                st.markdown('<div class="blk-label">Disponibilité</div>', unsafe_allow_html=True)
                dp = df_books['disponibilite'].value_counts().reset_index()
                dp.columns=['Statut','Nombre']
                fig3 = px.pie(dp, names='Statut', values='Nombre', hole=0.5,
                              color_discrete_sequence=['#22d3ee','#f87171'])
                fig3.update_layout(**plot_layout(260), legend=dict(bgcolor='rgba(0,0,0,0)'))
                st.plotly_chart(fig3, use_container_width=True)

            st.markdown('<div class="blk-label">Aperçu des données</div>', unsafe_allow_html=True)
            st.dataframe(df_books.head(50), use_container_width=True, hide_index=True)

    with sub2:
        df_v = load_table('voitures')
        if df_v.empty:
            st.info("Aucune donnée. Lancez un scraping depuis l'onglet Scraping Live.")
        else:
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Annonces", f"{len(df_v):,}")
            c2.metric("Prix moyen (FCFA)", f"{df_v['prix'].mean():,.0f}")
            c3.metric("Km moyen", f"{df_v['kilometrage'].mean():,.0f}")
            c4.metric("Marques", df_v['marque'].nunique())

            st.markdown('<div class="blk-label">Top 10 marques</div>', unsafe_allow_html=True)
            mc = df_v['marque'].value_counts().head(10).reset_index()
            mc.columns=['Marque','Nombre']
            fig4 = px.bar(mc, x='Nombre', y='Marque', orientation='h',
                          color_discrete_sequence=['#3b82f6'])
            fig4.update_layout(**plot_layout(300),
                xaxis=dict(gridcolor=GRID),
                yaxis=dict(gridcolor='rgba(0,0,0,0)', categoryorder='total ascending'))
            st.plotly_chart(fig4, use_container_width=True)

            cc2, cd2 = st.columns(2)
            with cc2:
                st.markdown('<div class="blk-label">Boîte de vitesses</div>', unsafe_allow_html=True)
                bv = df_v['boite_vitesses'].value_counts().reset_index()
                bv.columns=['Type','Nombre']
                fig5 = px.pie(bv, names='Type', values='Nombre', hole=0.5,
                              color_discrete_sequence=['#3b82f6','#6366f1','#22d3ee'])
                fig5.update_layout(**plot_layout(260), legend=dict(bgcolor='rgba(0,0,0,0)'))
                st.plotly_chart(fig5, use_container_width=True)

            with cd2:
                st.markdown('<div class="blk-label">Répartition par région</div>', unsafe_allow_html=True)
                rg = df_v['region'].value_counts().head(8).reset_index()
                rg.columns=['Région','Nombre']
                fig6 = px.bar(rg, x='Région', y='Nombre',
                              color_discrete_sequence=['#6366f1'])
                fig6.update_layout(**plot_layout(260),
                    xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                    yaxis=dict(gridcolor=GRID))
                st.plotly_chart(fig6, use_container_width=True)

            st.markdown('<div class="blk-label">Distribution par année</div>', unsafe_allow_html=True)
            an = df_v['annee'].dropna().astype(int)
            fig7 = px.histogram(an, nbins=20, color_discrete_sequence=['#3b82f6'])
            fig7.update_layout(**plot_layout(240),
                xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                yaxis=dict(gridcolor=GRID), showlegend=False)
            st.plotly_chart(fig7, use_container_width=True)

            st.markdown('<div class="blk-label">Aperçu des données</div>', unsafe_allow_html=True)
            st.dataframe(df_v.head(50), use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────
# ONGLET 5 — FORMULAIRES
# ─────────────────────────────────────────────
with tab_forms:
    st.markdown('<div class="sec-sub" style="margin-bottom:24px">Deux versions du formulaire de collecte primaire</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("""
        <div class="form-panel">
            <div class="form-panel-title">KoboToolbox</div>
            <div class="form-panel-desc">
                Formulaire d'évaluation hébergé sur KoboToolbox.<br>
                Fonctionne hors ligne, idéal pour la collecte terrain.
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.link_button("Ouvrir le formulaire KoboToolbox →", KOBO_URL, use_container_width=True)

    with col2:
        st.markdown("""
        <div class="form-panel">
            <div class="form-panel-title">Google Forms</div>
            <div class="form-panel-desc">
                Formulaire d'évaluation hébergé sur Google Forms.<br>
                Réponses centralisées automatiquement dans Google Sheets.
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.link_button("Ouvrir le formulaire Google Forms →", GFORMS_URL, use_container_width=True)
