import os
import json
from web3 import Web3

# These would be loaded from Environment Variables
RPC_URL = os.environ['RPC_URL']
CONTRACT_ADDRESS = os.environ['PREDICTION_MARKET_CONTRACT_ADDRESS']
CONTRACT_ABI = json.loads(os.environ['PREDICTION_MARKET_CONTRACT_ABI'])
# The name of the secret in AWS Secrets Manager
SECRET_NAME = os.environ['SECRET_NAME'] 

# Initialize Web3 and contract outside the handler for reuse
w3 = Web3(Web3.HTTPProvider(RPC_URL))
contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)

# Function to get the private key securely from Secrets Manager
def get_oracle_key():
    # In a real implementation, use boto3 to get the secret
    # For this example, we assume it's fetched and returned
    # client = boto3.client('secretsmanager')
    # response = client.get_secret_value(SecretId=SECRET_NAME)
    # return json.loads(response['SecretString'])['oracle_private_key']
    return os.environ['ORACLE_PRIVATE_KEY'] # For simpler local testing

def lambda_handler(event, context):
    """
    Invokes a function on the smart contract.
    This is a privileged, backend-only function.
    """
    api_path = event['apiPath']
    params = {p['name']: p['value'] for p in event.get('parameters', [])}

    # Extract function name and arguments from the agent's request
    function_to_call = params.get('functionName')
    function_args = json.loads(params.get('arguments', '[]')) # Arguments as a JSON string array

    if not function_to_call:
        return build_response("Function name not specified.", 400)

    try:
        private_key = get_oracle_key()
        oracle_account = w3.eth.account.from_key(private_key)
        nonce = w3.eth.get_transaction_count(oracle_account.address)

        # Dynamically get the function from the contract object
        contract_function = getattr(contract.functions, function_to_call)
        
        # Build the transaction
        tx = contract_function(*function_args).build_transaction({
            'chainId': 11155111,  # Sepolia Testnet
            'from': oracle_account.address,
            'gas': 500000,
            'gasPrice': w3.to_wei('50', 'gwei'),
            'nonce': nonce
        })

        signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        return build_response({'status': 'SUCCESS', 'tx_hash': w3.to_hex(tx_hash)})

    except Exception as e:
        print(f"Error: {str(e)}")
        return build_response({'status': 'ERROR', 'message': str(e)}, 500)

def build_response(body, status_code=200):
    # Helper to format the response for the Bedrock Agent
    return {
        'actionGroup': 'YourActionGroup',
        'apiPath': '/yourApiPath',
        'httpMethod': 'POST',
        'httpStatusCode': status_code,
        'responseBody': {
            'application/json': {
                'body': json.dumps(body)
            }
        }
    }