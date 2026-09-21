import asyncio
from google import genai
import tts

API_KEY = "VOTRE_CLE_API_GEMINI_ICI"
client = genai.Client(api_key=API_KEY)

async def gemini_llm_stream(prompt):
    """
    Interroge Gemini via la nouvelle API de Chat (Interactions API) recommandée,
    et découpe les paquets en mots pour assurer la fluidité du TTS.
    """
    chat = client.aio.chats.create(model='gemini-3.6-flash')
    response = await chat.send_message_stream(prompt)
    
    async for chunk in response:
        if chunk.text:
            # On découpe le bloc envoyé par Gemini en mots individuels
            mots = chunk.text.split()
            
            for mot in mots:
                # On rajoute l'espace manquant et on l'envoie au lecteur TTS
                yield mot + " "
                
                # Un micro-délai optionnel permet un affichage textuel beaucoup plus fluide 
                # et laisse le temps au regex de EdgeTTS de détecter les points.
                await asyncio.sleep(0.01)

async def main():
    if API_KEY == "VOTRE_CLE_API_GEMINI_ICI":
        print("ATTENTION : Vous devez insérer votre clé API Gemini dans le script.")
        return

    prompt = """
    Tu es une personne d'église, plus particulièrement un prêtre, tu as été reçu l'appel intérieur à l'âge de 17 ans, puis a 19 ans tu as commencé l'année de propédeutique dans le couvent Saint Basile, tu es par la suite allé au diocèse de Saint-Étienne pour te former, tu a fais les deux cycle et assisté au ministères institués en 11 ans. Finalement tu as été ordonné prêtre à la cathédrale Notre-Dame-de-la-Major à Marseille et opère maintenant en tant que prêtre de la paroisse Saint Thomas-de-Doué depuis 13 ans.
    Tu as fais énormément de présentation au près de différents institut (prison, école catholique, rencontre publique, séminaire, centre de réhabilitation, lieux d'aide social et humanitaire, orphelinas) pour prêché la parole du seigneur et plus particulièrement le mode de vie frugaliste mis en lien avec le voeux de pauvreté que tu as fais (le fais de se reconnecter aux autres sans le biais de l'argent et de la dépense de celle-ci, s'échapper du système capitaliste actuelle et le replacer par un style de vie moins consumériste).
    """
    print(f"Utilisateur: {prompt}\n")
    
    # On crée le flux Gemini
    stream = gemini_llm_stream(prompt)

    # On passe ce flux à votre script tts.py
    await tts.llm_stream_to_speech(stream, "fr-CA-AntoineNeural")

if __name__ == "__main__":
    asyncio.run(main())