import base64
import sys
import os

# Lazy-initialized client
_client = None

def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        _client = OpenAI(api_key=api_key)
    return _client


IMAGE_ANALYSIS_TOOL = {
    "type": "function",
    "name": "image_analysis",
    "description": "Analyze an image and return structured metadata for file naming.",
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "What type of image is this? Examples: photo, screenshot, diagram, receipt, document, meme, artwork, chart, map",
            },
            "subject": {
                "type": "string",
                "description": "1-3 word specific subject of the image. What is the main thing in it? Examples: golden_retriever, circuit_board, tax_form, sunset_beach",
            },
            "summary": {
                "type": "string",
                "description": "One sentence description of the image content, 5-15 words.",
            },
        },
        "required": ["category", "subject", "summary"],
    },
}


def analyze_image_with_openai(image_path):
    """Analyze image using OpenAI Vision API -- returns structured description."""
    try:
        client = _get_client()
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')

        response = client.responses.create(
            model="gpt-4o-mini",
            tools=[IMAGE_ANALYSIS_TOOL],
            tool_choice={"type": "function", "name": "image_analysis"},
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Analyze this image and describe what it contains."},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": "low"
                    },
                ],
            }],
        )

        import json
        # Extract tool call result from responses API
        for block in response.output:
            if block.type == "function_call":
                result = json.loads(block.arguments)
                return f"{result['category']} of {result['subject']}: {result['summary']}"

        return None
    except Exception as e:
        print(f"Error analyzing image with OpenAI Vision: {str(e)}")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_openai_vision.py <path_to_image>")
        sys.exit(1)
        
    image_path = sys.argv[1]
    if not os.path.exists(image_path):
        print(f"Error: Image file not found at {image_path}")
        sys.exit(1)
        
    summary = analyze_image_with_openai(image_path)
    print("\nReturned Summary:")
    print(summary) 