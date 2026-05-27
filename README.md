# 🎾 TennisFetcher

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Serverless-2088FF.svg)
![Status](https://img.shields.io/badge/Status-Production-success.svg)

**TennisFetcher** est un pipeline d'acquisition et de synchronisation de données sportives. Il automatise la récupération des matchs de tennis (ATP et WTA) planifiés et leur insertion dans la base de données participative [TheSportsDB](https://www.thesportsdb.com/).

Conçu pour fonctionner de manière autonome en environnement *Serverless* via GitHub Actions, ce script élimine le besoin de saisie manuelle tout en intégrant des mécanismes avancés de déduplication.

## 🏗 Architecture du Pipeline

Le script s'exécute selon une architecture ETL (Extract, Transform, Load) simplifiée en 3 étapes :

1. **Extraction (API ESPN) :** Interrogation des flux JSON en temps réel pour récupérer les tableaux complets des tournois en cours. Le routage ATP/WTA est géré dynamiquement selon les catégories (Simple Messieurs, Simple Dames).
2. **Validation & Anti-Doublon (Web Scraping) :** Avant toute insertion, le script vérifie l'existence du match sur le calendrier TheSportsDB. Il intègre une logique *Fuzzy Search* pour contourner les limitations techniques du front-end (notamment la troncature des noms d'événements à 40 caractères).
3. **Insertion (POST Request) :** Simulation d'une soumission de formulaire côté serveur pour injecter le match directement dans la bonne ligue TheSportsDB en utilisant une session utilisateur authentifiée.

## 🚀 Fonctionnalités clés

* **Exécution Horaire :** Déclenchement automatique via un cron job GitHub Actions (`0 * * * *`).
* **Smart Routing :** Détection automatique de la ligue (ATP = 4464, WTA = 4517) même sur les tournois du Grand Chelem mixtes.
* **Fuzzy Matching :** Algorithme de comparaison souple basé sur les noms de famille pour éviter les faux doublons liés à la casse ou aux prénoms.
* **Rate Limiting :** Temporisation intégrée (`time.sleep`) pour respecter les serveurs cibles et éviter les blocages d'IP.

## ⚙️ Prérequis et Installation (Local)

Pour faire tourner ou tester le projet sur votre machine locale :

1. Clonez le dépôt :
```bash
   git clone [https://github.com/votre-nom/TennisFetcher.git](https://github.com/votre-nom/TennisFetcher.git)
   cd TennisFetcher