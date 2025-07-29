import os
import time
import sys
# from fireworks.client import Fireworks
from dotenv import load_dotenv
import google.generativeai as genai

# API_KEY = os.environ.get("FIREWORKS_API_KEY")
# API_MODEL = os.environ.get("FIREWORKS_MODEL")
# fw = Fireworks(api_key=API_KEY)  # Fixed variable name (was api_key)
# model_id = API_MODEL

def reparar_texto(texto_danado: str) -> str:
    """
    Attempt to fix a string that was incorrectly decoded as latin-1
    when it was actually utf-8.
    """
    try:
        return texto_danado.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto_danado  # Return original if repair fails


class Fireworks_Api:
    def __init__(self, llm_client, model_id):

        self.client = llm_client
        self.model_id = model_id

    def ask_llm(self, prompt: str) -> str:
        """General-purpose method to query the LLM."""
        try:
            response = self.client.chat.completions.create(model=self.model_id, messages=[{"role": "user", "content": prompt}])
            time.sleep(5)
            llm_response = response.choices[0].message.content.strip()
            if llm_response:
                llm_response = reparar_texto(llm_response)
            return llm_response
        except Exception as e:
            print(f"An error occurred while calling the LLM API: {e}")
            return ""
        
class Gemini_Api:
    def __init__(self, model_name):
        load_dotenv()
        api_key = os.environ.get("GENAI_API_KEY")
        if not api_key:
            raise ValueError("GENAI_API_KEY no encontrada")
        genai.configure(api_key=api_key)

        self.model = genai.GenerativeModel(model_name)


    def ask_llm(self, prompt: str) -> str:
        """General-purpose method to query the LLM."""
        try:
            print("Trying prompt")
            print(prompt)
            response = self.model.generate_content(prompt)
            time.sleep(2)
            
            if response:
                print(response.text)
                llm_response = response.text.strip()
                with open("LLM_response.tex", "w", encoding="utf-8") as f:
                    f.write(llm_response)
                with open("LLM_response.tex", 'r', encoding='utf-8') as file:
                    fixed_response = file.read().strip()
                
                # llm_response = reparar_texto(llm_response)
            return fixed_response
        except Exception as e:
            print(f"An error occurred while calling the LLM API: {e}")
            return ""