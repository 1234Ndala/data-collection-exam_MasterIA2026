"""
Application Streamlit — Projet Data Collection
Sources : Books to Scrape + Gaaraas (annonces auto Dakar)
"""

import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import time
import re
import os

# ─────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Data Collection — Exam",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────────────────────
# NAVIGATION SIDEBAR
# ─────────────────────────────────────────────────────────────────
st.sidebar.title("📊 Navigation")
page = st.sidebar.radio(
    "Aller à :",
    [
        "🏠 Accueil",
        "🔍 Scraping Live",
        "📥 Données brutes (Web Scraper)",
        "📚 Dashboard Books to Scrape",
        "🚗 Dashboard Gaaraas",
        "📋 Formulaires d'évaluation"
    ]
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Projet d'examen — Data Collection**")
st.sidebar.markdown("Web scraping · Nettoyage · Streamlit")

# ─────────────────────────────────────────────────────────────────
# FONCTIONS UTILITAIRES
# ─────────────────────────────────────────────────────────────────

def charger_books():
    """Charger les données books depuis CSV ou BDD"""
    if os.path.exists("books_cleaned.csv"):
        return pd.read_csv("books_cleaned.csv")
    elif os.path.exists("books_scrape.db"):
        conn = sqlite3.connect("books_scrape.db")
        df = pd.read_sql_query("SELECT * FROM books", conn)
        conn.close()
        return df
    return pd.DataFrame()

def charger_gaaraas():
    """Charger les données gaaraas depuis CSV ou BDD"""
    if os.path.exists("gaaraas_cleaned.csv"):
        return pd.read_csv("gaaraas_cleaned.csv")
    elif os.path.exists("gaaraas.db"):
        conn = sqlite3.connect("gaaraas.db")
        df = pd.read_sql_query("SELECT * FROM voitures", conn)
        conn.close()
        return df
    return pd.DataFrame()

# ─────────────────────────────────────────────────────────────────
# PAGE : ACCUEIL
# ─────────────────────────────────────────────────────────────────
if page == "🏠 Accueil":
    st.title("📊 Projet Data Collection — Examen")
    st.markdown("""
    Cette application permet de :
    - **Scraper** des données en live via Selenium
    - **Télécharger** les données brutes issues du scraping no-code (Web Scraper)
    - **Visualiser** les données nettoyées sous forme de dashboards
    - **Accéder** aux formulaires d'évaluation (Kobo et Google Forms)
    """)

    col1, col2 = st.columns(2)
    with col1:
        st.info("**Source 1 — Books to Scrape**\n\nhttps://books.toscrape.com\n\n50 pages · 9 variables")
    with col2:
        st.info("**Source 2 — Gaaraas**\n\nhttps://www.gaaraas.com\n\n100 pages · 7 variables")

    st.markdown("---")
    df_books = charger_books()
    df_gaaraas = charger_gaaraas()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📚 Livres collectés", len(df_books) if not df_books.empty else "—")
    c2.metric("🚗 Annonces collectées", len(df_gaaraas) if not df_gaaraas.empty else "—")
    c3.metric("📄 Pages Books", "50")
    c4.metric("📄 Pages Gaaraas", "100")

# ─────────────────────────────────────────────────────────────────
# PAGE : SCRAPING LIVE
# ─────────────────────────────────────────────────────────────────
elif page == "🔍 Scraping Live":
    st.title("🔍 Scraping Live")
    st.markdown("Lancer un scraping Selenium directement depuis l'application.")

    source = st.selectbox("Choisir la source :", ["Books to Scrape", "Gaaraas"])

    if source == "Books to Scrape":
        nb_pages = st.slider("Nombre de pages à scraper :", 1, 50, 5)
        st.caption("⏱️ Estimation : ~2 min pour 5 pages (une page détail par livre)")
    else:
        nb_pages = st.slider("Nombre de pages à scraper :", 1, 100, 10)
        st.caption("⏱️ Estimation : ~30 sec pour 10 pages")

    if st.button("🚀 Lancer le scraping", type="primary"):
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            import google_colab_selenium as gs

            st.info("Lancement du navigateur...")
            driver = gs.Chrome()
            results = []
            progress = st.progress(0)
            status = st.empty()

            if source == "Books to Scrape":
                # Collecter les URLs
                book_urls = []
                for page_num in range(1, nb_pages + 1):
                    url = f'https://books.toscrape.com/catalogue/page-{page_num}.html'
                    driver.get(url)
                    time.sleep(1)
                    livres = driver.find_elements(By.CSS_SELECTOR, 'article.product_pod h3 a')
                    book_urls.extend([l.get_attribute('href') for l in livres])
                    progress.progress(int((page_num / nb_pages) * 50))

                # Scraper les détails
                note_map = {'One': 1, 'Two': 2, 'Three': 3, 'Four': 4, 'Five': 5}
                for idx, url in enumerate(book_urls):
                    try:
                        driver.get(url)
                        time.sleep(0.5)
                        titre = driver.find_element(By.CSS_SELECTOR, 'div.product_main h1').text
                        prix_brut = driver.find_element(By.CSS_SELECTOR, 'p.price_color').text
                        prix = float(re.sub(r'[^0-9.]', '', prix_brut))
                        dispo = driver.find_element(By.CSS_SELECTOR, 'p.availability').text.strip()
                        note_cls = driver.find_element(By.CSS_SELECTOR, 'p.star-rating').get_attribute('class')
                        note = next((v for k, v in note_map.items() if k in note_cls), None)
                        breadcrumb = driver.find_elements(By.CSS_SELECTOR, 'ul.breadcrumb li')
                        categorie = breadcrumb[2].text.strip() if len(breadcrumb) >= 3 else 'N/A'
                        results.append({'titre': titre, 'prix': prix, 'disponibilite': dispo,
                                        'note': note, 'categorie': categorie})
                    except:
                        pass
                    progress.progress(50 + int((idx / len(book_urls)) * 50))
                    status.text(f"{idx + 1}/{len(book_urls)} livres traités")

            else:  # Gaaraas
                for page_num in range(1, nb_pages + 1):
                    url = f'https://www.gaaraas.com/fr/users/dakar-auto?page={page_num}'
                    driver.get(url)
                    time.sleep(2)
                    containers = driver.find_elements(By.CSS_SELECTOR,
                        'div.vehicle-card, article.listing, div[class*="car"]')
                    for container in containers:
                        try:
                            titre = container.find_element(By.CSS_SELECTOR, 'h2, h3, [class*="title"]').text
                            prix_brut = container.find_element(By.CSS_SELECTOR, '[class*="price"], [class*="prix"]').text
                            prix = int(re.sub(r'[^0-9]', '', prix_brut)) if prix_brut else None
                            mots = titre.split()
                            results.append({'marque': mots[0] if mots else 'N/A',
                                            'modele': ' '.join(mots[1:3]) if len(mots) > 1 else 'N/A',
                                            'prix': prix})
                        except:
                            pass
                    progress.progress(int((page_num / nb_pages) * 100))
                    status.text(f"Page {page_num}/{nb_pages}")

            driver.quit()
            df_live = pd.DataFrame(results)
            st.success(f"✅ {len(df_live)} enregistrements collectés !")
            st.dataframe(df_live, use_container_width=True)

            csv = df_live.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Télécharger les données", csv,
                               f"scraping_live_{source.lower().replace(' ', '_')}.csv",
                               "text/csv")

        except ImportError:
            st.error("⚠️ Selenium n'est pas disponible dans cet environnement. "
                     "Lancez les notebooks sur Google Colab.")

# ─────────────────────────────────────────────────────────────────
# PAGE : DONNÉES BRUTES WEB SCRAPER
# ─────────────────────────────────────────────────────────────────
elif page == "📥 Données brutes (Web Scraper)":
    st.title("📥 Données brutes — Web Scraper (no-code)")
    st.markdown("""
    Cette section permet de télécharger ou d'explorer les données brutes collectées via 
    l'extension Chrome **Web Scraper** (sans nettoyage).
    """)

    source_brute = st.radio("Source :", ["Books to Scrape", "Gaaraas"])
    uploaded = st.file_uploader(
        f"Importer le fichier CSV brut ({source_brute}) exporté depuis Web Scraper :",
        type=["csv"]
    )

    if uploaded is not None:
        df_brut = pd.read_csv(uploaded)
        st.success(f"✅ Fichier chargé : {df_brut.shape[0]} lignes · {df_brut.shape[1]} colonnes")
        st.dataframe(df_brut, use_container_width=True)

        st.markdown("### Aperçu des données brutes")
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Types de colonnes :**")
            st.write(df_brut.dtypes.astype(str))
        with col2:
            st.write("**Valeurs manquantes :**")
            st.write(df_brut.isnull().sum())

        csv_out = df_brut.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Télécharger les données brutes", csv_out,
                           f"brut_{source_brute.lower().replace(' ', '_')}.csv", "text/csv")
    else:
        st.info("👆 Importez votre fichier CSV exporté depuis l'extension Web Scraper.")

# ─────────────────────────────────────────────────────────────────
# PAGE : DASHBOARD BOOKS
# ─────────────────────────────────────────────────────────────────
elif page == "📚 Dashboard Books to Scrape":
    st.title("📚 Dashboard — Books to Scrape")

    df = charger_books()

    if df.empty:
        st.warning("⚠️ Aucune donnée disponible. Lancez d'abord le notebook de scraping.")
        st.stop()

    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total livres", len(df))
    col2.metric("Prix moyen (£)", f"{df['prix'].mean():.2f}" if 'prix' in df else "—")
    col3.metric("Note moyenne", f"{df['note'].mean():.1f}/5" if 'note' in df else "—")
    col4.metric("Catégories", df['categorie'].nunique() if 'categorie' in df else "—")

    st.markdown("---")

    # Filtres
    st.sidebar.markdown("### Filtres Books")
    if 'categorie' in df.columns:
        cats = ['Toutes'] + sorted(df['categorie'].dropna().unique().tolist())
        cat_sel = st.sidebar.selectbox("Catégorie :", cats)
        if cat_sel != 'Toutes':
            df = df[df['categorie'] == cat_sel]

    if 'prix' in df.columns:
        prix_min, prix_max = float(df['prix'].min()), float(df['prix'].max())
        prix_range = st.sidebar.slider("Plage de prix (£) :", prix_min, prix_max, (prix_min, prix_max))
        df = df[(df['prix'] >= prix_range[0]) & (df['prix'] <= prix_range[1])]

    # Graphiques
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Répartition des notes")
        if 'note' in df.columns:
            fig = px.histogram(df, x='note', nbins=5, color_discrete_sequence=['#3498db'],
                               labels={'note': 'Note (étoiles)', 'count': 'Nombre de livres'})
            fig.update_layout(bargap=0.1)
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Distribution des prix")
        if 'prix' in df.columns:
            fig = px.box(df, y='prix', color_discrete_sequence=['#e74c3c'],
                         labels={'prix': 'Prix (£)'})
            st.plotly_chart(fig, use_container_width=True)

    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("Top 10 catégories")
        if 'categorie' in df.columns:
            top_cats = df['categorie'].value_counts().head(10).reset_index()
            top_cats.columns = ['Catégorie', 'Nombre']
            fig = px.bar(top_cats, x='Nombre', y='Catégorie', orientation='h',
                         color_discrete_sequence=['#2ecc71'])
            fig.update_layout(yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig, use_container_width=True)

    with col_d:
        st.subheader("Prix moyen par catégorie (Top 10)")
        if 'prix' in df.columns and 'categorie' in df.columns:
            prix_cat = df.groupby('categorie')['prix'].mean().sort_values(ascending=False).head(10).reset_index()
            prix_cat.columns = ['Catégorie', 'Prix moyen (£)']
            fig = px.bar(prix_cat, x='Prix moyen (£)', y='Catégorie', orientation='h',
                         color_discrete_sequence=['#9b59b6'])
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Données complètes")
    st.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 Télécharger les données nettoyées", csv, "books_cleaned.csv", "text/csv")

# ─────────────────────────────────────────────────────────────────
# PAGE : DASHBOARD GAARAAS
# ─────────────────────────────────────────────────────────────────
elif page == "🚗 Dashboard Gaaraas":
    st.title("🚗 Dashboard — Gaaraas (Annonces auto Dakar)")

    df = charger_gaaraas()

    if df.empty:
        st.warning("⚠️ Aucune donnée disponible. Lancez d'abord le notebook de scraping.")
        st.stop()

    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total annonces", len(df))
    col2.metric("Prix moyen (FCFA)", f"{df['prix'].mean():,.0f}" if 'prix' in df else "—")
    col3.metric("Km moyen", f"{df['kilometrage'].mean():,.0f}" if 'kilometrage' in df else "—")
    col4.metric("Marques", df['marque'].nunique() if 'marque' in df else "—")

    st.markdown("---")

    # Filtres
    st.sidebar.markdown("### Filtres Gaaraas")
    if 'marque' in df.columns:
        marques = ['Toutes'] + sorted(df['marque'].dropna().unique().tolist())
        marque_sel = st.sidebar.selectbox("Marque :", marques)
        if marque_sel != 'Toutes':
            df = df[df['marque'] == marque_sel]

    if 'boite_vitesses' in df.columns:
        boites = ['Toutes'] + df['boite_vitesses'].dropna().unique().tolist()
        boite_sel = st.sidebar.selectbox("Boîte de vitesses :", boites)
        if boite_sel != 'Toutes':
            df = df[df['boite_vitesses'] == boite_sel]

    # Graphiques
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Top 10 marques les plus annoncées")
        if 'marque' in df.columns:
            top_marques = df['marque'].value_counts().head(10).reset_index()
            top_marques.columns = ['Marque', 'Nombre']
            fig = px.bar(top_marques, x='Nombre', y='Marque', orientation='h',
                         color_discrete_sequence=['#e67e22'])
            fig.update_layout(yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Répartition par boîte de vitesses")
        if 'boite_vitesses' in df.columns:
            boite_counts = df['boite_vitesses'].value_counts().reset_index()
            boite_counts.columns = ['Boîte', 'Nombre']
            fig = px.pie(boite_counts, values='Nombre', names='Boîte',
                         color_discrete_sequence=px.colors.qualitative.Set2)
            st.plotly_chart(fig, use_container_width=True)

    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("Distribution des prix")
        if 'prix' in df.columns:
            df_prix = df[df['prix'].notna() & (df['prix'] > 0)]
            fig = px.histogram(df_prix, x='prix', nbins=30,
                               color_discrete_sequence=['#1abc9c'],
                               labels={'prix': 'Prix (FCFA)'})
            st.plotly_chart(fig, use_container_width=True)

    with col_d:
        st.subheader("Année vs Prix")
        if 'annee' in df.columns and 'prix' in df.columns:
            df_scatter = df[df['annee'].notna() & df['prix'].notna()]
            fig = px.scatter(df_scatter, x='annee', y='prix',
                             color='marque' if 'marque' in df.columns else None,
                             labels={'annee': 'Année', 'prix': 'Prix (FCFA)'},
                             opacity=0.6)
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Données complètes")
    st.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 Télécharger les données nettoyées", csv, "gaaraas_cleaned.csv", "text/csv")

# ─────────────────────────────────────────────────────────────────
# PAGE : FORMULAIRES D'ÉVALUATION
# ─────────────────────────────────────────────────────────────────
elif page == "📋 Formulaires d'évaluation":
    st.title("📋 Formulaires d'évaluation")
    st.markdown("Évaluez l'application via l'un des deux formulaires ci-dessous.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📝 Formulaire KoboToolbox")
        st.markdown("""
        Collecte structurée via KoboToolbox.
        """)
        KOBO_URL = "https://ee.kobotoolbox.org/x/VOTRE_CLE_KOBO"  # À remplacer
        st.link_button("Ouvrir le formulaire Kobo", KOBO_URL, use_container_width=True)

    with col2:
        st.markdown("### 📝 Formulaire Google Forms")
        st.markdown("""
        Collecte structurée via Google Forms.
        """)
        GFORMS_URL = "https://forms.gle/VOTRE_CLE_GFORMS"  # À remplacer
        st.link_button("Ouvrir le formulaire Google", GFORMS_URL, use_container_width=True)

    st.markdown("---")
    st.info("💡 Remplacez les URLs ci-dessus par vos liens réels une fois vos formulaires créés.")
