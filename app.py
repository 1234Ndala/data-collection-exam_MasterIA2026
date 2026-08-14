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

# ═══════════════════════════════════════════════
# CSS — BLANC / NOIR TRANCHÉ, ACCENTS CITRON
# ═══════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&family=Inter:wght@400;500&display=swap');

*, html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    box-sizing: border-box;
}

.stApp { background: #ffffff; }

/* ─── Sidebar ─── */
[data-testid="stSidebar"] {
    background: #111111 !important;
    border-right: none !important;
    width: 220px !important;
}
[data-testid="stSidebar"] * { color: #888 !important; }

.sb-name {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 16px;
    font-weight: 800;
    color: #ffffff !important;
    letter-spacing: -0.01em;
    margin-bottom: 2px;
}
.sb-course {
    font-size: 10px;
    color: #444 !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid #222;
}

/* nav items */
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
    gap: 2px !important;
    display: flex;
    flex-direction: column;
}
[data-testid="stSidebar"] .stRadio label {
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #555 !important;
    padding: 9px 12px !important;
    border-radius: 8px !important;
    margin: 0 !important;
}
[data-testid="stSidebar"] .stRadio label:hover { background: #1a1a1a !important; color: #fff !important; }

.sb-divider { border: none; border-top: 1px solid #222; margin: 20px 0; }

.sb-counter {
    margin-bottom: 10px;
}
.sb-counter-n {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 36px;
    font-weight: 800;
    color: #d4f542 !important;
    line-height: 1;
}
.sb-counter-l {
    font-size: 10px;
    color: #444 !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 2px;
}

/* ─── Page layout ─── */
.block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* ─── Page header : bande noire pleine largeur ─── */
.phead {
    background: #111111;
    padding: 32px 40px 28px;
    margin: -1rem -1rem 0 -1rem;
}
.phead-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    color: #d4f542;
    margin-bottom: 8px;
}
.phead-title {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 34px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.02em;
    line-height: 1.1;
}
.phead-sub {
    font-size: 13px;
    color: #555;
    margin-top: 5px;
}

/* ─── Contenu principal ─── */
.main-content {
    padding: 32px 40px;
    margin: 0 -1rem;
}

/* ─── KPI strip ─── */
.kpi-strip {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 40px;
}
.kpi-box {
    border: 1.5px solid #e8e8e8;
    border-radius: 12px;
    padding: 20px 22px;
    background: #fafafa;
}
.kpi-box-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #aaa;
    margin-bottom: 10px;
}
.kpi-box-val {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 36px;
    font-weight: 800;
    color: #111;
    line-height: 1;
}
.kpi-box-val.ok { font-size: 14px; color: #16a34a; font-weight: 600; margin-top: 6px; }
.kpi-box-val.ko { font-size: 14px; color: #dc2626; font-weight: 600; margin-top: 6px; }
.kpi-box-hint   { font-size: 11px; color: #bbb; margin-top: 4px; }

/* ─── Tableau sources ─── */
.src-table { border-top: 1.5px solid #111; }
.src-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 0;
    border-bottom: 1px solid #f0f0f0;
    font-size: 13px;
}
.src-k { color: #111; font-weight: 600; }
.src-v {
    background: #d4f542;
    color: #111;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 20px;
}

/* ─── Section label ─── */
.slbl {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: #aaa;
    margin: 32px 0 14px 0;
    display: flex;
    align-items: center;
    gap: 10px;
}
.slbl::after { content:''; flex:1; height:1px; background:#f0f0f0; }

/* ─── Filtres ─── */
.filter-bar {
    background: #fafafa;
    border: 1.5px solid #e8e8e8;
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 28px;
}

/* ─── Scraping ─── */
.scrape-box {
    border: 1.5px solid #e8e8e8;
    border-radius: 12px;
    padding: 28px;
    background: #fafafa;
    max-width: 500px;
}

/* ─── Formulaires ─── */
.form-card {
    border: 1.5px solid #e8e8e8;
    border-radius: 12px;
    padding: 28px;
    background: #fafafa;
}
.form-card-title {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 20px;
    font-weight: 800;
    color: #111;
    margin-bottom: 10px;
}
.form-card-desc { font-size: 13px; color: #888; line-height: 1.7; margin-bottom: 22px; }

/* Plotly charts : fond blanc */
.js-plotly-plot .plotly { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════
st.sidebar.markdown('<div class="sb-name">Data Collection</div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="sb-course">Master IA · DIT Dakar · 2026</div>', unsafe_allow_html=True)

PAGES = ["Accueil", "Scraping Live", "Téléchargement CSV", "Dashboard", "Formulaires"]
page  = st.sidebar.radio("", PAGES, label_visibility="collapsed")

st.sidebar.markdown("<hr class='sb-divider'>", unsafe_allow_html=True)
st.sidebar.markdown(f"""
<div class="sb-counter">
    <div class="sb-counter-n">{n_books:,}</div>
    <div class="sb-counter-l">Books en base</div>
</div>
<div class="sb-counter">
    <div class="sb-counter-n">{n_voitures:,}</div>
    <div class="sb-counter-l">Voitures en base</div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════
# HELPER PLOTLY
# ═══════════════════════════════════════════════
def pl(h=300):
    return dict(
        plot_bgcolor='#ffffff', paper_bgcolor='#ffffff',
        font_color='#888', height=h,
        margin=dict(l=0,r=0,t=20,b=0),
        font=dict(family='Inter'),
    )

CITRON = '#d4f542'
NOIR   = '#111111'
GRIS   = '#e8e8e8'
BLU    = '#4f6ef7'
ROS    = '#f74f6e'
VER    = '#22c55e'

# ═══════════════════════════════════════════════
# ACCUEIL
# ═══════════════════════════════════════════════
if page == "Accueil":
    books_ok   = os.path.exists(CSV_BOOKS_RAW)
    gaaraas_ok = os.path.exists(CSV_GAARAAS_RAW)

    st.markdown("""
    <div class="phead">
        <div class="phead-label">Vue d'ensemble</div>
        <div class="phead-title">Projet Data Collection</div>
        <div class="phead-sub">Master Intelligence Artificielle — DIT Dakar · Examen 2026</div>
    </div>
    <div class="main-content">
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="kpi-strip">
        <div class="kpi-box">
            <div class="kpi-box-label">Books en base</div>
            <div class="kpi-box-val">{n_books:,}</div>
            <div class="kpi-box-hint">books.toscrape.com</div>
        </div>
        <div class="kpi-box">
            <div class="kpi-box-label">Voitures en base</div>
            <div class="kpi-box-val">{n_voitures:,}</div>
            <div class="kpi-box-hint">gaaraas.com</div>
        </div>
        <div class="kpi-box">
            <div class="kpi-box-label">CSV Books</div>
            <div class="kpi-box-val ok">{'✓ Présent' if books_ok else '✗ Absent'}</div>
        </div>
        <div class="kpi-box">
            <div class="kpi-box-label">CSV Gaaraas</div>
            <div class="kpi-box-val {'ok' if gaaraas_ok else 'ko'}">{'✓ Présent' if gaaraas_ok else '✗ Absent'}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="slbl">Sources de données</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="src-table">
        <div class="src-row"><span class="src-k">Books to Scrape</span><span class="src-v">50 pages · 9 variables · Selenium</span></div>
        <div class="src-row"><span class="src-k">Gaaraas Dakar Auto</span><span class="src-v">100 pages · 7 variables · Selenium</span></div>
        <div class="src-row"><span class="src-k">Outil no-code</span><span class="src-v">Web Scraper Chrome</span></div>
        <div class="src-row"><span class="src-k">Stockage</span><span class="src-v">SQLite · 2 tables</span></div>
    </div>
    </div>
    """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════
# SCRAPING LIVE
# ═══════════════════════════════════════════════
elif page == "Scraping Live":
    st.markdown("""
    <div class="phead">
        <div class="phead-label">Collecte</div>
        <div class="phead-title">Scraping Live</div>
        <div class="phead-sub">Selenium · stockage automatique SQLite</div>
    </div>
    <div class="main-content">
    """, unsafe_allow_html=True)

    st.markdown('<div class="scrape-box">', unsafe_allow_html=True)
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
    st.markdown('</div></div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════
# TÉLÉCHARGEMENT CSV
# ═══════════════════════════════════════════════
elif page == "Téléchargement CSV":
    st.markdown("""
    <div class="phead">
        <div class="phead-label">Export</div>
        <div class="phead-title">Données brutes</div>
        <div class="phead-sub">Fichiers collectés via Web Scraper — non nettoyés</div>
    </div>
    <div class="main-content">
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown('<div class="slbl">Books to Scrape</div>', unsafe_allow_html=True)
        if os.path.exists(CSV_BOOKS_RAW):
            with open(CSV_BOOKS_RAW,"rb") as f:
                st.download_button("Télécharger le CSV", f, CSV_BOOKS_RAW, "text/csv", use_container_width=True)
            st.dataframe(pd.read_csv(CSV_BOOKS_RAW, nrows=5), use_container_width=True)
        else:
            st.warning(f"Fichier introuvable : `{CSV_BOOKS_RAW}`")
    with col2:
        st.markdown('<div class="slbl">Gaaraas</div>', unsafe_allow_html=True)
        if os.path.exists(CSV_GAARAAS_RAW):
            with open(CSV_GAARAAS_RAW,"rb") as f:
                st.download_button("Télécharger le CSV", f, CSV_GAARAAS_RAW, "text/csv", use_container_width=True)
            st.dataframe(pd.read_csv(CSV_GAARAAS_RAW, nrows=5), use_container_width=True)
        else:
            st.warning(f"Fichier introuvable : `{CSV_GAARAAS_RAW}`")
    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════
elif page == "Dashboard":
    import plotly.express as px

    st.markdown("""
    <div class="phead">
        <div class="phead-label">Analyse</div>
        <div class="phead-title">Dashboard</div>
        <div class="phead-sub">Données nettoyées · SQLite</div>
    </div>
    <div class="main-content">
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📚  Books to Scrape", "🚗  Gaaraas"])

    with tab1:
        df_b = load_table('books')
        if df_b.empty:
            st.info("Aucune donnée. Lancez un scraping d'abord.")
        else:
            # Filtres
            st.markdown('<div class="filter-bar">', unsafe_allow_html=True)
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

            k1,k2,k3,k4 = st.columns(4)
            k1.metric("Livres",       f"{len(df_f):,}")
            k2.metric("Prix moyen",   f"£{df_f['prix'].mean():.2f}"       if not df_f.empty else "—")
            k3.metric("Note moy.",    f"{df_f['note'].mean():.1f}/5"       if not df_f.empty else "—")
            k4.metric("Catégories",   df_f['categorie'].nunique())

            if not df_f.empty:
                st.markdown('<div class="slbl">Top 10 catégories</div>', unsafe_allow_html=True)
                cc = df_f['categorie'].value_counts().head(10).reset_index()
                cc.columns=['Catégorie','Nombre']
                fig1 = px.bar(cc, x='Nombre', y='Catégorie', orientation='h',
                              color_discrete_sequence=[NOIR])
                fig1.update_layout(**pl(280),
                    xaxis=dict(gridcolor='#f0f0f0'),
                    yaxis=dict(gridcolor='rgba(0,0,0,0)', categoryorder='total ascending'))
                st.plotly_chart(fig1, use_container_width=True)

                ca, cb = st.columns(2)
                with ca:
                    st.markdown('<div class="slbl">Notes</div>', unsafe_allow_html=True)
                    nc = df_f['note'].value_counts().sort_index().reset_index()
                    nc.columns=['Note','N']; nc['Note']=nc['Note'].astype(str)
                    fig2 = px.bar(nc, x='Note', y='N', color_discrete_sequence=[BLU])
                    fig2.update_layout(**pl(240),
                        xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                        yaxis=dict(gridcolor='#f0f0f0'))
                    st.plotly_chart(fig2, use_container_width=True)
                with cb:
                    st.markdown('<div class="slbl">Disponibilité</div>', unsafe_allow_html=True)
                    dp = df_f['disponibilite'].value_counts().reset_index()
                    dp.columns=['Statut','N']
                    fig3 = px.pie(dp, names='Statut', values='N', hole=0.6,
                                  color_discrete_sequence=[NOIR, '#e8e8e8'])
                    fig3.update_layout(**pl(240), legend=dict(bgcolor='rgba(0,0,0,0)'))
                    st.plotly_chart(fig3, use_container_width=True)

                st.markdown('<div class="slbl">Données</div>', unsafe_allow_html=True)
                st.dataframe(df_f.head(50), use_container_width=True, hide_index=True)

    with tab2:
        df_v = load_table('voitures')
        if df_v.empty:
            st.info("Aucune donnée. Lancez un scraping d'abord.")
        else:
            st.markdown('<div class="filter-bar">', unsafe_allow_html=True)
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

            k1,k2,k3,k4 = st.columns(4)
            k1.metric("Annonces",         f"{len(df_vf):,}")
            k2.metric("Prix moyen (FCFA)", f"{df_vf['prix'].mean():,.0f}"        if not df_vf.empty else "—")
            k3.metric("Km moyen",          f"{df_vf['kilometrage'].mean():,.0f}" if not df_vf.empty else "—")
            k4.metric("Marques",           df_vf['marque'].nunique())

            if not df_vf.empty:
                st.markdown('<div class="slbl">Top 10 marques</div>', unsafe_allow_html=True)
                mc = df_vf['marque'].value_counts().head(10).reset_index()
                mc.columns=['Marque','Nombre']
                fig4 = px.bar(mc, x='Nombre', y='Marque', orientation='h',
                              color_discrete_sequence=[NOIR])
                fig4.update_layout(**pl(280),
                    xaxis=dict(gridcolor='#f0f0f0'),
                    yaxis=dict(gridcolor='rgba(0,0,0,0)', categoryorder='total ascending'))
                st.plotly_chart(fig4, use_container_width=True)

                cc2, cd2 = st.columns(2)
                with cc2:
                    st.markdown('<div class="slbl">Boîte de vitesses</div>', unsafe_allow_html=True)
                    bv = df_vf['boite_vitesses'].value_counts().reset_index()
                    bv.columns=['Type','N']
                    fig5 = px.pie(bv, names='Type', values='N', hole=0.6,
                                  color_discrete_sequence=[NOIR,'#555','#aaa'])
                    fig5.update_layout(**pl(240), legend=dict(bgcolor='rgba(0,0,0,0)'))
                    st.plotly_chart(fig5, use_container_width=True)
                with cd2:
                    st.markdown('<div class="slbl">Top 8 régions</div>', unsafe_allow_html=True)
                    rg = df_vf['region'].value_counts().head(8).reset_index()
                    rg.columns=['Région','N']
                    fig6 = px.bar(rg, x='Région', y='N', color_discrete_sequence=[BLU])
                    fig6.update_layout(**pl(240),
                        xaxis=dict(gridcolor='rgba(0,0,0,0)', tickangle=-30),
                        yaxis=dict(gridcolor='#f0f0f0'))
                    st.plotly_chart(fig6, use_container_width=True)

                st.markdown('<div class="slbl">Distribution par année</div>', unsafe_allow_html=True)
                fig7 = px.histogram(df_vf['annee'].dropna().astype(int), nbins=20,
                                    color_discrete_sequence=[VER])
                fig7.update_layout(**pl(200),
                    xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                    yaxis=dict(gridcolor='#f0f0f0'), showlegend=False)
                st.plotly_chart(fig7, use_container_width=True)

                st.markdown('<div class="slbl">Données</div>', unsafe_allow_html=True)
                st.dataframe(df_vf.head(50), use_container_width=True, hide_index=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════
# FORMULAIRES
# ═══════════════════════════════════════════════
elif page == "Formulaires":
    st.markdown("""
    <div class="phead">
        <div class="phead-label">Collecte primaire</div>
        <div class="phead-title">Formulaires</div>
        <div class="phead-sub">KoboToolbox · Google Forms</div>
    </div>
    <div class="main-content">
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("""
        <div class="form-card">
            <div class="form-card-title">KoboToolbox</div>
            <div class="form-card-desc">Formulaire d'évaluation hébergé sur KoboToolbox. Fonctionne hors ligne, idéal pour la collecte terrain. Réponses centralisées en temps réel.</div>
        </div>""", unsafe_allow_html=True)
        st.link_button("Ouvrir KoboToolbox →", KOBO_URL, use_container_width=True)
    with col2:
        st.markdown("""
        <div class="form-card">
            <div class="form-card-title">Google Forms</div>
            <div class="form-card-desc">Formulaire d'évaluation hébergé sur Google Forms. Accessible partout, réponses collectées automatiquement dans Google Sheets.</div>
        </div>""", unsafe_allow_html=True)
        st.link_button("Ouvrir Google Forms →", GFORMS_URL, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
