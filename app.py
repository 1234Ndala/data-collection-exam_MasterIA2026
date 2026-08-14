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

DB_PATH         = "data_collection.db"
CSV_BOOKS_RAW   = "books-toscrape-com-2026-08-06-3.csv"
CSV_GAARAAS_RAW = "gaaraas-com-2026-08-07.csv"
KOBO_URL        = "https://ee.kobotoolbox.org/x/Xir2zltq"
GFORMS_URL      = "https://docs.google.com/forms/d/e/1FAIpQLSdbbp5jmSU-WZ-WO4nfWmdZa6evxXOt3xNqP8kQBcB7HVdcLQ/viewform"

# ─────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS books (
        titre TEXT, prix REAL, disponibilite TEXT, nb_produits_page INTEGER,
        note INTEGER, nb_reviews INTEGER, description TEXT, categorie TEXT, tax REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS voitures (
        marque TEXT, modele TEXT, annee INTEGER, prix REAL,
        kilometrage INTEGER, boite_vitesses TEXT, region TEXT)''')
    conn.commit(); conn.close()

def get_db_count(table):
    try:
        conn = sqlite3.connect(DB_PATH)
        n = pd.read_sql_query(f"SELECT COUNT(*) as n FROM {table}", conn).iloc[0]['n']
        conn.close(); return n
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
    for a in ["--headless","--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--window-size=1920,1080"]:
        options.add_argument(a)
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
    driver.quit(); insert_books(rows)
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
            if not annonces: status_text.text(f"Page {page} vide — arrêt."); break
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
    driver.quit(); insert_voitures(rows)
    progress_bar.progress(100)
    status_text.text(f"Terminé — {len(rows)} annonces insérées ({nb_erreurs} erreurs)")
    return len(rows), nb_erreurs

# ─────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────
init_db()
n_books    = get_db_count('books')
n_voitures = get_db_count('voitures')

# ─────────────────────────────────────────────
# CSS — STYLE BI TOPBAR, SIDEBAR CACHÉE, ONGLETS LARGES
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@500;700;800&family=Manrope:wght@400;500;600&display=swap');

*, html, body, [class*="css"] {
    font-family: 'Manrope', sans-serif;
}

/* Cache sidebar entièrement */
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }

/* Fond général anthracite chaud */
.stApp { background: #18181b; }

/* Topbar */
.topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #09090b;
    border-bottom: 1px solid #27272a;
    padding: 0 40px;
    height: 56px;
    position: sticky;
    top: 0;
    z-index: 999;
    margin: -1rem -1rem 0 -1rem;
}
.topbar-logo {
    font-family: 'Syne', sans-serif;
    font-size: 14px;
    font-weight: 800;
    color: #fafafa;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.topbar-center {
    display: flex;
    gap: 2px;
}
.topbar-pill {
    font-size: 12px;
    font-weight: 600;
    color: #71717a;
    padding: 6px 16px;
    border-radius: 6px;
    cursor: pointer;
    letter-spacing: 0.01em;
    transition: all 0.15s;
}
.topbar-pill.active {
    background: #27272a;
    color: #fafafa;
}
.topbar-right {
    display: flex;
    gap: 16px;
    align-items: center;
}
.topbar-chip {
    font-size: 11px;
    font-weight: 600;
    color: #52525b;
    letter-spacing: 0.06em;
}
.topbar-chip b { color: #a1a1aa; font-weight: 700; }

/* Zone contenu */
.content { padding: 36px 40px 0 40px; margin: 0 -1rem; }

/* Hero accueil */
.hero {
    padding: 48px 0 40px 0;
    border-bottom: 1px solid #27272a;
    margin-bottom: 40px;
}
.hero-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: #a78bfa;
    margin-bottom: 14px;
}
.hero-title {
    font-family: 'Syne', sans-serif;
    font-size: 48px;
    font-weight: 800;
    color: #fafafa;
    line-height: 1.05;
    letter-spacing: -0.02em;
    margin-bottom: 12px;
}
.hero-sub {
    font-size: 15px;
    color: #52525b;
    font-weight: 500;
}

/* Stats row accueil */
.stats-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: #27272a;
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 48px;
}
.stat-cell {
    background: #09090b;
    padding: 24px 28px;
}
.stat-cell-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #52525b;
    margin-bottom: 12px;
}
.stat-cell-num {
    font-family: 'Syne', sans-serif;
    font-size: 40px;
    font-weight: 700;
    color: #fafafa;
    line-height: 1;
}
.stat-cell-sub {
    font-size: 12px;
    color: #52525b;
    margin-top: 6px;
}
.stat-cell-num.present { font-size: 16px; color: #4ade80; margin-top: 4px; }
.stat-cell-num.absent  { font-size: 16px; color: #f87171; margin-top: 4px; }

/* Tableau sources */
.src-title {
    font-family: 'Syne', sans-serif;
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #52525b;
    margin-bottom: 16px;
}
.src-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 0;
    border-bottom: 1px solid #27272a;
    font-size: 14px;
}
.src-row:last-child { border-bottom: none; }
.src-k { color: #a1a1aa; font-weight: 500; }
.src-v {
    font-size: 12px;
    font-weight: 600;
    color: #a78bfa;
    letter-spacing: 0.02em;
}

/* Page titre générique */
.page-hero {
    padding: 36px 0 32px 0;
    border-bottom: 1px solid #27272a;
    margin-bottom: 32px;
}
.page-hero-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #a78bfa;
    margin-bottom: 8px;
}
.page-hero-title {
    font-family: 'Syne', sans-serif;
    font-size: 32px;
    font-weight: 800;
    color: #fafafa;
    letter-spacing: -0.02em;
}
.page-hero-desc {
    font-size: 13px;
    color: #52525b;
    margin-top: 4px;
}

/* Scraping */
.scrape-panel {
    background: #09090b;
    border: 1px solid #27272a;
    border-radius: 12px;
    padding: 32px;
    max-width: 500px;
}

/* Section label dashboard */
.dash-label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #52525b;
    margin: 32px 0 14px 0;
}

/* Formulaires */
.form-block {
    background: #09090b;
    border: 1px solid #27272a;
    border-radius: 12px;
    padding: 32px;
}
.form-block-num {
    font-family: 'Syne', sans-serif;
    font-size: 48px;
    font-weight: 800;
    color: #27272a;
    line-height: 1;
    margin-bottom: 16px;
}
.form-block-title {
    font-family: 'Syne', sans-serif;
    font-size: 20px;
    font-weight: 700;
    color: #fafafa;
    margin-bottom: 8px;
}
.form-block-desc {
    font-size: 13px;
    color: #52525b;
    line-height: 1.7;
    margin-bottom: 24px;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# NAVIGATION — query param
# ─────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "Accueil"

PAGES = ["Accueil", "Scraping Live", "Données brutes", "Dashboard", "Formulaires"]

# Topbar
pills_html = ""
for p in PAGES:
    cls = "topbar-pill active" if st.session_state.page == p else "topbar-pill"
    pills_html += f'<span class="{cls}">{p}</span>'

st.markdown(f"""
<div class="topbar">
    <div class="topbar-logo">Data Collection</div>
    <div class="topbar-center">{pills_html}</div>
    <div class="topbar-right">
        <span class="topbar-chip">Books &nbsp;<b>{n_books:,}</b></span>
        <span class="topbar-chip">Voitures &nbsp;<b>{n_voitures:,}</b></span>
    </div>
</div>
""", unsafe_allow_html=True)

# Boutons de nav invisibles sous la topbar
nav_cols = st.columns(len(PAGES))
for i, p in enumerate(PAGES):
    with nav_cols[i]:
        if st.button(p, key=f"nav_{p}", use_container_width=True):
            st.session_state.page = p
            st.rerun()

page = st.session_state.page

st.markdown('<div class="content">', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# ACCUEIL
# ─────────────────────────────────────────────
if page == "Accueil":
    books_ok   = os.path.exists(CSV_BOOKS_RAW)
    gaaraas_ok = os.path.exists(CSV_GAARAAS_RAW)

    st.markdown("""
    <div class="hero">
        <div class="hero-label">Master IA · DIT Dakar · Examen 2026</div>
        <div class="hero-title">Projet<br>Data Collection</div>
        <div class="hero-sub">Web scraping · Nettoyage · Visualisation · Formulaires</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="stats-row">
        <div class="stat-cell">
            <div class="stat-cell-label">Books en base</div>
            <div class="stat-cell-num">{n_books:,}</div>
            <div class="stat-cell-sub">books.toscrape.com</div>
        </div>
        <div class="stat-cell">
            <div class="stat-cell-label">Voitures en base</div>
            <div class="stat-cell-num">{n_voitures:,}</div>
            <div class="stat-cell-sub">gaaraas.com</div>
        </div>
        <div class="stat-cell">
            <div class="stat-cell-label">CSV Books brut</div>
            <div class="stat-cell-num {'present' if books_ok else 'absent'}">{'✓ Présent' if books_ok else '✗ Absent'}</div>
        </div>
        <div class="stat-cell">
            <div class="stat-cell-label">CSV Gaaraas brut</div>
            <div class="stat-cell-num {'present' if gaaraas_ok else 'absent'}">{'✓ Présent' if gaaraas_ok else '✗ Absent'}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="src-title">Sources</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="src-row"><span class="src-k">Books to Scrape</span><span class="src-v">50 pages · 9 variables · Selenium</span></div>
    <div class="src-row"><span class="src-k">Gaaraas Dakar Auto</span><span class="src-v">100 pages · 7 variables · Selenium</span></div>
    <div class="src-row"><span class="src-k">Outil no-code</span><span class="src-v">Web Scraper (extension Chrome)</span></div>
    <div class="src-row"><span class="src-k">Stockage</span><span class="src-v">SQLite · 2 tables (books, voitures)</span></div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SCRAPING LIVE
# ─────────────────────────────────────────────
elif page == "Scraping Live":
    st.markdown("""
    <div class="page-hero">
        <div class="page-hero-label">Collecte</div>
        <div class="page-hero-title">Scraping Live</div>
        <div class="page-hero-desc">Selenium · stockage automatique en SQLite</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="scrape-panel">', unsafe_allow_html=True)
    source = st.selectbox("Source", ["Books to Scrape", "Gaaraas"])
    if source == "Books to Scrape":
        nb_pages = st.slider("Pages", 1, 50, 5)
        st.caption(f"~{nb_pages*20} livres estimés")
        if st.button("Lancer le scraping", type="primary"):
            pb = st.progress(0); txt = st.empty()
            with st.spinner("En cours..."):
                n, err = scrape_books(nb_pages, pb, txt)
            st.success(f"{n} livres insérés ({err} erreurs).")
    else:
        nb_pages = st.slider("Pages", 1, 100, 5)
        st.caption(f"~{nb_pages*15} annonces estimées")
        if st.button("Lancer le scraping", type="primary"):
            pb = st.progress(0); txt = st.empty()
            with st.spinner("En cours..."):
                n, err = scrape_gaaraas(nb_pages, pb, txt)
            st.success(f"{n} annonces insérées ({err} erreurs).")
    st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# DONNÉES BRUTES
# ─────────────────────────────────────────────
elif page == "Données brutes":
    st.markdown("""
    <div class="page-hero">
        <div class="page-hero-label">Export</div>
        <div class="page-hero-title">Données brutes</div>
        <div class="page-hero-desc">Fichiers collectés via Web Scraper — non nettoyés</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown('<div class="dash-label">Books to Scrape</div>', unsafe_allow_html=True)
        if os.path.exists(CSV_BOOKS_RAW):
            with open(CSV_BOOKS_RAW,"rb") as f:
                st.download_button("Télécharger le CSV", f, CSV_BOOKS_RAW, "text/csv", use_container_width=True)
            st.dataframe(pd.read_csv(CSV_BOOKS_RAW, nrows=5), use_container_width=True)
        else:
            st.warning(f"Fichier introuvable : `{CSV_BOOKS_RAW}`")
    with col2:
        st.markdown('<div class="dash-label">Gaaraas</div>', unsafe_allow_html=True)
        if os.path.exists(CSV_GAARAAS_RAW):
            with open(CSV_GAARAAS_RAW,"rb") as f:
                st.download_button("Télécharger le CSV", f, CSV_GAARAAS_RAW, "text/csv", use_container_width=True)
            st.dataframe(pd.read_csv(CSV_GAARAAS_RAW, nrows=5), use_container_width=True)
        else:
            st.warning(f"Fichier introuvable : `{CSV_GAARAAS_RAW}`")

# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
elif page == "Dashboard":
    import plotly.express as px

    BG   = '#18181b'
    CARD = '#09090b'
    GRID = '#27272a'
    FC   = '#71717a'

    def pl(h=300):
        return dict(plot_bgcolor=CARD, paper_bgcolor=BG,
                    font_color=FC, height=h,
                    margin=dict(l=0,r=0,t=20,b=0),
                    font=dict(family='Manrope'))

    st.markdown("""
    <div class="page-hero">
        <div class="page-hero-label">Analyse</div>
        <div class="page-hero-title">Dashboard</div>
        <div class="page-hero-desc">Données nettoyées · SQLite</div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📚  Books to Scrape", "🚗  Gaaraas"])

    with tab1:
        df_b = load_table('books')
        if df_b.empty:
            st.info("Aucune donnée. Lancez un scraping d'abord.")
        else:
            # KPIs en ligne pleine largeur
            k1,k2,k3,k4 = st.columns(4)
            k1.metric("Livres", f"{len(df_b):,}")
            k2.metric("Prix moyen", f"£{df_b['prix'].mean():.2f}")
            k3.metric("Note moyenne", f"{df_b['note'].mean():.1f}/5")
            k4.metric("Catégories", df_b['categorie'].nunique())

            # Chart pleine largeur
            st.markdown('<div class="dash-label">Répartition par catégorie — Top 10</div>', unsafe_allow_html=True)
            cc = df_b['categorie'].value_counts().head(10).reset_index()
            cc.columns=['Catégorie','Nombre']
            fig1 = px.bar(cc, x='Catégorie', y='Nombre', color_discrete_sequence=['#a78bfa'])
            fig1.update_layout(**pl(280),
                xaxis=dict(gridcolor='rgba(0,0,0,0)', categoryorder='total descending'),
                yaxis=dict(gridcolor=GRID))
            st.plotly_chart(fig1, use_container_width=True)

            # 3 colonnes asymétriques : grand | petit | petit
            ca, cb, cc2 = st.columns([2,1,1])
            with ca:
                st.markdown('<div class="dash-label">Prix — scatter note vs prix</div>', unsafe_allow_html=True)
                fig_s = px.scatter(df_b, x='note', y='prix', opacity=0.5,
                                   color_discrete_sequence=['#a78bfa'])
                fig_s.update_layout(**pl(280),
                    xaxis=dict(gridcolor=GRID, title='Note'),
                    yaxis=dict(gridcolor=GRID, title='Prix (£)'))
                st.plotly_chart(fig_s, use_container_width=True)
            with cb:
                st.markdown('<div class="dash-label">Notes</div>', unsafe_allow_html=True)
                nc = df_b['note'].value_counts().sort_index().reset_index()
                nc.columns=['Note','N']; nc['Note']=nc['Note'].astype(str)
                fig2 = px.bar(nc, x='Note', y='N', color_discrete_sequence=['#f472b6'])
                fig2.update_layout(**pl(280),
                    xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                    yaxis=dict(gridcolor=GRID))
                st.plotly_chart(fig2, use_container_width=True)
            with cc2:
                st.markdown('<div class="dash-label">Dispo</div>', unsafe_allow_html=True)
                dp = df_b['disponibilite'].value_counts().reset_index()
                dp.columns=['Statut','N']
                fig3 = px.pie(dp, names='Statut', values='N', hole=0.6,
                              color_discrete_sequence=['#a78bfa','#f472b6'])
                fig3.update_layout(**pl(280), legend=dict(bgcolor='rgba(0,0,0,0)',orientation='h',y=-0.1))
                st.plotly_chart(fig3, use_container_width=True)

            st.markdown('<div class="dash-label">Aperçu des données</div>', unsafe_allow_html=True)
            st.dataframe(df_b.head(50), use_container_width=True, hide_index=True)

    with tab2:
        df_v = load_table('voitures')
        if df_v.empty:
            st.info("Aucune donnée. Lancez un scraping d'abord.")
        else:
            k1,k2,k3,k4 = st.columns(4)
            k1.metric("Annonces", f"{len(df_v):,}")
            k2.metric("Prix moyen (FCFA)", f"{df_v['prix'].mean():,.0f}")
            k3.metric("Km moyen", f"{df_v['kilometrage'].mean():,.0f}")
            k4.metric("Marques", df_v['marque'].nunique())

            # Ligne : scatter prix vs km (large) + donut boite (étroit)
            left, right = st.columns([3,1])
            with left:
                st.markdown('<div class="dash-label">Prix vs Kilométrage</div>', unsafe_allow_html=True)
                fig_sv = px.scatter(df_v, x='kilometrage', y='prix', color='boite_vitesses',
                                    opacity=0.55, color_discrete_sequence=['#34d399','#a78bfa','#f472b6','#fb923c'])
                fig_sv.update_layout(**pl(300),
                    xaxis=dict(gridcolor=GRID, title='Km'),
                    yaxis=dict(gridcolor=GRID, title='Prix FCFA'))
                st.plotly_chart(fig_sv, use_container_width=True)
            with right:
                st.markdown('<div class="dash-label">Boîte</div>', unsafe_allow_html=True)
                bv = df_v['boite_vitesses'].value_counts().reset_index()
                bv.columns=['Type','N']
                fig5 = px.pie(bv, names='Type', values='N', hole=0.6,
                              color_discrete_sequence=['#34d399','#a78bfa','#f472b6'])
                fig5.update_layout(**pl(300), legend=dict(bgcolor='rgba(0,0,0,0)',orientation='h',y=-0.1))
                st.plotly_chart(fig5, use_container_width=True)

            # Top marques horizontal + histogram années
            st.markdown('<div class="dash-label">Top 10 marques</div>', unsafe_allow_html=True)
            mc = df_v['marque'].value_counts().head(10).reset_index()
            mc.columns=['Marque','Nombre']
            fig4 = px.bar(mc, x='Nombre', y='Marque', orientation='h',
                          color_discrete_sequence=['#34d399'])
            fig4.update_layout(**pl(280),
                xaxis=dict(gridcolor=GRID),
                yaxis=dict(gridcolor='rgba(0,0,0,0)', categoryorder='total ascending'))
            st.plotly_chart(fig4, use_container_width=True)

            ca2, cb2 = st.columns(2)
            with ca2:
                st.markdown('<div class="dash-label">Distribution par année</div>', unsafe_allow_html=True)
                an = df_v['annee'].dropna().astype(int)
                fig7 = px.histogram(an, nbins=20, color_discrete_sequence=['#a78bfa'])
                fig7.update_layout(**pl(240),
                    xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                    yaxis=dict(gridcolor=GRID), showlegend=False)
                st.plotly_chart(fig7, use_container_width=True)
            with cb2:
                st.markdown('<div class="dash-label">Top 8 régions</div>', unsafe_allow_html=True)
                rg = df_v['region'].value_counts().head(8).reset_index()
                rg.columns=['Région','Nombre']
                fig6 = px.bar(rg, x='Région', y='Nombre',
                              color_discrete_sequence=['#fb923c'])
                fig6.update_layout(**pl(240),
                    xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                    yaxis=dict(gridcolor=GRID))
                st.plotly_chart(fig6, use_container_width=True)

            st.markdown('<div class="dash-label">Aperçu des données</div>', unsafe_allow_html=True)
            st.dataframe(df_v.head(50), use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────
# FORMULAIRES
# ─────────────────────────────────────────────
elif page == "Formulaires":
    st.markdown("""
    <div class="page-hero">
        <div class="page-hero-label">Collecte primaire</div>
        <div class="page-hero-title">Formulaires</div>
        <div class="page-hero-desc">KoboToolbox · Google Forms</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("""
        <div class="form-block">
            <div class="form-block-num">01</div>
            <div class="form-block-title">KoboToolbox</div>
            <div class="form-block-desc">Formulaire d'évaluation hébergé sur KoboToolbox. Fonctionne hors ligne, idéal pour la collecte terrain. Les réponses sont centralisées en temps réel.</div>
        </div>
        """, unsafe_allow_html=True)
        st.link_button("Ouvrir KoboToolbox →", KOBO_URL, use_container_width=True)

    with col2:
        st.markdown("""
        <div class="form-block">
            <div class="form-block-num">02</div>
            <div class="form-block-title">Google Forms</div>
            <div class="form-block-desc">Formulaire d'évaluation hébergé sur Google Forms. Accessible depuis n'importe quel appareil, les réponses sont automatiquement collectées dans Google Sheets.</div>
        </div>
        """, unsafe_allow_html=True)
        st.link_button("Ouvrir Google Forms →", GFORMS_URL, use_container_width=True)

st.markdown('</div>', unsafe_allow_html=True)
