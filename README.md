# Projet Data Collection — Examen

Web scraping, nettoyage de données et déploiement d'une application Streamlit.

## Sources de données
- **Books to Scrape** : https://books.toscrape.com (50 pages, 9 variables)
- **Gaaraas Dakar Auto** : https://www.gaaraas.com/fr/users/dakar-auto (100 pages, 7 variables)

## Structure du projet
```
├── app.py                              # Application Streamlit principale
├── requirements.txt                    # Dépendances Python
├── data_collection.db                  # Base SQLite (générée au runtime)
├── books-toscrape-com-2026-08-06-3.csv # Données brutes Books (Web Scraper)
├── gaaraas-com-2026-08-07.csv          # Données brutes Gaaraas (Web Scraper)
└── README.md
```

## Fonctionnalités de l'application
1. **Scraping Live** — Selenium intégré, choix du nombre de pages
2. **Téléchargement CSV** — Données brutes issues du Web Scraper (non nettoyées)
3. **Dashboard** — Visualisation des données nettoyées depuis SQLite
4. **Formulaires** — Liens vers les formulaires Kobo et Google Forms

## Installation locale
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Déploiement Streamlit Cloud
1. Pusher le repo sur GitHub
2. Aller sur https://share.streamlit.io
3. Connecter le repo et sélectionner `app.py`
4. Déployer

## Auteur
William Marrion Branham NDALA — Master Intelligence Artificielle, DIT Dakar
