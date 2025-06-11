import time


class Fireworks_Api:
    def __init__(self, llm_client, model_id):
        self.client = llm_client
        self.model_id = model_id

    def ask_llm(self, prompt: str) -> str:
        """General-purpose method to query the LLM."""
        try:
            response = self.client.chat.completions.create(model=self.model_id, messages=[{"role": "user", "content": prompt}])
            time.sleep(2)
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"An error occurred while calling the LLM API: {e}")
            return ""