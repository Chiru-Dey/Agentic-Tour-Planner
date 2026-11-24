"""LLM-as-judge for DeepEval, backed by Groq (no OpenAI key needed).
Uses a DIFFERENT model than the agent (llama-3.3-70b vs deepseek-r1-distill-70b)
to reduce self-preference bias."""
import os, re
from deepeval.models.base_model import DeepEvalBaseLLM
from langchain_groq import ChatGroq

class GroqJudge(DeepEvalBaseLLM):
    def __init__(self, model: str = "llama-3.3-70b-versatile", temperature: float = 0.0):
        self._name = model
        self.client = ChatGroq(model=model, temperature=temperature, api_key=os.getenv("GROQ_API_KEY"))
        super().__init__(model)

    def load_model(self):
        return self.client

    def _coerce(self, text: str, schema):
        if schema is None:
            return text
        try:
            return schema.model_validate_json(text)
        except Exception:
            m = re.search(r"\{.*\}", text, re.S)   # strip prose / code fences around JSON
            if m:
                return schema.model_validate_json(m.group(0))
            raise

    def generate(self, prompt: str, schema=None):
        text = self.client.invoke(prompt).content
        if schema is None:
            return text
        for _ in range(2):
            try:
                return self._coerce(text, schema)
            except Exception as e:
                text = self.client.invoke(
                    prompt + f"\n\nReturn ONLY valid JSON matching the schema. Previous error: {e}").content
        return self._coerce(text, schema)

    async def a_generate(self, prompt: str, schema=None):
        text = (await self.client.ainvoke(prompt)).content
        if schema is None:
            return text
        for _ in range(2):
            try:
                return self._coerce(text, schema)
            except Exception as e:
                text = (await self.client.ainvoke(
                    prompt + f"\n\nReturn ONLY valid JSON matching the schema. Previous error: {e}")).content
        return self._coerce(text, schema)

    def get_model_name(self):
        return f"groq/{self._name}"