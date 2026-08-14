import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

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

def get_driver():
    options = Options()
    for a in ["--headless","--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--window-size=1920,1080"]:
        options.add_argument(a)
    return webdriver.Chrome(options=options)

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
    status_text.text(f"{len(book_urls)} livres trouvés.")
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
    status_text.text(f"Terminé — {len(rows)} insérés ({nb_erreurs} erreurs)")
    return len(rows), nb_erreurs

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
    status_text.text(f"Terminé — {len(rows)} insérés ({nb_erreurs} erreurs)")
    return len(rows), nb_erreurs

init_db()
n_books    = get_db_count('books')
n_voitures = get_db_count('voitures')

# ══════════════════════════════════════════════
# CSS — STYLE CITIZENS' HOUR
# ══════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Open Sans', sans-serif !important;
}

/* Fond gris clair général */
.stApp { background: #eef2f7 !important; }
.main { background: #eef2f7 !important; }
section[data-testid="stAppViewContainer"] { background: #eef2f7 !important; }
section[data-testid="stMain"] { background: #eef2f7 !important; }

/* ── Sidebar navy ── */
[data-testid="stSidebar"] {
    background: #1a2a4a !important;
    border-right: none !important;
}
[data-testid="stSidebar"] * { color: #c8d6e8 !important; }
[data-testid="stSidebar"] .stRadio label {
    font-size: 13px !important;
    font-weight: 600 !important;
    color: #c8d6e8 !important;
    padding: 10px 14px !important;
    border-radius: 6px !important;
    margin-bottom: 2px !important;
    display: flex !important;
    align-items: center !important;
    gap: 8px;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(255,255,255,0.08) !important;
    color: #ffffff !important;
}

.sb-header {
    background: #0f1f3d;
    margin: -1rem -1rem 0 -1rem;
    padding: 16px 20px 14px;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    margin-bottom: 20px;
}
.sb-title {
    font-size: 15px;
    font-weight: 800;
    color: #ffffff !important;
    letter-spacing: 0.01em;
}
.sb-sub {
    font-size: 10px;
    color: #5a7aaa !important;
    margin-top: 2px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.sb-divider { border:none; border-top:1px solid rgba(255,255,255,0.08); margin:16px 0; }
.sb-stat-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #5a7aaa !important;
    margin-bottom: 2px;
}
.sb-stat-val {
    font-size: 22px;
    font-weight: 800;
    color: #ffffff !important;
    margin-bottom: 10px;
}

/* ── Topbar bleu foncé ── */
.topbar {
    background: #1a2a4a;
    margin: -1rem -1rem 0 -1rem;
    padding: 14px 28px;
    display: flex;
    align-items: center;
    gap: 12px;
    border-bottom: 3px solid #2e7bc4;
}
.topbar-icon { font-size: 20px; }
.topbar-title {
    font-size: 17px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.01em;
}

/* ── Fond page ── */
.page-body {
    padding: 24px 8px 0 8px;
}

/* ── KPI cards bleues (style Citizens' Hour) ── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4,1fr);
    gap: 14px;
    margin-bottom: 20px;
}
.kpi-card {
    background: linear-gradient(135deg, #2e7bc4 0%, #1a5fa0 100%);
    border-radius: 8px;
    padding: 20px 20px 16px;
    position: relative;
    overflow: hidden;
    min-height: 100px;
}
.kpi-card.light {
    background: linear-gradient(135deg, #3a9bd5 0%, #2278b5 100%);
}
.kpi-card-icon {
    position: absolute;
    right: 14px;
    bottom: 10px;
    font-size: 42px;
    opacity: 0.18;
    line-height: 1;
}
.kpi-card-val {
    font-size: 32px;
    font-weight: 800;
    color: #ffffff;
    line-height: 1.1;
    margin-bottom: 6px;
}
.kpi-card-label {
    font-size: 12px;
    font-weight: 600;
    color: rgba(255,255,255,0.85);
}
.kpi-card.ok  { background: linear-gradient(135deg, #27ae60 0%, #1e8449 100%); }
.kpi-card.ko  { background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); }

/* ── Chart panels ── */
.chart-panel {
    background: #ffffff;
    border-radius: 8px;
    padding: 18px 20px 12px;
    border: 1px solid #dde4ee;
    margin-bottom: 16px;
}
.chart-panel-title {
    font-size: 14px;
    font-weight: 700;
    color: #1a2a4a;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 2px solid #2e7bc4;
    display: inline-block;
}

/* ── Filtres ── */
.filter-label {
    font-size: 12px;
    font-weight: 700;
    color: #1a2a4a;
    margin-bottom: 6px;
}

/* ── Scraping ── */
.scrape-panel {
    background: #ffffff;
    border-radius: 8px;
    padding: 28px;
    border: 1px solid #dde4ee;
    max-width: 520px;
}
.scrape-panel-title {
    font-size: 14px;
    font-weight: 700;
    color: #1a2a4a;
    margin-bottom: 16px;
    padding-bottom: 10px;
    border-bottom: 2px solid #2e7bc4;
    display: inline-block;
}

/* ── Section titre ── */
.section-head {
    font-size: 13px;
    font-weight: 700;
    color: #1a2a4a;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 20px 0 12px 0;
    display: flex;
    align-items: center;
    gap: 8px;
}
.section-head::after {
    content: '';
    flex: 1;
    height: 2px;
    background: #dde4ee;
}

/* ── Tableau info ── */
.info-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 11px 0;
    border-bottom: 1px solid #eef2f7;
    font-size: 13px;
}
.info-row:last-child { border-bottom: none; }
.info-k { color: #2c3e50; font-weight: 600; }
.info-v {
    background: #2e7bc4;
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 20px;
}

/* ── Formulaires ── */
.form-card {
    background: #ffffff;
    border-radius: 8px;
    border: 1px solid #dde4ee;
    border-top: 4px solid #2e7bc4;
    padding: 24px;
}
.form-card-title {
    font-size: 16px;
    font-weight: 800;
    color: #1a2a4a;
    margin-bottom: 10px;
}
.form-card-desc {
    font-size: 13px;
    color: #7f8c8d;
    line-height: 1.65;
    margin-bottom: 20px;
}
</style>
""", unsafe_allow_html=True)

# ── CACHE SIDEBAR + NAVBAR ───────────────────
st.markdown("""
<style>
[data-testid="stSidebar"]      { display: none !important; }
[data-testid="collapsedControl"]{ display: none !important; }

.navbar {
    background: #1a2a4a;
    margin: -1rem -1rem 0 -1rem;
    padding: 14px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 3px solid #2e7bc4;
}
.navbar-left  { display: flex; align-items: center; gap: 16px; }
.navbar-logo  { font-size: 17px; font-weight: 800; color: #fff; }
.navbar-meta  { font-size: 11px; color: #5a7aaa; text-transform: uppercase; letter-spacing: 0.08em; }
.navbar-right { display: flex; gap: 16px; }
.navbar-chip  { font-size: 12px; color: #a8c8e8; }
.navbar-chip b { color: #fff; }

/* Style des onglets natifs Streamlit */
div[data-testid="stTabs"] > div:first-child {
    background: #1a2a4a;
    margin: 0 -1rem;
    padding: 0 20px;
    border-bottom: none !important;
    gap: 0 !important;
}
div[data-testid="stTabs"] button[role="tab"] {
    font-family: 'Open Sans', sans-serif !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    color: #7a9cc4 !important;
    padding: 14px 20px !important;
    border-radius: 0 !important;
    border-bottom: 3px solid transparent !important;
    background: transparent !important;
}
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #ffffff !important;
    border-bottom: 3px solid #ffffff !important;
    background: rgba(255,255,255,0.06) !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="navbar">
    <div class="navbar-left">
        <span class="navbar-logo">📊 Data Collection</span>
        <span class="navbar-meta">Master IA · DIT Dakar · 2026</span>
    </div>
    <div class="navbar-right">
        <span class="navbar-chip">📚 <b>{n_books:,}</b> books</span>
        <span class="navbar-chip">🚗 <b>{n_voitures:,}</b> voitures</span>
    </div>
</div>
""", unsafe_allow_html=True)

tab_accueil, tab_scraping, tab_csv, tab_dashboard, tab_forms = st.tabs([
    "🏠  Accueil",
    "⚡  Scraping Live",
    "📥  Téléchargement CSV",
    "📊  Dashboard",
    "📋  Formulaires"
])

# ── PLOTLY helper ─────────────────────────────
def pl(h=300):
    return dict(
        plot_bgcolor='#ffffff', paper_bgcolor='#ffffff',
        font_color='#7f8c8d', height=h,
        margin=dict(l=0,r=0,t=8,b=0),
        font=dict(family='Open Sans'),
    )

BLEU  = '#2e7bc4'
BLEU2 = '#1a5fa0'
VERT  = '#27ae60'
ROUGE = '#e74c3c'
GRIS  = '#dde4ee'

# ════════════════════════════════════════════
# ACCUEIL
# ════════════════════════════════════════════
with tab_accueil:
    books_ok   = os.path.exists(CSV_BOOKS_RAW)
    gaaraas_ok = os.path.exists(CSV_GAARAAS_RAW)

    st.markdown('<div class="page-body">', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-card-val">{n_books:,}</div>
            <div class="kpi-card-label">Books en base</div>
            <div class="kpi-card-icon">📚</div>
        </div>
        <div class="kpi-card light">
            <div class="kpi-card-val">{n_voitures:,}</div>
            <div class="kpi-card-label">Voitures en base</div>
            <div class="kpi-card-icon">🚗</div>
        </div>
        <div class="kpi-card {'ok' if books_ok else 'ko'}">
            <div class="kpi-card-val">{'Présent' if books_ok else 'Absent'}</div>
            <div class="kpi-card-label">CSV Books brut</div>
            <div class="kpi-card-icon">{'✓' if books_ok else '✗'}</div>
        </div>
        <div class="kpi-card {'ok' if gaaraas_ok else 'ko'}">
            <div class="kpi-card-val">{'Présent' if gaaraas_ok else 'Absent'}</div>
            <div class="kpi-card-label">CSV Gaaraas brut</div>
            <div class="kpi-card-icon">{'✓' if gaaraas_ok else '✗'}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-head">Sources de données</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="chart-panel">
        <div class="info-row"><span class="info-k">Books to Scrape</span><span class="info-v">50 pages · 9 variables · Selenium</span></div>
        <div class="info-row"><span class="info-k">Gaaraas Dakar Auto</span><span class="info-v">100 pages · 7 variables · Selenium</span></div>
        <div class="info-row"><span class="info-k">Outil no-code</span><span class="info-v">Web Scraper Chrome</span></div>
        <div class="info-row"><span class="info-k">Stockage</span><span class="info-v">SQLite · 2 tables</span></div>
    </div>
    </div>
    """, unsafe_allow_html=True)

# ════════════════════════════════════════════
# SCRAPING LIVE
# ════════════════════════════════════════════
with tab_scraping:
    st.markdown('<div class="page-body">', unsafe_allow_html=True)
    st.markdown('<div class="section-head">Scraping Live</div>', unsafe_allow_html=True)
    st.markdown('<div class="scrape-panel"><div class="scrape-panel-title">Lancer une collecte</div>', unsafe_allow_html=True)

    source = st.selectbox("Source", ["Books to Scrape", "Gaaraas"])
    if source == "Books to Scrape":
        nb_pages = st.slider("Nombre de pages", 1, 50, 5)
        st.caption(f"~{nb_pages*20} livres estimés")
        if st.button("▶ Lancer le scraping", type="primary"):
            pb = st.progress(0); txt = st.empty()
            with st.spinner("Scraping en cours..."):
                n, err = scrape_books(nb_pages, pb, txt)
            st.success(f"{n} livres insérés ({err} erreurs).")
    else:
        nb_pages = st.slider("Nombre de pages", 1, 100, 5)
        st.caption(f"~{nb_pages*15} annonces estimées")
        if st.button("▶ Lancer le scraping", type="primary"):
            pb = st.progress(0); txt = st.empty()
            with st.spinner("Scraping en cours..."):
                n, err = scrape_gaaraas(nb_pages, pb, txt)
            st.success(f"{n} annonces insérées ({err} erreurs).")

    st.markdown('</div></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════
# TÉLÉCHARGEMENT CSV
# ════════════════════════════════════════════
with tab_csv:
    st.markdown('<div class="page-body">', unsafe_allow_html=True)
    st.markdown('<div class="section-head">Données brutes — Web Scraper Chrome</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown('<div class="chart-panel"><div class="chart-panel-title">Books to Scrape</div>', unsafe_allow_html=True)
        if os.path.exists(CSV_BOOKS_RAW):
            with open(CSV_BOOKS_RAW,"rb") as f:
                st.download_button("⬇ Télécharger le CSV", f, CSV_BOOKS_RAW, "text/csv", use_container_width=True)
            st.dataframe(pd.read_csv(CSV_BOOKS_RAW, nrows=5), use_container_width=True)
        else:
            st.warning(f"Fichier introuvable : `{CSV_BOOKS_RAW}`")
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="chart-panel"><div class="chart-panel-title">Gaaraas Dakar Auto</div>', unsafe_allow_html=True)
        if os.path.exists(CSV_GAARAAS_RAW):
            with open(CSV_GAARAAS_RAW,"rb") as f:
                st.download_button("⬇ Télécharger le CSV", f, CSV_GAARAAS_RAW, "text/csv", use_container_width=True)
            st.dataframe(pd.read_csv(CSV_GAARAAS_RAW, nrows=5), use_container_width=True)
        else:
            st.warning(f"Fichier introuvable : `{CSV_GAARAAS_RAW}`")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════
with tab_dashboard:
    import plotly.express as px

    st.markdown('<div class="page-body">', unsafe_allow_html=True)
    st.markdown('<div class="section-head">Dashboard — Données nettoyées · SQLite</div>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📚  Books to Scrape", "🚗  Gaaraas"])

    with tab1:
        df_b = load_table('books')
        if df_b.empty:
            st.info("Aucune donnée en base. Lancez un scraping d'abord.")
        else:
            # KPI cards
            st.markdown(f"""
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-card-val">{len(df_b):,}</div>
                    <div class="kpi-card-label">Livres</div>
                    <div class="kpi-card-icon">📚</div>
                </div>
                <div class="kpi-card light">
                    <div class="kpi-card-val">£{df_b['prix'].mean():.2f}</div>
                    <div class="kpi-card-label">Prix moyen</div>
                    <div class="kpi-card-icon">💷</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-card-val">{df_b['note'].mean():.1f}/5</div>
                    <div class="kpi-card-label">Note moyenne</div>
                    <div class="kpi-card-icon">⭐</div>
                </div>
                <div class="kpi-card light">
                    <div class="kpi-card-val">{df_b['categorie'].nunique()}</div>
                    <div class="kpi-card-label">Catégories</div>
                    <div class="kpi-card-icon">🏷️</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Filtres
            st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
            st.markdown('<div class="filter-label">Filtrer les données</div>', unsafe_allow_html=True)
            f1, f2, f3 = st.columns(3)
            with f1:
                cats = ["Toutes"] + sorted(df_b['categorie'].dropna().unique().tolist())
                cat_sel = st.selectbox("Catégorie", cats)
            with f2:
                notes = ["Toutes"] + [str(n) for n in sorted(df_b['note'].dropna().unique().astype(int).tolist())]
                note_sel = st.selectbox("Note", notes)
            with f3:
                dispo_opts = ["Toutes"] + df_b['disponibilite'].dropna().unique().tolist()
                dispo_sel = st.selectbox("Disponibilité", dispo_opts)
            st.markdown('</div>', unsafe_allow_html=True)

            df_f = df_b.copy()
            if cat_sel   != "Toutes": df_f = df_f[df_f['categorie']     == cat_sel]
            if note_sel  != "Toutes": df_f = df_f[df_f['note']          == int(note_sel)]
            if dispo_sel != "Toutes": df_f = df_f[df_f['disponibilite'] == dispo_sel]

            if df_f.empty:
                st.warning("Aucun résultat pour ces filtres.")
            else:
                # Charts côte à côte
                c_left, c_right = st.columns([3, 2])
                with c_left:
                    st.markdown('<div class="chart-panel"><div class="chart-panel-title">Répartition par catégorie</div>', unsafe_allow_html=True)
                    cc = df_f['categorie'].value_counts().head(10).reset_index()
                    cc.columns=['Catégorie','Nombre']
                    fig1 = px.bar(cc, x='Nombre', y='Catégorie', orientation='h',
                                  color_discrete_sequence=[BLEU])
                    fig1.update_layout(**pl(300),
                        xaxis=dict(gridcolor='#f0f4f8', showgrid=True),
                        yaxis=dict(gridcolor='rgba(0,0,0,0)', categoryorder='total ascending'))
                    st.plotly_chart(fig1, use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)

                with c_right:
                    st.markdown('<div class="chart-panel"><div class="chart-panel-title">Disponibilité</div>', unsafe_allow_html=True)
                    dp = df_f['disponibilite'].value_counts().reset_index()
                    dp.columns=['Statut','Nombre']
                    fig3 = px.pie(dp, names='Statut', values='Nombre', hole=0.5,
                                  color_discrete_sequence=[BLEU, '#a8c8e8'])
                    fig3.update_layout(**pl(300), legend=dict(bgcolor='rgba(0,0,0,0)', orientation='h', y=-0.1))
                    st.plotly_chart(fig3, use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('<div class="chart-panel"><div class="chart-panel-title">Distribution des notes</div>', unsafe_allow_html=True)
                nc = df_f['note'].value_counts().sort_index().reset_index()
                nc.columns=['Note','Nombre']; nc['Note']=nc['Note'].astype(str)
                fig2 = px.bar(nc, x='Note', y='Nombre', color_discrete_sequence=[BLEU2])
                fig2.update_layout(**pl(220),
                    xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                    yaxis=dict(gridcolor='#f0f4f8'))
                st.plotly_chart(fig2, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('<div class="chart-panel"><div class="chart-panel-title">Aperçu des données</div>', unsafe_allow_html=True)
                st.dataframe(df_f.head(50), use_container_width=True, hide_index=True)
                st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        df_v = load_table('voitures')
        if df_v.empty:
            st.info("Aucune donnée en base. Lancez un scraping d'abord.")
        else:
            st.markdown(f"""
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-card-val">{len(df_v):,}</div>
                    <div class="kpi-card-label">Annonces</div>
                    <div class="kpi-card-icon">🚗</div>
                </div>
                <div class="kpi-card light">
                    <div class="kpi-card-val">{df_v['prix'].mean():,.0f}</div>
                    <div class="kpi-card-label">Prix moyen (FCFA)</div>
                    <div class="kpi-card-icon">💰</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-card-val">{df_v['kilometrage'].mean():,.0f}</div>
                    <div class="kpi-card-label">Km moyen</div>
                    <div class="kpi-card-icon">🛣️</div>
                </div>
                <div class="kpi-card light">
                    <div class="kpi-card-val">{df_v['marque'].nunique()}</div>
                    <div class="kpi-card-label">Marques</div>
                    <div class="kpi-card-icon">🏷️</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Filtres
            st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
            st.markdown('<div class="filter-label">Filtrer les données</div>', unsafe_allow_html=True)
            g1, g2, g3, g4 = st.columns(4)
            with g1:
                marques = ["Toutes"] + sorted(df_v['marque'].dropna().unique().tolist())
                marque_sel = st.selectbox("Marque", marques)
            with g2:
                regions = ["Toutes"] + sorted(df_v['region'].dropna().unique().tolist())
                region_sel = st.selectbox("Région", regions)
            with g3:
                boites = ["Toutes"] + sorted(df_v['boite_vitesses'].dropna().unique().tolist())
                boite_sel = st.selectbox("Boîte", boites)
            with g4:
                ann = sorted(df_v['annee'].dropna().astype(int).unique().tolist())
                annee_range = st.slider("Année", min(ann), max(ann), (min(ann), max(ann))) if ann else (2000,2026)
            st.markdown('</div>', unsafe_allow_html=True)

            df_vf = df_v.copy()
            if marque_sel != "Toutes": df_vf = df_vf[df_vf['marque']         == marque_sel]
            if region_sel != "Toutes": df_vf = df_vf[df_vf['region']         == region_sel]
            if boite_sel  != "Toutes": df_vf = df_vf[df_vf['boite_vitesses'] == boite_sel]
            df_vf = df_vf[df_vf['annee'].between(annee_range[0], annee_range[1], inclusive='both')]

            if df_vf.empty:
                st.warning("Aucun résultat pour ces filtres.")
            else:
                v_left, v_right = st.columns([3, 2])
                with v_left:
                    st.markdown('<div class="chart-panel"><div class="chart-panel-title">Top 10 marques</div>', unsafe_allow_html=True)
                    mc = df_vf['marque'].value_counts().head(10).reset_index()
                    mc.columns=['Marque','Nombre']
                    fig4 = px.bar(mc, x='Nombre', y='Marque', orientation='h',
                                  color_discrete_sequence=[BLEU])
                    fig4.update_layout(**pl(300),
                        xaxis=dict(gridcolor='#f0f4f8'),
                        yaxis=dict(gridcolor='rgba(0,0,0,0)', categoryorder='total ascending'))
                    st.plotly_chart(fig4, use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)

                with v_right:
                    st.markdown('<div class="chart-panel"><div class="chart-panel-title">Boîte de vitesses</div>', unsafe_allow_html=True)
                    bv = df_vf['boite_vitesses'].value_counts().reset_index()
                    bv.columns=['Type','Nombre']
                    fig5 = px.pie(bv, names='Type', values='Nombre', hole=0.5,
                                  color_discrete_sequence=[BLEU, BLEU2, '#a8c8e8'])
                    fig5.update_layout(**pl(300), legend=dict(bgcolor='rgba(0,0,0,0)', orientation='h', y=-0.1))
                    st.plotly_chart(fig5, use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)

                v2_left, v2_right = st.columns(2)
                with v2_left:
                    st.markdown('<div class="chart-panel"><div class="chart-panel-title">Top 8 régions</div>', unsafe_allow_html=True)
                    rg = df_vf['region'].value_counts().head(8).reset_index()
                    rg.columns=['Région','Nombre']
                    fig6 = px.bar(rg, x='Région', y='Nombre', color_discrete_sequence=[BLEU2])
                    fig6.update_layout(**pl(240),
                        xaxis=dict(gridcolor='rgba(0,0,0,0)', tickangle=-30),
                        yaxis=dict(gridcolor='#f0f4f8'))
                    st.plotly_chart(fig6, use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)

                with v2_right:
                    st.markdown('<div class="chart-panel"><div class="chart-panel-title">Distribution par année</div>', unsafe_allow_html=True)
                    fig7 = px.histogram(df_vf['annee'].dropna().astype(int), nbins=20,
                                        color_discrete_sequence=[BLEU])
                    fig7.update_layout(**pl(240),
                        xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                        yaxis=dict(gridcolor='#f0f4f8'), showlegend=False)
                    st.plotly_chart(fig7, use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('<div class="chart-panel"><div class="chart-panel-title">Aperçu des données</div>', unsafe_allow_html=True)
                st.dataframe(df_vf.head(50), use_container_width=True, hide_index=True)
                st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════
# FORMULAIRES
# ════════════════════════════════════════════
with tab_forms:
    st.markdown('<div class="page-body">', unsafe_allow_html=True)
    st.markdown('<div class="section-head">Formulaires d\'évaluation</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("""
        <div class="form-card">
            <div class="form-card-title">📋 KoboToolbox</div>
            <div class="form-card-desc">Formulaire d'évaluation hébergé sur KoboToolbox. Fonctionne hors ligne, idéal pour la collecte terrain. Les réponses sont centralisées en temps réel.</div>
        </div>""", unsafe_allow_html=True)
        st.link_button("Ouvrir KoboToolbox →", KOBO_URL, use_container_width=True)
    with col2:
        st.markdown("""
        <div class="form-card">
            <div class="form-card-title">📝 Google Forms</div>
            <div class="form-card-desc">Formulaire d'évaluation hébergé sur Google Forms. Accessible partout, les réponses sont automatiquement collectées dans Google Sheets.</div>
        </div>""", unsafe_allow_html=True)
        st.link_button("Ouvrir Google Forms →", GFORMS_URL, use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)
