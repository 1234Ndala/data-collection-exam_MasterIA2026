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

KOBO_URL = "https://kobo.lien-fictif.com/formulaire"       # À remplacer
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
# NAVIGATION
# ─────────────────────────────────────────────
st.sidebar.title("📊 Data Collection")
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigation",
    ["🏠 Accueil", "🔍 Scraping Live", "⬇️ Téléchargement CSV", "📈 Dashboard", "📋 Formulaires"]
)
st.sidebar.markdown("---")
st.sidebar.markdown(f"**Books en BDD :** {get_db_count('books')} lignes")
st.sidebar.markdown(f"**Voitures en BDD :** {get_db_count('voitures')} lignes")

# ─────────────────────────────────────────────
# PAGE 1 — ACCUEIL
# ─────────────────────────────────────────────
if page == "🏠 Accueil":
    st.title("📊 Projet Data Collection — Examen")
    st.markdown("### Web scraping, nettoyage de données et visualisation")
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Books en BDD", get_db_count('books'))
    with col2:
        st.metric("Voitures en BDD", get_db_count('voitures'))
    with col3:
        books_raw_ok = os.path.exists(CSV_BOOKS_RAW)
        st.metric("CSV Books brut", "✅ Présent" if books_raw_ok else "❌ Absent")
    with col4:
        gaaraas_raw_ok = os.path.exists(CSV_GAARAAS_RAW)
        st.metric("CSV Gaaraas brut", "✅ Présent" if gaaraas_raw_ok else "❌ Absent")
    st.markdown("---")
    st.markdown("""
    **Sources de données :**
    - 📚 [Books to Scrape](https://books.toscrape.com) — 50 pages, 9 variables
    - 🚗 [Gaaraas Dakar Auto](https://www.gaaraas.com/fr/users/dakar-auto) — 100 pages, 7 variables

    **Fonctionnalités :**
    - 🔍 Scraping live via Selenium (choix du nombre de pages)
    - ⬇️ Téléchargement des données brutes (Web Scraper no-code)
    - 📈 Dashboard de visualisation des données nettoyées
    - 📋 Accès aux formulaires d'évaluation (Kobo + Google Forms)
    """)

# ─────────────────────────────────────────────
# PAGE 2 — SCRAPING LIVE
# ─────────────────────────────────────────────
elif page == "🔍 Scraping Live":
    st.title("🔍 Scraping Live")
    st.markdown("Lance un scraping Selenium directement depuis l'application.")
    st.markdown("---")

    source = st.selectbox("Source à scraper", ["Books to Scrape", "Gaaraas"])

    if source == "Books to Scrape":
        nb_pages = st.slider("Nombre de pages à scraper", min_value=1, max_value=50, value=5)
        st.info(f"Environ {nb_pages * 20} livres seront collectés ({nb_pages} pages × 20 livres/page).")
        if st.button("▶️ Lancer le scraping Books"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            with st.spinner("Scraping en cours..."):
                n, err = scrape_books(nb_pages, progress_bar, status_text)
            st.success(f"{n} livres insérés en base de données ({err} erreurs).")
    else:
        nb_pages = st.slider("Nombre de pages à scraper", min_value=1, max_value=100, value=5)
        st.info(f"Environ {nb_pages * 15} annonces seront collectées.")
        if st.button("▶️ Lancer le scraping Gaaraas"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            with st.spinner("Scraping en cours..."):
                n, err = scrape_gaaraas(nb_pages, progress_bar, status_text)
            st.success(f"{n} annonces insérées en base de données ({err} erreurs).")

# ─────────────────────────────────────────────
# PAGE 3 — TÉLÉCHARGEMENT CSV BRUTS
# ─────────────────────────────────────────────
elif page == "⬇️ Téléchargement CSV":
    st.title("⬇️ Téléchargement des données brutes")
    st.markdown("Données collectées via **Web Scraper** (extension Chrome) — non nettoyées.")
    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📚 Books to Scrape")
        if os.path.exists(CSV_BOOKS_RAW):
            with open(CSV_BOOKS_RAW, "rb") as f:
                st.download_button(
                    label="⬇️ Télécharger books-toscrape (brut)",
                    data=f,
                    file_name=CSV_BOOKS_RAW,
                    mime="text/csv"
                )
            df_preview = pd.read_csv(CSV_BOOKS_RAW, nrows=5)
            st.dataframe(df_preview, use_container_width=True)
        else:
            st.warning(f"Fichier `{CSV_BOOKS_RAW}` introuvable. Placez-le à la racine du projet.")

    with col2:
        st.subheader("🚗 Gaaraas")
        if os.path.exists(CSV_GAARAAS_RAW):
            with open(CSV_GAARAAS_RAW, "rb") as f:
                st.download_button(
                    label="⬇️ Télécharger gaaraas (brut)",
                    data=f,
                    file_name=CSV_GAARAAS_RAW,
                    mime="text/csv"
                )
            df_preview = pd.read_csv(CSV_GAARAAS_RAW, nrows=5)
            st.dataframe(df_preview, use_container_width=True)
        else:
            st.warning(f"Fichier `{CSV_GAARAAS_RAW}` introuvable. Placez-le à la racine du projet.")

# ─────────────────────────────────────────────
# PAGE 4 — DASHBOARD
# ─────────────────────────────────────────────
elif page == "📈 Dashboard":
    st.title("📈 Dashboard — Données nettoyées")
    st.markdown("Données issues du scraping **Selenium**, stockées en SQLite.")
    st.markdown("---")

    tab1, tab2 = st.tabs(["📚 Books to Scrape", "🚗 Gaaraas"])

    with tab1:
        df_books = load_table('books')
        if df_books.empty:
            st.warning("Aucune donnée Books en base. Lancez d'abord un scraping.")
        else:
            st.markdown(f"**{len(df_books)} livres en base de données**")
            col1, col2, col3 = st.columns(3)
            col1.metric("Prix moyen", f"£{df_books['prix'].mean():.2f}")
            col2.metric("Note moyenne", f"{df_books['note'].mean():.1f} / 5")
            col3.metric("Catégories", df_books['categorie'].nunique())

            st.markdown("#### Répartition par catégorie (Top 10)")
            cat_counts = df_books['categorie'].value_counts().head(10)
            st.bar_chart(cat_counts)

            st.markdown("#### Distribution des notes")
            note_counts = df_books['note'].value_counts().sort_index()
            st.bar_chart(note_counts)

            st.markdown("#### Distribution des prix")
            st.bar_chart(df_books['prix'].dropna().value_counts().sort_index())

            st.markdown("#### Disponibilité")
            dispo_counts = df_books['disponibilite'].value_counts()
            st.bar_chart(dispo_counts)

            st.markdown("#### Aperçu des données")
            st.dataframe(df_books.head(50), use_container_width=True)

    with tab2:
        df_voitures = load_table('voitures')
        if df_voitures.empty:
            st.warning("Aucune donnée Gaaraas en base. Lancez d'abord un scraping.")
        else:
            st.markdown(f"**{len(df_voitures)} annonces en base de données**")
            col1, col2, col3 = st.columns(3)
            col1.metric("Prix moyen (FCFA)", f"{df_voitures['prix'].mean():,.0f}")
            col2.metric("Km moyen", f"{df_voitures['kilometrage'].mean():,.0f}")
            col3.metric("Marques", df_voitures['marque'].nunique())

            st.markdown("#### Top 10 des marques")
            marque_counts = df_voitures['marque'].value_counts().head(10)
            st.bar_chart(marque_counts)

            st.markdown("#### Répartition par région")
            region_counts = df_voitures['region'].value_counts().head(10)
            st.bar_chart(region_counts)

            st.markdown("#### Boîte de vitesses")
            boite_counts = df_voitures['boite_vitesses'].value_counts()
            st.bar_chart(boite_counts)

            st.markdown("#### Distribution par année")
            annee_counts = df_voitures['annee'].dropna().astype(int).value_counts().sort_index()
            st.bar_chart(annee_counts)

            st.markdown("#### Aperçu des données")
            st.dataframe(df_voitures.head(50), use_container_width=True)

# ─────────────────────────────────────────────
# PAGE 5 — FORMULAIRES
# ─────────────────────────────────────────────
elif page == "📋 Formulaires":
    st.title("📋 Formulaires d'évaluation")
    st.markdown("Deux versions du formulaire d'évaluation de l'application.")
    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🟠 KoboToolbox")
        st.markdown("Formulaire d'évaluation hébergé sur KoboToolbox.")
        st.link_button("Ouvrir le formulaire Kobo", KOBO_URL, use_container_width=True)

    with col2:
        st.subheader("🔵 Google Forms")
        st.markdown("Formulaire d'évaluation hébergé sur Google Forms.")
        st.link_button("Ouvrir le formulaire Google Forms", GFORMS_URL, use_container_width=True)
