"""Pre-defined emergency call scenarios used in Demo Mode.

Each scenario contains a multi-turn script (caller lines only — the dispatcher's
responses are what we want our AI to help produce). The script is pre-synthesized
to an MP3 by `generate_demos.py` using edge-tts.

During demo playback, the server streams the audio through the SAME Whisper +
Claude pipeline a live mic would hit — so what the judges see is a faithful
end-to-end run, not a scripted fake.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Scenario:
    id: str
    title: str
    description: str
    category: str  # "medical", "fire", "police", "traffic", "multilingual"
    language: str  # BCP-47
    voice: str  # edge-tts voice id
    script: str  # full monologue with natural pauses (comma, period, ellipsis)
    difficulty: str = "medium"  # "easy", "medium", "hard"
    # Speech delivery — tuned per scenario. Faster + higher pitch = distress.
    rate: str = "+30%"
    pitch: str = "+4Hz"
    volume: str = "+0%"


SCENARIOS: list[Scenario] = [
    Scenario(
        id="cardiac-medical-01",
        title="Cardiac arrest — husband collapsed",
        description="Caller's husband collapsed with chest pain, not breathing normally.",
        category="medical",
        language="en-US",
        voice="en-US-JennyNeural",
        difficulty="medium",
        rate="+42%",
        pitch="+10Hz",
        script=(
            "Oh my god, oh my god, please help me! "
            "It's my husband, he just collapsed in the kitchen, he's — he's clutching his chest, "
            "he's barely breathing! His name is Robert Chen, he's sixty-two, he has a heart condition. "
            "Please, please, send someone now! "
            "We're at four-two-one Maple Street, apartment three B, near Oak Avenue. "
            "My phone is five-five-five, zero one nine two. He's not responding to me! "
            "What do I do, oh god, what do I do?"
        ),
    ),
    Scenario(
        id="fire-structure-01",
        title="House fire — possible person trapped",
        description="Neighbor reporting a house fire, unsure if elderly occupant is home.",
        category="fire",
        language="en-US",
        voice="en-US-GuyNeural",
        difficulty="medium",
        rate="+32%",
        pitch="+6Hz",
        script=(
            "I need to report a fire, right now! My neighbor's house is on fire, "
            "there's flames coming out of the upstairs windows and a ton of black smoke. "
            "The address is eighteen-fifty-seven Pine Ridge Road — it's the two-story yellow house on the corner. "
            "I think Mrs. Patterson might still be inside, she's about eighty years old, she doesn't move fast, "
            "I don't see her anywhere! I can hear cracking, like the roof! "
            "My name is David Kim, I'm at eighteen-fifty-five. "
            "Please hurry, it's spreading fast!"
        ),
    ),
    Scenario(
        id="police-domestic-01",
        title="Domestic disturbance — weapon mentioned",
        description="Caller whispering, partner has a knife, children in the house.",
        category="police",
        language="en-US",
        voice="en-US-AriaNeural",
        difficulty="hard",
        rate="+8%",
        pitch="-4Hz",
        volume="-40%",
        script=(
            "I'm whispering, I'm whispering, he's gonna hear me. "
            "My boyfriend is drunk, he's been screaming and throwing things for an hour. "
            "He grabbed a kitchen knife about a minute ago. "
            "I'm locked in the bathroom with my two kids, they're four and seven. "
            "We're at thirty-three Cedar Lane, the blue house. "
            "His name is Michael Torres, he's about six foot, red t-shirt and jeans. "
            "I don't know if he hurt anyone. Please come quick — but please, no sirens near the house!"
        ),
    ),
    Scenario(
        id="traffic-mva-01",
        title="Motor vehicle accident with injuries",
        description="Caller witnessed a multi-car crash on the highway, multiple injuries.",
        category="traffic",
        language="en-US",
        voice="en-US-ChristopherNeural",
        difficulty="easy",
        rate="+28%",
        pitch="+4Hz",
        script=(
            "There's been a bad accident on Interstate ninety-five northbound, "
            "about mile marker forty-seven, just past the Bedford exit. "
            "Three cars — one of them is flipped on its roof. "
            "I can see at least two people that are hurt, and one of them is not moving at all. "
            "There's broken glass everywhere and I can smell gasoline really strong. "
            "No fire yet but I'm worried. I've pulled over on the shoulder. "
            "I'm Sarah Williams, calling from five-five-five, four-four-eight-nine."
        ),
    ),
    Scenario(
        id="multilingual-spanish-01",
        title="Spanish-speaking caller — allergic reaction",
        description="Spanish-speaking mother, child having an allergic reaction, can't breathe properly.",
        category="multilingual",
        language="es-US",
        voice="es-US-PalomaNeural",
        difficulty="hard",
        rate="+36%",
        pitch="+10Hz",
        script=(
            "¡Por favor, necesito ayuda, mi hija no puede respirar bien! "
            "Comió algo con cacahuates y ahora tiene la cara muy hinchada, muy hinchada. "
            "Ella tiene cinco años, cinco años. "
            "Estamos en el setecientos veintitrés de la calle Laurel, apartamento dos. "
            "Mi nombre es María Hernández. Mi número es cinco, cinco, cinco, ocho, uno, dos, tres. "
            "¡Ella está muy asustada, por favor manden una ambulancia rápido, rápido!"
        ),
    ),
    Scenario(
        id="medical-overdose-01",
        title="Opioid overdose — roommate unresponsive",
        description="College student, roommate took pills, blue lips, not waking up.",
        category="medical",
        language="en-US",
        voice="en-US-AnaNeural",
        difficulty="medium",
        rate="+30%",
        pitch="+8Hz",
        script=(
            "My roommate won't wake up, I can't wake him up! "
            "I think he took too many pills. His lips look blue, "
            "and his breathing is really slow, like gasping. "
            "I shook him and he's not responding. "
            "We're in Branson Hall, room two-fourteen, State University, twelve hundred University Drive. "
            "His name is Tyler, he's nineteen. "
            "There's a bottle on the floor but I can't read it, I don't know what he took! "
            "My name is Jordan. Please, tell me what to do!"
        ),
    ),
]


def get_scenario(scenario_id: str) -> Scenario | None:
    return next((s for s in SCENARIOS if s.id == scenario_id), None)


def scenarios_summary() -> list[dict]:
    return [
        {
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "category": s.category,
            "language": s.language,
            "difficulty": s.difficulty,
        }
        for s in SCENARIOS
    ]
