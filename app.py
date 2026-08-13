import streamlit as st
import pandas as pd
import sqlite3
import time
import re
import os
import tempfile
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

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

KOBO_URL = "https://ee.kobotoolbox.org/x/Xir2zltq"       # À remplacer
GFORMS_URL = "https://forms.google.com/lien-fictif"        # À remplacer

# ─────────────────────────────────────────────
# BASE DE DONNÉES
# ─────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS books (
            titre TEXT,
            prix REAL,
            disponibilite TEXT,
            nb_produits_page INTEGER,
            note INTEGER,
            nb_reviews INTEGER,
            description TEXT,
            categorie TEXT,
            tax REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS voitures (
            marque TEXT,
            modele TEXT,
            annee INTEGER,
            prix REAL,
            kilometrage INTEGER,
            boite_vitesses TEXT,
            region TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_db_count(table):
    try:
        conn = sqlite3.connect(DB_PATH)
        count = pd.read_sql_query(f"SELECT COUNT(*) as n FROM {table}", conn).iloc[0]['n']
        conn.close()
        return count
    except:
        return 0

def load_table(table):
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

def insert_books(rows):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executemany("INSERT INTO books VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()

def insert_voitures(rows):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executemany("INSERT INTO voitures VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
# SELENIUM — DRIVER
# ─────────────────────────────────────────────
def get_driver():
    # Streamlit Cloud : Chromium installé via packages.txt
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    return driver

# ─────────────────────────────────────────────
# NETTOYAGE — BOOKS
# ─────────────────────────────────────────────
note_map = {'One': 1, 'Two': 2, 'Three': 3, 'Four': 4, 'Five': 5}

def nettoyer_prix(v):
    try: return float(re.sub(r'[^0-9.]', '', v))
    except: return None

def nettoyer_tax(v):
    try: return float(re.sub(r'[^0-9.]', '', v))
    except: return None

def nettoyer_note(v):
    for mot, n in note_map.items():
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
    book_urls = []
    rows = []
    nb_erreurs = 0

    status_text.text("Collecte des URLs des livres...")
    for page in range(1, nb_pages + 1):
        url = f"https://books.toscrape.com/catalogue/page-{page}.html"
        driver.get(url)
        time.sleep(1)
        livres = driver.find_elements(By.CSS_SELECTOR, 'article.product_pod h3 a')
        for l in livres:
            book_urls.append(l.get_attribute('href'))
        progress_bar.progress(int(page / nb_pages * 40))

    status_text.text(f"{len(book_urls)} livres trouvés. Scraping des détails...")
    total = len(book_urls)

    for idx, url in enumerate(book_urls):
        try:
            driver.get(url)
            time.sleep(0.5)
            titre = driver.find_element(By.CSS_SELECTOR, 'div.product_main h1').text
            prix = nettoyer_prix(driver.find_element(By.CSS_SELECTOR, 'p.price_color').text)
            dispo = nettoyer_dispo(driver.find_element(By.CSS_SELECTOR, 'p.availability').text)
            note_el = driver.find_element(By.CSS_SELECTOR, 'p.star-rating')
            note = nettoyer_note(note_el.get_attribute('class'))
            lignes = driver.find_elements(By.CSS_SELECTOR, 'table.table tr')
            table_data = {}
            for ligne in lignes:
                try:
                    k = ligne.find_element(By.TAG_NAME, 'th').text.strip()
                    v = ligne.find_element(By.TAG_NAME, 'td').text.strip()
                    table_data[k] = v
                except: pass
            nb_reviews = int(table_data.get('Number of reviews', '0')) if table_data.get('Number of reviews', '0').isdigit() else 0
            tax = nettoyer_tax(table_data.get('Tax', '£0.00'))
            try: desc = driver.find_element(By.CSS_SELECTOR, 'article.product_page > p').text
            except: desc = 'N/A'
            try:
                bc = driver.find_elements(By.CSS_SELECTOR, 'ul.breadcrumb li')
                cat = bc[2].text.strip() if len(bc) >= 3 else 'N/A'
            except: cat = 'N/A'
            rows.append((titre, prix, dispo, 20, note, nb_reviews, desc, cat, tax))
        except:
            nb_erreurs += 1
        progress_bar.progress(40 + int((idx + 1) / total * 55))
        if (idx + 1) % 20 == 0:
            status_text.text(f"{idx + 1}/{total} livres traités...")

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
    rows = []
    nb_erreurs = 0

    for page in range(1, nb_pages + 1):
        url = f"https://www.gaaraas.com/fr/users/dakar-auto?page={page}"
        try:
            driver.get(url)
            time.sleep(2)
            annonces = driver.find_elements(By.CSS_SELECTOR, 'div.ad-specification')
            if len(annonces) == 0:
                status_text.text(f"Page {page} vide — arrêt.")
                break
            for annonce in annonces:
                try:
                    titre_brut = annonce.find_element(By.CSS_SELECTOR, 'h4').text.strip()
                    mots = titre_brut.split()
                    annee = int(mots[0]) if mots and mots[0].isdigit() and len(mots[0]) == 4 else None
                    marque = mots[1] if len(mots) > 1 else 'N/A'
                    modele = ' '.join(mots[2:]) if len(mots) > 2 else 'N/A'
                    try:
                        region = annonce.find_element(By.CSS_SELECTOR, 'div.location').text.strip()
                        region = re.sub(r'\s+', ' ', region).strip()
                    except: region = 'N/A'
                    try:
                        prix_brut = annonce.find_element(By.CSS_SELECTOR, 'span.price').text
                        prix = int(re.sub(r'[^0-9]', '', prix_brut))
                    except: prix = None
                    try:
                        km_brut = annonce.find_element(By.CSS_SELECTOR, 'div.ad-vehicle-mileage div.value').text
                        km = int(re.sub(r'[^0-9]', '', km_brut))
                    except: km = None
                    try:
                        boite = annonce.find_element(By.CSS_SELECTOR, 'div.transmission span:last-child').text.strip()
                    except: boite = 'N/A'
                    rows.append((marque, modele, annee, prix, km, boite, region))
                except: nb_erreurs += 1
        except Exception as e:
            status_text.text(f"Erreur page {page} : {e}")
        progress_bar.progress(int(page / nb_pages * 95))
        if page % 10 == 0:
            status_text.text(f"Page {page}/{nb_pages} — {len(rows)} annonces collectées")

    driver.quit()
    insert_voitures(rows)
    progress_bar.progress(100)
    status_text.text(f"Terminé — {len(rows)} annonces insérées ({nb_erreurs} erreurs)")
    return len(rows), nb_erreurs

# ─────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────
init_db()

# ─────────────────────────────────────────────
# CSS — STYLE SOBRE ET PROFESSIONNEL
# ─────────────────────────────────────────────
st.markdown("""
<style>
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #0f1117;
        border-right: 1px solid #1e2130;
    }
    .sidebar-title {
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #6b7280;
        margin-bottom: 24px;
        padding-bottom: 12px;
        border-bottom: 1px solid #1e2130;
    }
    .sidebar-stat {
        font-size: 12px;
        color: #6b7280;
        margin-top: 4px;
    }
    .sidebar-stat span {
        color: #e5e7eb;
        font-weight: 600;
    }
    /* Titres de page */
    .page-header {
        margin-bottom: 8px;
    }
    .page-title {
        font-size: 22px;
        font-weight: 700;
        color: #f3f4f6;
        letter-spacing: -0.01em;
    }
    .page-sub {
        font-size: 13px;
        color: #6b7280;
        margin-top: 2px;
    }
    .divider {
        border: none;
        border-top: 1px solid #1e2130;
        margin: 20px 0;
    }
    /* Metric cards */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin: 20px 0;
    }
    .metric-card {
        background: #161b27;
        border: 1px solid #1e2130;
        border-radius: 6px;
        padding: 16px 20px;
    }
    .metric-label {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #6b7280;
        margin-bottom: 8px;
    }
    .metric-value {
        font-size: 28px;
        font-weight: 700;
        color: #f3f4f6;
        line-height: 1;
    }
    .metric-value.ok { color: #10b981; font-size: 14px; font-weight: 600; margin-top: 4px; }
    .metric-value.ko { color: #ef4444; font-size: 14px; font-weight: 600; margin-top: 4px; }
    /* Section title */
    .section-title {
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #6b7280;
        margin: 28px 0 12px 0;
    }
    /* Info table accueil */
    .info-row {
        display: flex;
        justify-content: space-between;
        padding: 10px 0;
        border-bottom: 1px solid #1e2130;
        font-size: 13px;
    }
    .info-label { color: #9ca3af; }
    .info-val { color: #e5e7eb; font-weight: 500; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# NAVIGATION
# ─────────────────────────────────────────────
st.sidebar.markdown('<div class="sidebar-title">Data Collection</div>', unsafe_allow_html=True)

PAGES = ["Accueil", "Scraping Live", "Telechargement CSV", "Dashboard", "Formulaires"]
page = st.sidebar.radio("", PAGES, label_visibility="collapsed")

st.sidebar.markdown("<hr style='border-color:#1e2130;margin:20px 0'>", unsafe_allow_html=True)
n_books = get_db_count('books')
n_voitures = get_db_count('voitures')
st.sidebar.markdown(f"""
<div class="sidebar-stat">Books en base &nbsp;<span>{n_books}</span></div>
<div class="sidebar-stat" style="margin-top:6px">Voitures en base &nbsp;<span>{n_voitures}</span></div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# PAGE 1 — ACCUEIL
# ─────────────────────────────────────────────
if page == "Accueil":
    st.markdown('''
    <div class="page-header">
        <div class="page-title">Projet Data Collection</div>
        <div class="page-sub">Master Intelligence Artificielle — DIT Dakar · Examen 2026</div>
    </div>
    ''', unsafe_allow_html=True)
    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    books_raw_ok = os.path.exists(CSV_BOOKS_RAW)
    gaaraas_raw_ok = os.path.exists(CSV_GAARAAS_RAW)

    st.markdown('''<div class="metric-grid">
        <div class="metric-card">
            <div class="metric-label">Books en base</div>
            <div class="metric-value">{}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Voitures en base</div>
            <div class="metric-value">{}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">CSV Books brut</div>
            <div class="metric-value {}">  {}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">CSV Gaaraas brut</div>
            <div class="metric-value {}">  {}</div>
        </div>
    </div>'''.format(
        n_books, n_voitures,
        "ok" if books_raw_ok else "ko", "Present" if books_raw_ok else "Absent",
        "ok" if gaaraas_raw_ok else "ko", "Present" if gaaraas_raw_ok else "Absent"
    ), unsafe_allow_html=True)

    st.markdown('''<div class="section-title">Sources de donnees</div>''', unsafe_allow_html=True)
    st.markdown('''
    <div class="info-row"><span class="info-label">Books to Scrape</span><span class="info-val">50 pages · 9 variables · Selenium</span></div>
    <div class="info-row"><span class="info-label">Gaaraas Dakar Auto</span><span class="info-val">100 pages · 7 variables · Selenium</span></div>
    <div class="info-row"><span class="info-label">Outil no-code</span><span class="info-val">Web Scraper (extension Chrome)</span></div>
    <div class="info-row"><span class="info-label">Stockage</span><span class="info-val">SQLite · 2 tables (books, voitures)</span></div>
    ''', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# PAGE 2 — SCRAPING LIVE
# ─────────────────────────────────────────────
elif page == "Scraping Live":
    st.markdown('''
    <div class="page-header">
        <div class="page-title">Scraping Live</div>
        <div class="page-sub">Collecte de donnees via Selenium — stockage automatique en SQLite</div>
    </div>
    ''', unsafe_allow_html=True)
    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    source = st.selectbox("Source", ["Books to Scrape", "Gaaraas"])

    if source == "Books to Scrape":
        nb_pages = st.slider("Nombre de pages", min_value=1, max_value=50, value=5)
        st.caption(f"{nb_pages} page(s) · environ {nb_pages * 20} livres")
        if st.button("Lancer le scraping"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            with st.spinner("Scraping en cours..."):
                n, err = scrape_books(nb_pages, progress_bar, status_text)
            st.success(f"{n} livres inseres en base ({err} erreurs).")
    else:
        nb_pages = st.slider("Nombre de pages", min_value=1, max_value=100, value=5)
        st.caption(f"{nb_pages} page(s) · environ {nb_pages * 15} annonces")
        if st.button("Lancer le scraping"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            with st.spinner("Scraping en cours..."):
                n, err = scrape_gaaraas(nb_pages, progress_bar, status_text)
            st.success(f"{n} annonces inserees en base ({err} erreurs).")

# ─────────────────────────────────────────────
# PAGE 3 — TELECHARGEMENT CSV
# ─────────────────────────────────────────────
elif page == "Telechargement CSV":
    st.markdown('''
    <div class="page-header">
        <div class="page-title">Donnees brutes</div>
        <div class="page-sub">Fichiers collectes via Web Scraper (extension Chrome) — non nettoyes</div>
    </div>
    ''', unsafe_allow_html=True)
    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="section-title">Books to Scrape</div>', unsafe_allow_html=True)
        if os.path.exists(CSV_BOOKS_RAW):
            with open(CSV_BOOKS_RAW, "rb") as f:
                st.download_button(
                    label="Telecharger le CSV",
                    data=f,
                    file_name=CSV_BOOKS_RAW,
                    mime="text/csv",
                    use_container_width=True
                )
            df_preview = pd.read_csv(CSV_BOOKS_RAW, nrows=5)
            st.dataframe(df_preview, use_container_width=True)
        else:
            st.warning(f"Fichier introuvable : {CSV_BOOKS_RAW}")

    with col2:
        st.markdown('<div class="section-title">Gaaraas</div>', unsafe_allow_html=True)
        if os.path.exists(CSV_GAARAAS_RAW):
            with open(CSV_GAARAAS_RAW, "rb") as f:
                st.download_button(
                    label="Telecharger le CSV",
                    data=f,
                    file_name=CSV_GAARAAS_RAW,
                    mime="text/csv",
                    use_container_width=True
                )
            df_preview = pd.read_csv(CSV_GAARAAS_RAW, nrows=5)
            st.dataframe(df_preview, use_container_width=True)
        else:
            st.warning(f"Fichier introuvable : {CSV_GAARAAS_RAW}")

# ─────────────────────────────────────────────
# PAGE 4 — DASHBOARD
# ─────────────────────────────────────────────
elif page == "Dashboard":
    import plotly.express as px

    st.markdown('''
    <div class="page-header">
        <div class="page-title">Dashboard</div>
        <div class="page-sub">Donnees nettoyees issues du scraping Selenium · stockees en SQLite</div>
    </div>
    ''', unsafe_allow_html=True)
    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["Books to Scrape", "Gaaraas"])

    with tab1:
        df_books = load_table('books')
        if df_books.empty:
            st.info("Aucune donnee en base. Lancez un scraping depuis la page Scraping Live.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Livres", len(df_books))
            col2.metric("Prix moyen", f"£{df_books['prix'].mean():.2f}")
            col3.metric("Note moyenne", f"{df_books['note'].mean():.1f} / 5")
            col4.metric("Categories", df_books['categorie'].nunique())

            st.markdown('<div class="section-title">Repartition par categorie</div>', unsafe_allow_html=True)
            cat_counts = df_books['categorie'].value_counts().head(10).reset_index()
            cat_counts.columns = ['Categorie', 'Nombre']
            fig1 = px.bar(cat_counts, x='Nombre', y='Categorie', orientation='h',
                         color_discrete_sequence=['#3b82f6'], height=320)
            fig1.update_layout(
                plot_bgcolor='#0f1117', paper_bgcolor='#0f1117',
                font_color='#9ca3af', margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(gridcolor='#1e2130', showgrid=True),
                yaxis=dict(gridcolor='rgba(0,0,0,0)', categoryorder='total ascending')
            )
            st.plotly_chart(fig1, use_container_width=True)

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown('<div class="section-title">Distribution des notes</div>', unsafe_allow_html=True)
                note_counts = df_books['note'].value_counts().sort_index().reset_index()
                note_counts.columns = ['Note', 'Nombre']
                note_counts['Note'] = note_counts['Note'].astype(str)
                fig2 = px.bar(note_counts, x='Note', y='Nombre',
                             color_discrete_sequence=['#6366f1'], height=260)
                fig2.update_layout(
                    plot_bgcolor='#0f1117', paper_bgcolor='#0f1117',
                    font_color='#9ca3af', margin=dict(l=0, r=0, t=10, b=0),
                    xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                    yaxis=dict(gridcolor='#1e2130')
                )
                st.plotly_chart(fig2, use_container_width=True)

            with col_b:
                st.markdown('<div class="section-title">Disponibilite</div>', unsafe_allow_html=True)
                dispo = df_books['disponibilite'].value_counts().reset_index()
                dispo.columns = ['Statut', 'Nombre']
                fig3 = px.pie(dispo, names='Statut', values='Nombre',
                             color_discrete_sequence=['#10b981', '#ef4444'], height=260,
                             hole=0.45)
                fig3.update_layout(
                    plot_bgcolor='#0f1117', paper_bgcolor='#0f1117',
                    font_color='#9ca3af', margin=dict(l=0, r=0, t=10, b=0),
                    legend=dict(bgcolor='rgba(0,0,0,0)')
                )
                st.plotly_chart(fig3, use_container_width=True)

            st.markdown('<div class="section-title">Apercu des donnees</div>', unsafe_allow_html=True)
            st.dataframe(df_books.head(50), use_container_width=True, hide_index=True)

    with tab2:
        df_voitures = load_table('voitures')
        if df_voitures.empty:
            st.info("Aucune donnee en base. Lancez un scraping depuis la page Scraping Live.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Annonces", len(df_voitures))
            col2.metric("Prix moyen (FCFA)", f"{df_voitures['prix'].mean():,.0f}")
            col3.metric("Km moyen", f"{df_voitures['kilometrage'].mean():,.0f}")
            col4.metric("Marques", df_voitures['marque'].nunique())

            st.markdown('<div class="section-title">Top 10 des marques</div>', unsafe_allow_html=True)
            marque_counts = df_voitures['marque'].value_counts().head(10).reset_index()
            marque_counts.columns = ['Marque', 'Nombre']
            fig4 = px.bar(marque_counts, x='Nombre', y='Marque', orientation='h',
                         color_discrete_sequence=['#3b82f6'], height=320)
            fig4.update_layout(
                plot_bgcolor='#0f1117', paper_bgcolor='#0f1117',
                font_color='#9ca3af', margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(gridcolor='#1e2130'),
                yaxis=dict(gridcolor='rgba(0,0,0,0)', categoryorder='total ascending')
            )
            st.plotly_chart(fig4, use_container_width=True)

            col_c, col_d = st.columns(2)
            with col_c:
                st.markdown('<div class="section-title">Boite de vitesses</div>', unsafe_allow_html=True)
                boite = df_voitures['boite_vitesses'].value_counts().reset_index()
                boite.columns = ['Type', 'Nombre']
                fig5 = px.pie(boite, names='Type', values='Nombre',
                             color_discrete_sequence=['#3b82f6', '#6366f1', '#8b5cf6'],
                             height=260, hole=0.45)
                fig5.update_layout(
                    plot_bgcolor='#0f1117', paper_bgcolor='#0f1117',
                    font_color='#9ca3af', margin=dict(l=0, r=0, t=10, b=0),
                    legend=dict(bgcolor='rgba(0,0,0,0)')
                )
                st.plotly_chart(fig5, use_container_width=True)

            with col_d:
                st.markdown('<div class="section-title">Repartition par region</div>', unsafe_allow_html=True)
                region = df_voitures['region'].value_counts().head(8).reset_index()
                region.columns = ['Region', 'Nombre']
                fig6 = px.bar(region, x='Region', y='Nombre',
                             color_discrete_sequence=['#6366f1'], height=260)
                fig6.update_layout(
                    plot_bgcolor='#0f1117', paper_bgcolor='#0f1117',
                    font_color='#9ca3af', margin=dict(l=0, r=0, t=10, b=0),
                    xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                    yaxis=dict(gridcolor='#1e2130')
                )
                st.plotly_chart(fig6, use_container_width=True)

            st.markdown('<div class="section-title">Distribution par annee</div>', unsafe_allow_html=True)
            annee = df_voitures['annee'].dropna().astype(int)
            fig7 = px.histogram(annee, nbins=20, color_discrete_sequence=['#3b82f6'], height=260)
            fig7.update_layout(
                plot_bgcolor='#0f1117', paper_bgcolor='#0f1117',
                font_color='#9ca3af', margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(gridcolor='rgba(0,0,0,0)'),
                yaxis=dict(gridcolor='#1e2130'),
                showlegend=False
            )
            st.plotly_chart(fig7, use_container_width=True)

            st.markdown('<div class="section-title">Apercu des donnees</div>', unsafe_allow_html=True)
            st.dataframe(df_voitures.head(50), use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────
# PAGE 5 — FORMULAIRES
# ─────────────────────────────────────────────
elif page == "Formulaires":
    st.markdown('''
    <div class="page-header">
        <div class="page-title">Formulaires d'evaluation</div>
        <div class="page-sub">Deux versions du formulaire — KoboToolbox et Google Forms</div>
    </div>
    ''', unsafe_allow_html=True)
    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="section-title">KoboToolbox</div>', unsafe_allow_html=True)
        st.caption("Formulaire d'evaluation heberge sur KoboToolbox.")
        st.link_button("Ouvrir le formulaire Kobo", KOBO_URL, use_container_width=True)

    with col2:
        st.markdown('<div class="section-title">Google Forms</div>', unsafe_allow_html=True)
        st.caption("Formulaire d'evaluation heberge sur Google Forms.")
        st.link_button("Ouvrir le formulaire Google Forms", GFORMS_URL, use_container_width=True)
