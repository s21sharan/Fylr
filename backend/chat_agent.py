import json
import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm import get_provider


SYSTEM_PROMPT = """
You are an AI assistant specialized in organizing files. You're helping a user
modify their file organization structure according to their preferences.

Always respond in the following format:

1. A friendly explanation of what you did (1-2 sentences).
2. The updated file structure in valid **JSON** format (matching the input structure style, no markdown).

---

Important rules:
- Do **not** give terminal commands or CLI steps.
- Do **not** summarize file contents.
- Do **not** respond in markdown or code blocks.
- If no changes are needed, return the original structure and explain why.
- Ensure the JSON is **valid and parsable** -- it will be used by a program.
""".strip()


class FileOrganizationAgent:
    def __init__(self, client=None, online_mode=False):
        self.online_mode = online_mode
        self.provider = get_provider(online_mode)
        self.conversation_history = []
        print(f"Using {self.provider.name} for chat agent in {'online' if online_mode else 'offline'} mode")

    def process_query(self, message, current_file_structure):
        """Process a user query and return response with optional updated file structure"""
        file_structure_str = json.dumps(current_file_structure, indent=2)

        print("[DEBUG] User instruction:", message)
        print("[DEBUG] Current file structure length:", len(file_structure_str))
        print(f"[DEBUG] Using {self.provider.name} for chat assistant")

        # Build messages for the provider
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        # Add conversation history
        messages.extend(self.conversation_history)

        # Add the current user message with file structure context
        user_content = (
            f"Current file structure:\n{file_structure_str}\n\n"
            f"User instruction: {message}"
        )
        messages.append({"role": "user", "content": user_content})

        try:
            llm_response = self.provider.chat(
                messages,
                temperature=0,
                max_tokens=2048,
                response_format={"type": "json_object"} if self.online_mode else None,
            )

            response = llm_response.content

            # Track token usage
            if llm_response.tokens_used:
                print(f"TOKEN_USAGE:{llm_response.tokens_used}")

            # Update conversation history
            self.conversation_history.append({"role": "user", "content": user_content})
            self.conversation_history.append({"role": "assistant", "content": response})

        except Exception as e:
            print(f"Error calling LLM: {str(e)}")
            return {
                "message": f"Error: {str(e)}",
                "updatedFileStructure": None,
            }

        print("[DEBUG] LLM response:", response)

        # Check if the response contains a new file structure (in JSON format)
        try:
            new_structure = self.extract_json_from_response(response)

            if new_structure:
                # Split response into text and JSON parts
                text_parts = response.split('{')
                text_response = text_parts[0].strip()

                return {
                    "message": text_response,
                    "updatedFileStructure": new_structure,
                }
            else:
                return {
                    "message": response,
                    "updatedFileStructure": None,
                }
        except Exception as e:
            print(f"Error processing query: {str(e)}")
            return {
                "message": response,
                "updatedFileStructure": None,
            }

    def extract_json_from_response(self, response: str):
        """Extract JSON structure from the response if present"""
        # 1. Try direct parse first
        try:
            return json.loads(response.strip())
        except Exception:
            pass
        # 2. Strip markdown code fences
        stripped = re.sub(r'```(?:json)?\s*', '', response).strip().rstrip('`').strip()
        try:
            return json.loads(stripped)
        except Exception:
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
                    except Exception:
                        start = None  # keep scanning
        return None
