from langchain_ollama import ChatOllama


def get_ollama():
    return ChatOllama(
        model="gemma3:4b",
        temperature=0,
    )
