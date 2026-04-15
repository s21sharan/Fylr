from langchain.agents import create_react_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.llms import Ollama
from langchain.chat_models import ChatOpenAI
from openai import OpenAI
import json
import re
import os
from dotenv import load_dotenv

class FileOrganizationAgent:
    def __init__(self, client=None, online_mode=False):
        self.client = client
        self.online_mode = online_mode
        load_dotenv()
        
        # Initialize the appropriate LLM based on mode
        if online_mode:
            # Use OpenAI in online mode
            openai_api_key = os.getenv('OPENAI_API_KEY')
            if not openai_api_key:
                raise ValueError("OPENAI_API_KEY environment variable is required for online mode")
            
            # Initialize both the LangChain and direct OpenAI clients
            self.llm = ChatOpenAI(temperature=0, model_name="gpt-4-turbo-preview", openai_api_key=openai_api_key)
            self.openai_client = OpenAI(api_key=openai_api_key)
            print("Using OpenAI for chat agent in online mode")
        else:
            # Use local Ollama model in offline mode
            self.llm = Ollama(base_url="http://localhost:11434", model="mistral")
            self.openai_client = None
            print("Using local Ollama model for chat agent in offline mode")
            
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            input_key="instruction",
            return_messages=True
        )
        
        self.prompt_template = PromptTemplate(
            input_variables=["file_structure", "instruction", "chat_history"],
            template="""
        You are an AI assistant specialized in organizing files. You're helping a user 
        modify their file organization structure according to their preferences.

        Current file structure:
        {file_structure}

        User instruction: {instruction}

        Previous conversation:
        {chat_history}

        ---

        Task:
        Carefully read the user's instruction and apply it to the current file structure.

        Always respond in the following format:

        1. A friendly explanation of what you did (1–2 sentences).
        2. The updated file structure in valid **JSON** format (matching the input structure style, no markdown).

        ---

        💡 Important rules:
        - Do **not** give terminal commands or CLI steps.
        - Do **not** summarize file contents.
        - Do **not** respond in markdown or code blocks.
        - If no changes are needed, return the original structure and explain why.
        - Ensure the JSON is **valid and parsable** — it will be used by a program.
        """
        )
        
        self.chain = LLMChain(
            llm=self.llm,
            prompt=self.prompt_template,
            memory=self.memory
        )
    
    def process_query(self, message, current_file_structure):
        """Process a user query and return response with optional updated file structure"""
        # Convert the file structure to a pretty string representation for the prompt
        file_structure_str = json.dumps(current_file_structure, indent=2)
        
        print("[DEBUG] User instruction:", message)
        print("[DEBUG] Current file structure length:", len(file_structure_str))
        print(f"[DEBUG] Using {'OpenAI' if self.online_mode else 'Local LLM'} for chat assistant")

        # Process differently based on mode
        if self.online_mode and self.openai_client:
            # Direct OpenAI API call for better token tracking
            try:
                prompt = self.prompt_template.format(
                    file_structure=file_structure_str,
                    instruction=message,
                    chat_history=str(self.memory.chat_memory.messages)
                )
                
                response_obj = self.openai_client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    response_format={"type": "json_object"}
                )
                
                # Track token usage
                if hasattr(response_obj, 'usage') and response_obj.usage:
                    token_usage = response_obj.usage.total_tokens
                    print(f"TOKEN_USAGE:{token_usage}")
                
                # Get response text
                response = response_obj.choices[0].message.content
                
                # Update memory manually
                self.memory.chat_memory.add_user_message(message)
                self.memory.chat_memory.add_ai_message(response)
                
            except Exception as e:
                print(f"Error calling OpenAI API directly: {str(e)}")
                # Fall back to LangChain
                response = self.chain.run(
                    file_structure=file_structure_str,
                    instruction=message
                )
        else:
            # Use LangChain with Ollama for offline mode
            response = self.chain.run(
                file_structure=file_structure_str,
                instruction=message
            )
        
        print("[DEBUG] LLM response:", response)
        
        # Check if the response contains a new file structure (in JSON format)
        try:
            # Extract JSON structure if it exists in the response
            new_structure = self.extract_json_from_response(response)
            
            if new_structure:
                # Split response into text and JSON parts
                text_parts = response.split('{')
                text_response = text_parts[0].strip()
                
                return {
                    "message": text_response,
                    "updatedFileStructure": new_structure
                }
            else:
                return {
                    "message": response,
                    "updatedFileStructure": None
                }
        except Exception as e:
            print(f"Error processing query: {str(e)}")
            return {
                "message": response,
                "updatedFileStructure": None
            }
    
    def extract_json_from_response(self, response: str):
        """Extract JSON structure from the response if present"""
        # 1. Try direct parse first
        try:
            return json.loads(response.strip())
        except:
            pass
        # 2. Strip markdown code fences
        stripped = re.sub(r'```(?:json)?\s*', '', response).strip().rstrip('`').strip()
        try:
            return json.loads(stripped)
        except:
            pass
        # 3. Find the outermost JSON object using a proper scan
        depth = 0
        start = None
        for i, ch in enumerate(response):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        return json.loads(response[start:i+1])
                    except:
                        start = None  # keep scanning
        return None