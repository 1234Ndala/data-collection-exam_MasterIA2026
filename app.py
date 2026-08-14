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

# ── DB ──────────────────────────────────────
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

# ── SELENIUM ────────────────────────────────
def get_driver():
    options = Options()
    for a in ["--headless","--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--window-size=1920,1080"]:
        options.add_argument(a)
    return webdriver.Chrome(options=options)

# ── NETTOYAGE ───────────────────────────────
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

# ── SCRAPING BOOKS ───────────────────────────
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

# ── SCRAPING GAARAAS ─────────────────────────
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

# ── INIT ────────────────────────────────────
init_db()
n_books    = get_db_count('books')
n_voitures = get_db_count('voitures')

# ── CSS ─────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

html, body, [class*="css"], .stApp {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
}

.stApp { background: #0d1117; }

[data-testid="stSidebar"] {
    background: #0d1117;
    border-right: 1px solid #21262d;
}
[data-testid="stSidebar"] * { color: #8b949e !important; }
[data-testid="stSidebar"] .stRadio label {
    font-size: 13px;
    font-weight: 500;
    padding: 7px 10px;
    border-radius: 6px;
    margin-bottom: 2px;
    display: block;
    color: #8b949e !important;
    transition: background 0.15s;
}
[data-testid="stSidebar"] .stRadio label:hover { background: #161b22; }

.sb-logo {
    font-size: 13px;
    font-weight: 700;
    color: #f0f6fc !important;
    letter-spacing: 0.01em;
    margin-bottom: 4px;
}
.sb-meta {
    font-size: 11px;
    color: #484f58 !important;
    margin-bottom: 20px;
    padding-bottom: 16px;
    border-bottom: 1px solid #21262d;
}
.sb-stat {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 14px 16px;
    margin-bottom: 8px;
}
.sb-stat-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #484f58 !important;
    margin-bottom: 4px;
}
.sb-stat-val {
    font-size: 24px;
    font-weight: 700;
    color: #f0f6fc !important;
}

/* Page header */
.ph {
    margin: 8px 0 28px 0;
    padding-bottom: 20px;
    border-bottom: 1px solid #21262d;
}
.ph-title {
    font-size: 22px;
    font-weight: 700;
    color: #f0f6fc;
    letter-spacing: -0.01em;
}
.ph-desc {
    font-size: 13px;
    color: #484f58;
    margin-top: 3px;
}

/* KPI cards */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4,1fr);
    gap: 12px;
    margin-bottom: 28px;
}
.kpi {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 18px 20px;
}
.kpi-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: #484f58;
    margin-bottom: 10px;
}
.kpi-val {
    font-size: 28px;
    font-weight: 700;
    color: #f0f6fc;
    line-height: 1;
}
.kpi-val.ok  { font-size: 13px; color: #3fb950; margin-top:6px; font-weight:600; }
.kpi-val.ko  { font-size: 13px; color: #f85149; margin-top:6px; font-weight:600; }
.kpi-hint    { font-size: 11px; color: #484f58; margin-top:4px; }

/* Section label */
.slabel {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #484f58;
    margin: 28px 0 12px 0;
}

/* Info rows */
.irow {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid #21262d;
    font-size: 13px;
}
.irow:last-child { border-bottom:none; }
.irow-k { color: #8b949e; font-weight:500; }
.irow-v {
    font-size: 12px;
    font-weight: 600;
    color: #58a6ff;
    background: #1c2128;
    padding: 3px 10px;
    border-radius: 5px;
    border: 1px solid #21262d;
}

/* Scraping panel */
.scrape-panel {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 28px;
    max-width: 520px;
}

/* Formulaires */
.form-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 28px;
    height: 100%;
}
.form-card-title {
    font-size: 16px;
    font-weight: 700;
    color: #f0f6fc;
    margin-bottom: 8px;
}
.form-card-desc {
    font-size: 13px;
    color: #8b949e;
    line-height: 1.65;
    margin-bottom: 22px;
}
</style>
""", unsafe_allow_html=True)

# ── SIDEBAR ──────────────────────────────────
st.sidebar.markdown(f'<div class="sb-logo">Data Collection</div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="sb-meta">Master IA · DIT Dakar · Examen 2026</div>', unsafe_allow_html=True)

PAGES = ["Accueil", "Scraping Live", "Téléchargement CSV", "Dashboard", "Formulaires"]
page  = st.sidebar.radio("", PAGES, label_visibility="collapsed")

st.sidebar.markdown("<br>", unsafe_allow_html=True)
st.sidebar.markdown(f"""
<div class="sb-stat">
    <div class="sb-stat-label">Books en base</div>
    <div class="sb-stat-val">{n_books:,}</div>
</div>
<div class="sb-stat">
    <div class="sb-stat-label">Voitures en base</div>
    <div class="sb-stat-val">{n_voitures:,}</div>
</div>
""", unsafe_allow_html=True)

# ── ACCUEIL ──────────────────────────────────
if page == "Accueil":
    books_ok   = os.path.exists(CSV_BOOKS_RAW)
    gaaraas_ok = os.path.exists(CSV_GAARAAS_RAW)

    st.markdown("""
    <div class="ph">
        <div class="ph-title">Projet Data Collection</div>
        <div class="ph-desc">Master Intelligence Artificielle — DIT Dakar · Examen 2026</div>
    </div>""", unsafe_allow_html=True)

    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi">
            <div class="kpi-label">Books en base</div>
            <div class="kpi-val">{n_books:,}</div>
            <div class="kpi-hint">books.toscrape.com</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">Voitures en base</div>
            <div class="kpi-val">{n_voitures:,}</div>
            <div class="kpi-hint">gaaraas.com</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">CSV Books</div>
            <div class="kpi-val ok">{'✓ Présent' if books_ok else '✗ Absent'}</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">CSV Gaaraas</div>
            <div class="kpi-val {'ok' if gaaraas_ok else 'ko'}">{'✓ Présent' if gaaraas_ok else '✗ Absent'}</div>
        </div>
    </div>""", unsafe_allow_html=True)

    st.markdown('<div class="slabel">Sources de données</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="irow"><span class="irow-k">Books to Scrape</span><span class="irow-v">50 pages · 9 variables · Selenium</span></div>
    <div class="irow"><span class="irow-k">Gaaraas Dakar Auto</span><span class="irow-v">100 pages · 7 variables · Selenium</span></div>
    <div class="irow"><span class="irow-k">Outil no-code</span><span class="irow-v">Web Scraper (Chrome)</span></div>
    <div class="irow"><span class="irow-k">Stockage</span><span class="irow-v">SQLite · 2 tables</span></div>
    """, unsafe_allow_html=True)

# ── SCRAPING LIVE ─────────────────────────────
elif page == "Scraping Live":
    st.markdown("""
    <div class="ph">
        <div class="ph-title">Scraping Live</div>
        <div class="ph-desc">Collecte via Selenium · stockage automatique en SQLite</div>
    </div>""", unsafe_allow_html=True)

    st.markdown('<div class="scrape-panel">', unsafe_allow_html=True)
    source = st.selectbox("Source à scraper", ["Books to Scrape", "Gaaraas"])
    if source == "Books to Scrape":
        nb_pages = st.slider("Nombre de pages", 1, 50, 5)
        st.caption(f"~{nb_pages*20} livres estimés")
        if st.button("Lancer le scraping", type="primary"):
            pb = st.progress(0); txt = st.empty()
            with st.spinner("Scraping en cours..."):
                n, err = scrape_books(nb_pages, pb, txt)
            st.success(f"{n} livres insérés ({err} erreurs).")
    else:
        nb_pages = st.slider("Nombre de pages", 1, 100, 5)
        st.caption(f"~{nb_pages*15} annonces estimées")
        if st.button("Lancer le scraping", type="primary"):
            pb = st.progress(0); txt = st.empty()
            with st.spinner("Scraping en cours..."):
                n, err = scrape_gaaraas(nb_pages, pb, txt)
            st.success(f"{n} annonces insérées ({err} erreurs).")
    st.markdown('</div>', unsafe_allow_html=True)

# ── TÉLÉCHARGEMENT CSV ────────────────────────
elif page == "Téléchargement CSV":
    st.markdown("""
    <div class="ph">
        <div class="ph-title">Données brutes</div>
        <div class="ph-desc">Fichiers collectés via Web Scraper — non nettoyés</div>
    </div>""", unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown('<div class="slabel">Books to Scrape</div>', unsafe_allow_html=True)
        if os.path.exists(CSV_BOOKS_RAW):
            with open(CSV_BOOKS_RAW,"rb") as f:
                st.download_button("Télécharger le CSV", f, CSV_BOOKS_RAW, "text/csv", use_container_width=True)
            st.dataframe(pd.read_csv(CSV_BOOKS_RAW, nrows=5), use_container_width=True)
        else:
            st.warning(f"Fichier introuvable : `{CSV_BOOKS_RAW}`")
    with col2:
        st.markdown('<div class="slabel">Gaaraas</div>', unsafe_allow_html=True)
        if os.path.exists(CSV_GAARAAS_RAW):
            with open(CSV_GAARAAS_RAW,"rb") as f:
                st.download_button("Télécharger le CSV", f, CSV_GAARAAS_RAW, "text/csv", use_container_width=True)
            st.dataframe(pd.read_csv(CSV_GAARAAS_RAW, nrows=5), use_container_width=True)
        else:
            st.warning(f"Fichier introuvable : `{CSV_GAARAAS_RAW}`")

# ── DASHBOARD ─────────────────────────────────
elif page == "Dashboard":
    import plotly.express as px

    BG   = '#0d1117'
    CARD = '#161b22'
    GRID = '#21262d'
    FC   = '#8b949e'
    C1   = '#58a6ff'
    C2   = '#3fb950'
    C3   = '#f78166'
    C4   = '#d2a8ff'

    def pl(h=300):
        return dict(plot_bgcolor=CARD, paper_bgcolor=BG,
                    font_color=FC, height=h,
                    margin=dict(l=0,r=0,t=20,b=0),
                    font=dict(family='Plus Jakarta Sans'))

    st.markdown("""
    <div class="ph">
        <div class="ph-title">Dashboard</div>
        <div class="ph-desc">Données nettoyées · SQLite</div>
    </div>""", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📚  Books to Scrape", "🚗  Gaaraas"])

    with tab1:
        df_b = load_table('books')
        if df_b.empty:
            st.info("Aucune donnée. Lancez un scraping d'abord.")
        else:
            # ── Filtres ──────────────────────────────
            st.markdown('<div class="slabel">Filtres</div>', unsafe_allow_html=True)
            f1, f2, f3 = st.columns(3)
            with f1:
                cats = ["Toutes"] + sorted(df_b['categorie'].dropna().unique().tolist())
                cat_sel = st.selectbox("Catégorie", cats)
            with f2:
                notes = ["Toutes"] + sorted(df_b['note'].dropna().unique().astype(int).tolist())
                note_sel = st.selectbox("Note", notes)
            with f3:
                dispo_opts = ["Toutes"] + df_b['disponibilite'].dropna().unique().tolist()
                dispo_sel = st.selectbox("Disponibilité", dispo_opts)

            df_f = df_b.copy()
            if cat_sel   != "Toutes": df_f = df_f[df_f['categorie']    == cat_sel]
            if note_sel  != "Toutes": df_f = df_f[df_f['note']         == int(note_sel)]
            if dispo_sel != "Toutes": df_f = df_f[df_f['disponibilite']== dispo_sel]

            st.markdown('<div class="slabel">Indicateurs</div>', unsafe_allow_html=True)
            k1,k2,k3,k4 = st.columns(4)
            k1.metric("Livres", f"{len(df_f):,}")
            k2.metric("Prix moyen", f"£{df_f['prix'].mean():.2f}" if not df_f.empty else "—")
            k3.metric("Note moyenne", f"{df_f['note'].mean():.1f}/5" if not df_f.empty else "—")
            k4.metric("Catégories", df_f['categorie'].nunique())

            if df_f.empty:
                st.warning("Aucun résultat pour ces filtres.")
            else:
                st.markdown('<div class="slabel">Top 10 catégories</div>', unsafe_allow_html=True)
                cc = df_f['categorie'].value_counts().head(10).reset_index()
                cc.columns=['Catégorie','Nombre']
                fig1 = px.bar(cc, x='Nombre', y='Catégorie', orientation='h',
                              color_discrete_sequence=[C1])
                fig1.update_layout(**pl(300),
                    xaxis=dict(gridcolor=GRID),
                    yaxis=dict(gridcolor='rgba(0,0,0,0)', categoryorder='total ascending'))
                st.plotly_chart(fig1, use_container_width=True)

                ca, cb = st.columns(2)
                with ca:
                    st.markdown('<div class="slabel">Distribution des notes</div>', unsafe_allow_html=True)
                    nc = df_f['note'].value_counts().sort_index().reset_index()
                    nc.columns=['Note','Nombre']; nc['Note']=nc['Note'].astype(str)
                    fig2 = px.bar(nc, x='Note', y='Nombre', color_discrete_sequence=[C4])
                    fig2.update_layout(**pl(260),
                        xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                        yaxis=dict(gridcolor=GRID))
                    st.plotly_chart(fig2, use_container_width=True)
                with cb:
                    st.markdown('<div class="slabel">Disponibilité</div>', unsafe_allow_html=True)
                    dp = df_f['disponibilite'].value_counts().reset_index()
                    dp.columns=['Statut','Nombre']
                    fig3 = px.pie(dp, names='Statut', values='Nombre', hole=0.55,
                                  color_discrete_sequence=[C2, C3])
                    fig3.update_layout(**pl(260), legend=dict(bgcolor='rgba(0,0,0,0)'))
                    st.plotly_chart(fig3, use_container_width=True)

                st.markdown('<div class="slabel">Aperçu des données</div>', unsafe_allow_html=True)
                st.dataframe(df_f.head(50), use_container_width=True, hide_index=True)

    with tab2:
        df_v = load_table('voitures')
        if df_v.empty:
            st.info("Aucune donnée. Lancez un scraping d'abord.")
        else:
            # ── Filtres ──────────────────────────────
            st.markdown('<div class="slabel">Filtres</div>', unsafe_allow_html=True)
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
                annees_dispo = sorted(df_v['annee'].dropna().astype(int).unique().tolist())
                if annees_dispo:
                    annee_range = st.slider("Année", min_value=min(annees_dispo),
                                            max_value=max(annees_dispo),
                                            value=(min(annees_dispo), max(annees_dispo)))
                else:
                    annee_range = (2000, 2026)

            df_vf = df_v.copy()
            if marque_sel != "Toutes": df_vf = df_vf[df_vf['marque']        == marque_sel]
            if region_sel != "Toutes": df_vf = df_vf[df_vf['region']        == region_sel]
            if boite_sel  != "Toutes": df_vf = df_vf[df_vf['boite_vitesses']== boite_sel]
            df_vf = df_vf[df_vf['annee'].between(annee_range[0], annee_range[1], inclusive='both')]

            st.markdown('<div class="slabel">Indicateurs</div>', unsafe_allow_html=True)
            k1,k2,k3,k4 = st.columns(4)
            k1.metric("Annonces", f"{len(df_vf):,}")
            k2.metric("Prix moyen (FCFA)", f"{df_vf['prix'].mean():,.0f}" if not df_vf.empty else "—")
            k3.metric("Km moyen", f"{df_vf['kilometrage'].mean():,.0f}" if not df_vf.empty else "—")
            k4.metric("Marques", df_vf['marque'].nunique())

            if df_vf.empty:
                st.warning("Aucun résultat pour ces filtres.")
            else:
                st.markdown('<div class="slabel">Top 10 marques</div>', unsafe_allow_html=True)
                mc = df_vf['marque'].value_counts().head(10).reset_index()
                mc.columns=['Marque','Nombre']
                fig4 = px.bar(mc, x='Nombre', y='Marque', orientation='h',
                              color_discrete_sequence=[C1])
                fig4.update_layout(**pl(300),
                    xaxis=dict(gridcolor=GRID),
                    yaxis=dict(gridcolor='rgba(0,0,0,0)', categoryorder='total ascending'))
                st.plotly_chart(fig4, use_container_width=True)

                cc2, cd2 = st.columns(2)
                with cc2:
                    st.markdown('<div class="slabel">Boîte de vitesses</div>', unsafe_allow_html=True)
                    bv = df_vf['boite_vitesses'].value_counts().reset_index()
                    bv.columns=['Type','Nombre']
                    fig5 = px.pie(bv, names='Type', values='Nombre', hole=0.55,
                                  color_discrete_sequence=[C1, C4, C2])
                    fig5.update_layout(**pl(260), legend=dict(bgcolor='rgba(0,0,0,0)'))
                    st.plotly_chart(fig5, use_container_width=True)
                with cd2:
                    st.markdown('<div class="slabel">Top 8 régions</div>', unsafe_allow_html=True)
                    rg = df_vf['region'].value_counts().head(8).reset_index()
                    rg.columns=['Région','Nombre']
                    fig6 = px.bar(rg, x='Région', y='Nombre',
                                  color_discrete_sequence=[C4])
                    fig6.update_layout(**pl(260),
                        xaxis=dict(gridcolor='rgba(0,0,0,0)', tickangle=-30),
                        yaxis=dict(gridcolor=GRID))
                    st.plotly_chart(fig6, use_container_width=True)

                st.markdown('<div class="slabel">Distribution par année</div>', unsafe_allow_html=True)
                an = df_vf['annee'].dropna().astype(int)
                fig7 = px.histogram(an, nbins=20, color_discrete_sequence=[C2])
                fig7.update_layout(**pl(220),
                    xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                    yaxis=dict(gridcolor=GRID), showlegend=False)
                st.plotly_chart(fig7, use_container_width=True)

                st.markdown('<div class="slabel">Aperçu des données</div>', unsafe_allow_html=True)
                st.dataframe(df_vf.head(50), use_container_width=True, hide_index=True)

# ── FORMULAIRES ───────────────────────────────
elif page == "Formulaires":
    st.markdown("""
    <div class="ph">
        <div class="ph-title">Formulaires d'évaluation</div>
        <div class="ph-desc">KoboToolbox · Google Forms</div>
    </div>""", unsafe_allow_html=True)

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
            <div class="form-card-desc">Formulaire d'évaluation hébergé sur Google Forms. Accessible depuis n'importe quel appareil, les réponses sont automatiquement collectées dans Google Sheets.</div>
        </div>""", unsafe_allow_html=True)
        st.link_button("Ouvrir Google Forms →", GFORMS_URL, use_container_width=True)
