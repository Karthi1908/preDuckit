import os
import requests
import json
from datetime import datetime, timezone

API_KEY = os.environ['FOOTBALL_DATA_API_KEY']
API_URL = "https://api.football-data.org/v4/competitions/PL/matches"

def lambda_handler(event, context):
    # The agent might ask for matches based on status ('SCHEDULED', 'FINISHED')
    api_path = event['apiPath']
    params = {p['name']: p['value'] for p in event.get('parameters', [])}
    status_filter = params.get('status', 'SCHEDULED')
    
    headers = {'X-Auth-Token': API_KEY}
    response = requests.get(API_URL, headers=headers, params={'status': status_filter})
    
    matches = response.json().get('matches', [])
    
    # Simple formatting for the agent to easily understand
    formatted_matches = [
        {
            "matchId": m['id'],
            "homeTeam": m['homeTeam']['name'],
            "awayTeam": m['awayTeam']['name'],
            "startTimeUTC": m['utcDate'],
            "status": m['status'],
            "winner": m['score']['winner'] if m.get('score') else None
        } for m in matches
    ]
    
    # Build and return the standard agent response structure
    return {
        'actionGroup': 'YourActionGroup',
        'apiPath': api_path,
        'httpMethod': 'GET',
        'httpStatusCode': 200,
        'responseBody': {
            'application/json': {
                'body': json.dumps(formatted_matches)
            }
        }
    }