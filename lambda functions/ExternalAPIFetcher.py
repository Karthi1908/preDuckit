import json
import requests
from datetime import datetime, timedelta
import time

API_TOKEN = "your_api_key_here"  # Replace with your actual API key
COMPETITION_ID = 'PL'  # English Premier League
BASE_URL = "https://api.football-data.org/v4"

def get_team_id(team_name):
    """Fetch team ID by name from competition teams list."""
    url = f"{BASE_URL}/competitions/{COMPETITION_ID}/teams"
    headers = {"X-Auth-Token": API_TOKEN}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch teams: {response.text}")
    
    teams = response.json().get('teams', [])
    for team in teams:
        if team['name'].lower() == team_name.lower():
            return team['id']
    
    raise ValueError(f"Team '{team_name}' not found in EPL.")

def lambda_handler(event, context):
    try:
        # Extract and validate parameters
        status = event.get('status', 'SCHEDULED')
        if status not in ['SCHEDULED', 'FINISHED']:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid status. Must be SCHEDULED or FINISHED'})
            }
        
        # Compute default dates based on status
        current_date = datetime.utcnow()
        if status == 'SCHEDULED':
            # Default to 5 days from now
            target_date = (current_date + timedelta(days=5)).strftime('%Y-%m-%d')
            date_from = event.get('date_from', target_date)
            date_to = event.get('date_to', target_date)
        else:  # FINISHED
            # Default to last 7 days for completed matches
            date_to = event.get('date_to', current_date.strftime('%Y-%m-%d'))
            date_from = event.get('date_from', (current_date - timedelta(days=7)).strftime('%Y-%m-%d'))
        
        # Validate date format
        try:
            datetime.strptime(date_from, '%Y-%m-%d')
            datetime.strptime(date_to, '%Y-%m-%d')
        except ValueError:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid date format. Use YYYY-MM-DD'})
            }
        
        # Handle empty input
        if not event:
            return {
                'statusCode': 200,
                'body': json.dumps({'matches': []})
            }
        
        # Determine endpoint based on team parameter
        team = event.get('team')
        if team:
            # Assume team is name (string), fetch ID
            try:
                team_id = get_team_id(team)
                url = f"{BASE_URL}/teams/{team_id}/matches"
            except ValueError as ve:
                return {
                    'statusCode': 404,
                    'body': json.dumps({'error': str(ve)})
                }
            except Exception as e:
                return {
                    'statusCode': 500,
                    'body': json.dumps({'error': f'Failed to fetch team ID: {str(e)}'})
                }
        else:
            url = f"{BASE_URL}/competitions/{COMPETITION_ID}/matches"
        
        params = {'status': status, 'dateFrom': date_from, 'dateTo': date_to}
        headers = {"X-Auth-Token": API_TOKEN}
        
        # Handle API rate limits with retries
        for attempt in range(3):
            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            if response.status_code != 200:
                return {
                    'statusCode': response.status_code,
                    'body': json.dumps({'error': f'API request failed: {response.text}'})
                }
            break
        else:
            return {
                'statusCode': 429,
                'body': json.dumps({'error': 'API rate limit exceeded after retries'})
            }
        
        # Format matches
        matches = response.json().get('matches', [])
        formatted_matches = []
        for match in matches:
            match_data = {
                'match_date': match['utcDate'],
                'venue': match.get('venue', 'Unknown'),
                'home_team': match['homeTeam']['name'],
                'away_team': match['awayTeam']['name']
            }
            if match['status'] == 'FINISHED':
                # Add score
                match_data['score'] = {
                    'home': match['score']['fullTime']['home'],
                    'away': match['score']['fullTime']['away']
                }
                # Determine winner
                winner_code = match['score']['winner']
                if winner_code == 'HOME_TEAM':
                    match_data['winner'] = match['homeTeam']['name']
                elif winner_code == 'AWAY_TEAM':
                    match_data['winner'] = match['awayTeam']['name']
                elif winner_code == 'DRAW':
                    match_data['winner'] = 'draw'
                else:
                    match_data['winner'] = 'unknown'
            formatted_matches.append(match_data)
        
        return {
            'statusCode': 200,
            'body': json.dumps({'matches': formatted_matches})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal server error: {str(e)}'})
        }
