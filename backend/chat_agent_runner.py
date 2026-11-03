# backend/chat_agent_runner.py
import json
import sys
from chat_agent import FileOrganizationAgent
from dotenv import load_dotenv
import os

def main():
    # Load environment variables
    load_dotenv()
    
    # Read the input config file (passed as the first argument)
    with open(sys.argv[1], 'r') as f:
        config = json.load(f)

    message = config['message']
    file_structure = config['currentFileStructure']
    
    online_mode = config.get('online_mode', False)
    provider_name = config.get('provider')
    print(f"Chat agent running in {'ONLINE' if online_mode else 'OFFLINE'} mode, provider: {provider_name or 'auto'}")

    agent = FileOrganizationAgent(client=None, online_mode=online_mode, provider_name=provider_name)
    result = agent.process_query(message, file_structure)

    # Output result in one JSON line
    print(json.dumps(result))

if __name__ == '__main__':
    main()