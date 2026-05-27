import os
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
ESPN_ATP_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard"
ESPN_WTA_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard"

# ID des ligues TheSportsDB
LEAGUE_ATP = 4464
LEAGUE_WTA = 4517

SPORTSDB_PHPSESSID = os.getenv('SPORTSDB_SESSION')


def get_espn_matches():
    """Étape 1: Récupère les matchs planifiés depuis l'API ESPN."""
    matches = []
    headers = {'User-Agent': 'Mozilla/5.0'}

    for url in [ESPN_ATP_URL, ESPN_WTA_URL]:
        try:
            response = requests.get(url, headers=headers)
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

                # ESPN groupe par Simple Messieurs, Simple Dames, Doubles...
                for grouping in event.get('groupings', []):

                    # --- CORRECTION DU BUG ATP/WTA ---
                    grouping_info = grouping.get('grouping', {})
                    grouping_slug = grouping_info.get('slug', '').lower()

                    if 'women' in grouping_slug:
                        league_id = LEAGUE_WTA
                    elif 'men' in grouping_slug:
                        league_id = LEAGUE_ATP
                    else:
                        # On ignore les doubles mixtes ou autres formats non identifiés
                        continue

                    # On boucle sur chaque match de ce groupe
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

    # Pour éviter les doublons liés au fait qu'on appelle les deux URL ESPN qui peuvent
    # renvoyer le même tournoi du Grand Chelem deux fois
    unique_matches = {f"{m['player1']}-{m['player2']}-{m['date']}": m for m in matches}
    return list(unique_matches.values())


def check_sportsdb_exists(date_yyyy_mm_dd, tournament, player1, player2):
    """Étape 2: Vérifie la présence du match sur TheSportsDB en gérant la troncature à 40 caractères."""
    url = f"https://www.thesportsdb.com/browse_calendar/?d={date_yyyy_mm_dd}&s=tennis"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text().lower()

        # Stratégie 1 : Recherche de la chaîne exacte tronquée à 40 caractères
        event_name = f"{tournament} {player1} vs {player2}"
        expected_string = event_name[:40].lower()

        if expected_string in page_text:
            return True

        # Stratégie 2 : Fallback (Nom entier pour P1, 4 premières lettres pour P2)
        # On sécurise avec un if au cas où le joueur n'a qu'un seul mot comme nom
        p1_parts = player1.split()
        p2_parts = player2.split()

        p1_lastname = p1_parts[-1].lower() if p1_parts else ""
        p2_lastname_short = p2_parts[-1][:4].lower() if p2_parts else ""

        if p1_lastname and p2_lastname_short:
            if p1_lastname in page_text and p2_lastname_short in page_text:
                return True

        return False

    except Exception as e:
        print(f"Erreur scraping TheSportsDB pour le {date_yyyy_mm_dd}: {e}")
        return False


def push_to_php_endpoint(match_data):
    """Étape 3: Pousse les données vers le backend PHP de TheSportsDB."""
    league_id = match_data['league_id']
    url = f"https://www.thesportsdb.com/edit_event_add_process.php?l={league_id}"

    # Formatage de la date et de l'heure pour les champs du formulaire
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

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Cookie': f'PHPSESSID={SPORTSDB_PHPSESSID}',
        'Referer': f'https://www.thesportsdb.com/edit_event_add.php?l={league_id}'
    }

    try:
        response = requests.post(url, data=payload, headers=headers)
        response.raise_for_status()
        print(f"   -> 🚀 POST réussi pour : {event_name}")
    except Exception as e:
        print(f"   -> ❌ Erreur POST pour {event_name} : {e}")


def main():
    print("Démarrage du job horaire de synchronisation ATP/WTA...")

    matches = get_espn_matches()
    print(f"🎾 {len(matches)} matchs récupérés sur ESPN (après dédoublonnage).")

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
            push_to_php_endpoint(match)

        time.sleep(1.5)

    print("Job terminé.")


if __name__ == "__main__":
    main()
