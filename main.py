import os
import time
from datetime import datetime

import requests
import unicodedata
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
ESPN_ATP_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard"
ESPN_WTA_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard"

# ID des ligues TheSportsDB
LEAGUE_ATP = 4464
LEAGUE_WTA = 4517

# Initialisation de la session HTTP globale pour TheSportsDB
sportsdb_session = requests.Session()


def authenticate_session():
    """
    Crée une session HTTP, s'authentifie sur TheSportsDB et retourne le statut.
    """
    # 1. Configuration des headers globaux
    sportsdb_session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
    })

    login_url = "https://www.thesportsdb.com/user_login.php"

    # 2. Premier GET pour initialiser le cookie côté serveur
    try:
        sportsdb_session.get(login_url, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"[ERREUR] Impossible de joindre TheSportsDB : {e}")
        return False

    # 3. Récupération des identifiants (Local: .env / Prod: GitHub Secrets)
    username = os.environ.get('SPORTSDB_USERNAME')
    password = os.environ.get('SPORTSDB_PASSWORD')

    if not username or not password:
        print("[ERREUR] Identifiants manquants dans les variables d'environnement.")
        return False

    payload = {
        'username': username,
        'password': password
    }

    post_headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://www.thesportsdb.com',
        'Referer': login_url
    }

    print("[INFO] Tentative de connexion à TheSportsDB...")

    # 4. Envoi du POST d'authentification
    try:
        response = sportsdb_session.post(login_url, data=payload, headers=post_headers, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"[ERREUR] Échec de la requête de connexion : {e}")
        return False

    # 5. Vérification de la réussite
    if 'docs_pricing.php' in response.url or 'user' in sportsdb_session.cookies.get_dict() or 'PHPSESSID' in sportsdb_session.cookies.get_dict():
        print("[INFO] ✅ Connexion réussie. Session active.")
        return True
    else:
        print("[WARN] ❌ Échec de la connexion. Vérifiez les identifiants.")
        return False


def get_espn_matches():
    """Étape 1: Récupère les matchs planifiés depuis l'API ESPN."""
    matches = []
    # On utilise requests classique ici (pas la session) pour ne pas envoyer
    # nos cookies TheSportsDB aux serveurs d'ESPN (bonne pratique de sécurité).
    headers = {'User-Agent': 'Mozilla/5.0'}

    for url in [ESPN_ATP_URL, ESPN_WTA_URL]:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            for event in data.get('events', []):
                tournament_name = event.get('name', 'Tournoi Inconnu')
                season = event.get('season', {}).get('year', datetime.now().year)

                venue_display = event.get('venue', {}).get('displayName', '')
                country = venue_display.split(',')[-1].strip() if ',' in venue_display else venue_display
                city = venue_display.split(',')[0].strip() if ',' in venue_display else venue_display
                if not country: country = 'Unknown'
                if not city: city = 'Unknown'

                for grouping in event.get('groupings', []):
                    grouping_info = grouping.get('grouping', {})
                    grouping_slug = grouping_info.get('slug', '').lower()

                    if 'women' in grouping_slug:
                        league_id = LEAGUE_WTA
                    elif 'men' in grouping_slug:
                        league_id = LEAGUE_ATP
                    else:
                        continue

                    for competition in grouping.get('competitions', []):
                        date_str = competition.get('date', event.get('date'))
                        competitors = competition.get('competitors', [])

                        if len(competitors) == 2:
                            p1 = competitors[0].get('athlete', {}).get('displayName', 'Inconnu')
                            p2 = competitors[1].get('athlete', {}).get('displayName', 'Inconnu')

                            if p1 in {'TBD', 'Inconnu'} or p2 in {'TBD', 'Inconnu'}:
                                continue

                            matches.append({
                                'season': season,
                                'country': country,
                                'city': city,
                                'tournament': tournament_name,
                                'player1': p1,
                                'player2': p2,
                                'date': date_str,
                                'league_id': league_id
                            })
        except Exception as e:
            print(f"Erreur lors de l'appel ESPN ({url}): {e}")

    unique_matches = {f"{m['player1']}-{m['player2']}-{m['date']}": m for m in matches}
    return list(unique_matches.values())


def sanitize_text(text):
    """
    Supprime les accents, passe en minuscules et ignore les caractères corrompus.
    """
    if not text:
        return ""
    # NFKD sépare la lettre de son accent
    text = unicodedata.normalize('NFKD', text)
    # On force l'encodage ASCII. 'ignore' supprime automatiquement les accents isolés et les
    text = text.encode('ASCII', 'ignore')
    return text.decode('utf-8').lower().replace('-', ' ').replace("'", '')


def check_sportsdb_exists(date_yyyy_mm_dd, tournament, player1, player2):
    """Étape 2: Vérifie la présence du match sur TheSportsDB via la session authentifiée."""
    url = f"https://www.thesportsdb.com/browse_calendar/?d={date_yyyy_mm_dd}&s=tennis"

    try:
        response = sportsdb_session.get(url, timeout=10)
        # On force la lecture en UTF-8 (bonne pratique en web scraping)
        response.encoding = 'utf-8'
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # On passe tout le HTML à la moulinette anti-accents
        page_text = sanitize_text(soup.get_text())

        # Création de la chaîne recherchée
        event_name = f"{tournament} {player1} vs {player2}"
        expected_string = sanitize_text(event_name)

        # L'astuce : On coupe à 35 caractères au lieu de 40.
        # Cela garantit qu'on ne cherche jamais la lettre qui a été tronquée/corrompue à la fin,
        # tout en restant assez long pour identifier un match unique avec 100% de certitude.
        expected_string_safe = expected_string[:35]

        if expected_string_safe in page_text:
            return True

        # Stratégie 2 : Fallback (Nom entier pour P1, 4 premières lettres pour P2)
        p1_parts = player1.split()
        p2_parts = player2.split()

        p1_lastname = sanitize_text(p1_parts[-1]) if p1_parts else ""
        p2_lastname_short = sanitize_text(p2_parts[-1])[:4] if p2_parts else ""

        if p1_lastname and p2_lastname_short:
            if p1_lastname in page_text and p2_lastname_short in page_text:
                return True

        return False

    except Exception as e:
        print(f"Erreur scraping TheSportsDB pour le {date_yyyy_mm_dd}: {e}")
        return False


def push_to_php_endpoint(match_data):
    """Étape 3: Pousse les données vers TheSportsDB avec la session."""
    league_id = match_data['league_id']
    url = f"https://www.thesportsdb.com/edit_event_add_process.php?l={league_id}"

    try:
        match_dt = datetime.strptime(match_data['date'], "%Y-%m-%dT%H:%MZ")
        datepicker = match_dt.strftime("%Y-%m-%d")
        starttime = match_dt.strftime("%H:%M")
    except ValueError:
        datepicker = ""
        starttime = ""

    event_name = f"{match_data['tournament']} {match_data['player1']} vs {match_data['player2']}"

    payload = {
        'datepicker': datepicker,
        'starttime': starttime,
        'season': match_data['season'],
        'round': '',
        'eventcountry': match_data['country'],
        'eventcity': match_data['city'],
        'eventname': event_name,
        'submit': 'Submit'
    }

    # On ajoute uniquement les headers requis pour tromper le système anti-bot PHP
    # Le Content-Type et les Cookies sont gérés par la Session
    headers = {
        'Referer': f'https://www.thesportsdb.com/edit_event_add.php?l={league_id}',
        'Origin': 'https://www.thesportsdb.com'
    }

    try:
        response = sportsdb_session.post(url, data=payload, headers=headers, timeout=10)
        response.raise_for_status()
        print(f"   -> 🚀 POST réussi pour : {event_name}")
    except Exception as e:
        print(f"   -> ❌ Erreur POST pour {event_name} : {e}")


def main():
    print("=== Démarrage du job horaire de synchronisation ATP/WTA ===")

    # Étape 0 : Authentification
    if not authenticate_session():
        print("[CRITIQUE] Arrêt du script suite à l'échec d'authentification.")
        return

    # Étape 1 : Récupération ESPN
    matches = get_espn_matches()
    print(f"🎾 {len(matches)} matchs récupérés sur ESPN (après dédoublonnage).")

    # Étape 2 & 3 : Vérification et Insertion
    for match in matches:
        try:
            match_date_obj = datetime.strptime(match['date'], "%Y-%m-%dT%H:%MZ")
            date_str = match_date_obj.strftime("%Y-%m-%d")
        except ValueError:
            continue

        circuit = "ATP" if match['league_id'] == LEAGUE_ATP else "WTA"
        print(f"Analyse [{circuit}]: {match['player1']} vs {match['player2']} à {match['tournament']} le {date_str}")

        if check_sportsdb_exists(date_str, match['tournament'], match['player1'], match['player2']):
            print(f"   -> 🛑 Match déjà existant sur TheSportsDB. Ignoré.")
        else:
            print(f"   -> ✅ Match inédit. Envoi de la requête...")
            # push_to_php_endpoint(match)

        time.sleep(1.5)

    print("=== Job terminé ===")


if __name__ == "__main__":
    main()
