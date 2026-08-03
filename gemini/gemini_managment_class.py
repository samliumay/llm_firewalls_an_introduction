import os
from google import genai
from pathlib import Path
from dotenv import load_dotenv

class gemini_managment_object:
    def __init__(self): 
        project_root=Path(__file__).resolve().parents[1]

        load_dotenv(project_root / ".env")

        self.client = genai.Client()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")

        if not self.gemini_api_key:
            raise RuntimeError("Gemini_API_KEY is missing from .env")
        

    def one_iteration_text_generation(self, prompt: str): 

        if not prompt:
            raise RuntimeError("Enter what you want from the model")

        response = self.client.interactions.create(
            model="gemini-3.1-flash-lite",
            input=prompt
        )

        print(response.output_text)

        
        
