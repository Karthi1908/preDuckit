# Import necessary libraries
import json  # To handle JSON data from Telegram and API Gateway
import os    # To access environment variables for security
import requests # To send the final message back to the Telegram API
import boto3 # The AWS SDK for Python, used to interact with Bedrock

# Initialize the Boto3 client for the Bedrock Agent Runtime
# This is done outside the handler for better performance (reuse across invocations)
bedrock_agent_client = boto3.client('bedrock-agent-runtime')

# Get configuration from Lambda Environment Variables
# This is more secure and flexible than hardcoding values
AGENT_ID = os.environ['BEDROCK_AGENT_ID']
AGENT_ALIAS_ID = os.environ['BEDROCK_AGENT_ALIAS_ID']
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']

# Construct the URL for sending messages back to Telegram
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

def lambda_handler(event, context):
    """
    This function is triggered by API Gateway for every message from Telegram.
    """
    
    # 1. RECEIVE & PARSE THE MESSAGE
    # API Gateway wraps the original Telegram request. We need to parse the 'body'.
    try:
        body = json.loads(event.get('body', '{}'))
        message = body.get('message')
        
        if not message:
            # This could be a different type of update we don't handle, so we exit.
            return {'statusCode': 200, 'body': 'Not a message update'}
            
    except json.JSONDecodeError:
        print("ERROR: Could not parse event body.")
        return {'statusCode': 400, 'body': 'Invalid JSON'}

    # 2. EXTRACT KEY INFORMATION
    try:
        chat_id = message['chat']['id']        # ID of the chat to send the reply to
        user_id = message['from']['id']        # Unique ID for the user
        text_from_user = message.get('text', '') # The actual text the user sent
        
        if not text_from_user:
            # If the user sent a sticker, photo, etc., we ignore it.
            requests.post(TELEGRAM_API_URL, json={'chat_id': chat_id, 'text': "I can only understand text messages."})
            return {'statusCode': 200, 'body': 'Non-text message received'}

    except KeyError as e:
        print(f"ERROR: Missing expected key in Telegram message: {e}")
        return {'statusCode': 400, 'body': 'Malformed Telegram message'}

    # 3. INVOKE THE BEDROCK AGENT
    # This is where we hand off the user's query to our AI brain.
    # We use the user's unique ID as the session ID to maintain conversation history.
    try:
        response = bedrock_agent_client.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=str(user_id),  # Session ID must be a string
            inputText=text_from_user
        )
    except Exception as e:
        print(f"ERROR: Bedrock Agent invocation failed: {e}")
        # Send a generic error message to the user
        requests.post(TELEGRAM_API_URL, json={'chat_id': chat_id, 'text': "Sorry, I'm having trouble thinking right now. Please try again later."})
        return {'statusCode': 500, 'body': 'Agent invocation error'}

    # 4. PROCESS THE AGENT'S STREAMED RESPONSE
    agent_response_text = ""
    try:
        # The agent's response is a stream of events. We need to iterate through them
        # and piece together the final text from the 'chunk' parts.
        for event in response.get('completion', []):
            if 'chunk' in event:
                agent_response_text += event['chunk']['bytes'].decode('utf-8')
    except Exception as e:
        print(f"ERROR: Could not process agent's streamed response: {e}")
        return {'statusCode': 500, 'body': 'Agent response processing error'}
        
    # 5. REPLY TO THE USER
    # Send the final, assembled text from the agent back to the user in Telegram.
    if agent_response_text:
        payload = {
            'chat_id': chat_id,
            'text': agent_response_text,
            'parse_mode': 'Markdown' # Allows for bold, italics, etc. in the agent's response
        }
        requests.post(TELEGRAM_API_URL, json=payload)
    
    # Return a 200 OK status to Telegram to acknowledge receipt of the message.
    # This is important, otherwise Telegram will keep trying to resend the webhook.
    return {'statusCode': 200, 'body': 'Message processed successfully'}