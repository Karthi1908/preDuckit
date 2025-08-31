import boto3
import json

# Bedrock Agent Runtime client
bedrock_agent_client = boto3.client('bedrock-agent-runtime')
AGENT_ID = "YOUR_AGENT_ID"
AGENT_ALIAS_ID = "YOUR_AGENT_ALIAS_ID" # e.g., 'TSTALIASID'

def lambda_handler(event, context):
    # This Lambda's only job is to give the agent a command.
    response = bedrock_agent_client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId="daily-market-creation-task", # A consistent session ID for recurring tasks
        inputText="run daily market creation" # The command that triggers the logic in the agent's prompt
    )
    print("Agent invoked for market creation.")
    return {'statusCode': 200}