import re
import sys
import spacy
import unicodedata

from utils import strip_accents

# Load Spanish model (or replace with "en_core_web_sm" for English)
nlp = spacy.load("es_core_news_sm")

def extract_ambiguous_ideas(text: str) -> list[dict]:
    pattern = re.compile(
        r"Idea:\s*\"?(.+?)\"?\s*"                          # quotes optional
        r"Ambigua/No ambigua:\s*(\w+)\s*"                  # accept any word
        r"Por qué:\s*(.+?)(?=\nIdea:|\Z)", 
        re.DOTALL
    )

    matches = pattern.findall(text)
    result = []
    for idea, status, reason in matches:
        if status and idea and reason and status.strip().lower() == "ambigua":
            result.append({
                "idea": idea.strip(),
                "reason": reason.strip()
            })
    return result

import re

def extract_sections_without_transition(text: str) -> dict[str, str]:
    result = {}

    # Permitir errores de codificación y variantes con o sin corchetes
    block_pattern = re.compile(
        r"(?:###\s*Secci[oó�]n\s*\d+\s*)?"  # encabezado tipo '### Sección 1'
        r"Nombre de secci[oó�]n:\s*(.+?)\s*"
        r"Transici[oó�]n:\s*(?:\[(Sí|No)\]|(Sí|No))\s*"
        r"Sugerencia para incluir transici[oó�]n:\s*(.+?)(?=\n(?:###|Nombre de secci[oó�]n:|\Z))",
        re.DOTALL | re.IGNORECASE
    )

    try:
        for match in block_pattern.findall(text):
            name = match[0].strip()
            transition = match[1] or match[2]  # puede venir del grupo con o sin corchetes
            suggestion = match[3].strip()

            if transition and transition.strip().lower() == "no":
                result[name] = suggestion
    except Exception as e:
        print(e)

    return result



def get_intro_suggestion(text: str) -> str | None:
    
    intro_match = re.search(r'Introducción:\s*(?:\[(Sí|No)\]|(Sí|No))\s*', text, re.IGNORECASE)
    suggestion_match = re.search(r'Sugerencia para mejorar introducción:\s*(.*)', text, re.IGNORECASE)

    if not intro_match or not suggestion_match:
        return None

    intro_value = (intro_match.group(1) or intro_match.group(2) or "").strip().lower()

    if intro_value in {"sí", "si"}:
        return None

    return suggestion_match.group(1).strip()


def get_order_suggestion(text: str) -> str | None:
    order_match = re.search(r'Orden lógico:\s*(Sí|No)', text, re.IGNORECASE)

    if not order_match:
        return None

    if order_match.group(1).strip().lower() in ["sí", "si"]:
        return None

    # Find the position after the label
    label_pattern = re.search(r'Sugerencias de mejora para el orden:\s*', text, re.IGNORECASE)
    
    if not label_pattern or not text:
        return None

    # Get the end position of the match
    start_pos = label_pattern.end()

    # Return everything after that position
    answer = text[start_pos:]
    if answer is not None:
        answer = answer.strip()
    return answer




def normalize(text: str) -> str:
    text = text.replace('�', '')  # you can also try 'e', 'o', or a guess
    return ''.join(
        c for c in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(c)
    ).lower()


def index_window_match(fragment: str, sentence: str, threshold: float = 0.62) -> bool:
    frag_words = re.findall(r'\w+', normalize(fragment))
    sent_words = re.findall(r'\w+', normalize(sentence))

    frag_len = len(frag_words)
    if frag_len == 0 or len(sent_words) < frag_len:
        return False

    # Slide a window over the sentence
    for i in range(len(sent_words) - frag_len + 1):
        window = sent_words[i:i+frag_len]
        exact_matches = sum(1 for j in range(frag_len) if frag_words[j] == window[j])
        match_ratio = exact_matches / frag_len

        if match_ratio >= threshold:
            return True

    return False

def find_fragment_location(text: str, fragment: str) -> tuple[int, int] | None:
    text = strip_accents(text)
    lines = text.splitlines()
    lines = [line.rstrip('\n') for line in lines]  # Remove any trailing newlines

    for line_num, line in enumerate(lines):
        if line.strip().startswith("\\section") or line.strip().startswith("\\chapter"):
            continue
        doc = nlp(line)
        for sent_num, sent in enumerate(doc.sents):

            if index_window_match(fragment, sent.text):
                return (line_num, sent_num-1)

    return None, None



def remove_empty_lines(text: str) -> str:
    lines = text.splitlines()
    non_empty_lines = [line for line in lines if line.strip()]
    return "\n".join(non_empty_lines)


def parse_ambiguity_response(text: str) -> list[dict]:
    """
    Parses a text containing one or more ambiguity analyses.
    This version is robustly handles multi-line content and different
    whitespace/newline separators between sections.
    """
    pattern = re.compile(
        r"(?:Response:\s*)?"
        r"Idea:\s*(.*?)\s*?"  # <-- 1. Changed to non-greedy whitespace match
        r"Ambigua(?:/No ambigua)?:\s*(Sí|Si|S�|No|Ambigua|No ambigua)\s*?" # <-- 2. Changed to non-greedy
        r"(?:Por qué|Por qu[ée�]):\s*(.*?)"
        r"(?=\n\s*(?:Response:\s*)?Idea:|\Z)",  # <-- 3. Improved lookahead
        re.DOTALL | re.IGNORECASE
    )

    matches = pattern.findall(text)
    result = []
    for idea, status, reason in matches:
        # Filter for ambiguous cases only
        if status.strip().lower() in {"sí", "si", "s�", "ambigua"}:
            result.append({
                "idea": idea.strip(),
                "reason": reason.strip()
            })
    return result




def parse_document_structure(latex_text: str) -> list:
    """Parses LaTeX text into a hierarchical list of chapters and sections."""
    latex_text = remove_empty_lines(latex_text)
    lines = latex_text.splitlines()
    result = ""
    intro = ""
    general_structure = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        chapter_match = re.match(r'^\s*\\(chapter|part)\*?\{(.+?)\}', line)
        section_match = re.match(r'^\s*\\(sub)*section\*?\{(.+?)\}', line)

        if chapter_match:
            
            title = chapter_match.group(2)  
            general_structure.append(f"Capítulo: {title}")
            intro += "{"+ f"Capítulo {title}: "
            i+=1
            line = lines[i]
            if re.match(r'^\s*\\(chapter|part)\*?\{', line) or re.match(r'^\s*\\(sub)*section\*?\{', line):
                intro += "no hay introducción}\n"
            else:
                intro += f"{line}" + "}\n"
                i+=1
            
        elif section_match:
            title = section_match.group(2)
            general_structure.append(f"Sección: {title}")
            result += "{"+ f"Sección {title}: " "Párrafo anterior: {"
            prev_line = lines[i-1]
            if re.match(r'^\s*\\(chapter|part)\*?\{', prev_line) or re.match(r'^\s*\\(sub)*section\*?\{', prev_line):
                result += "no text} Párrafo siguiente a sección: {"
            else:
                result += f"{prev_line}" + "} Párrafo siguiente a sección: {"
            i+=1
            line = lines[i]
            if re.match(r'^\s*\\(chapter|part)\*?\{', line) or re.match(r'^\s*\\(sub)*section\*?\{', line):
                result += "no text}\n"
            else:
                result += f"{line}" + "}\n"
                i+=1
        else:
            i+=1
        
    return result, intro, general_structure


def transition_analyzer(llm_client, latex_text: str):
    """Analyzes the narrative flow within and between sections for each chapter."""
    print("\n" + "="*20 + " 3. TRANSITION ANALYSIS " + "="*20)
    transitions_text, chapter_intro, general_structure = parse_document_structure(latex_text)
    intro = None
    answer = None
    if transitions_text:
        prompt_sections = (
            f"""A continuación tienes un conjunto de inicios de secciones. 
        El inicio de una sección tiene la estructura: 
        Sección nombre_de_sección: Párrafo anterior: {{}} Párrafo siguiente a sección: {{}}

        Tu tarea consiste en:
        1. Por cada sección, determinar si el párrafo que la precede y el que la sigue están interconectados y si hay una transición entre ellos. 
        Es decir, si hay una transición de una sección a la otra. 
        El último párrafo de una sección debería conectar con el primero de la siguiente.

        ### Texto a analizar:
        {transitions_text}

        ### Formato de respuesta (usa este formato estricto):
        Nombre de sección: sección
        Transición: [Sí/No]
        Sugerencia para incluir transición: []
        """
        )
        answer = llm_client.ask_llm(prompt_sections)
        if answer:
            print(answer)
            answer = extract_sections_without_transition(answer)
        print()
        if answer:
            print(answer)
    if chapter_intro:
        prompt_chapter = (
            f"""A continuación tienes el primer párrafo de un capítulo. 
        El inicio del capítulo tiene la estructura:
        {{Capítulo nombre_capítulo: 1er párrafo}}

        Tu tarea consiste en:
        1. Determinar si el párrafo con el que comienza el capítulo sirve como pequeña introducción al tema del capítulo.
        ### Texto a analizar:
        {chapter_intro}

        ### Formato de respuesta (usa este formato estricto):
        Introducción: [Sí/No]
        Sugerencia para mejorar introducción: []
        """)
        intro = llm_client.ask_llm(prompt_chapter)
        intro = get_intro_suggestion(intro)
    return answer, intro, general_structure

def logical_order_analyzer(llm_client, gen_structure):
    
    structure = "\n".join(gen_structure)

    prompt = (
        f"""A continuación tienes un conjunto de capítulo y secciones que representa el orden en que se trata un tema en un capítulo de una tesis. Si el primer elemento es un capítulo este va a contener el nombre del capítulo a analizar, que siempre viene primero que las secciones y sobre él no debes sugerir cambios.
    Tu tarea consiste en:

    1. Determinar si el orden propuesto para las secciones dado el nombre del capítulo está bien y en caso contrario sugerir otro orden con la justificación de tu propuesta.
    ### Estructura del capítulo:
    {structure}

    ### Formato de respuesta (usa este formato estricto):

    Orden lógico: [Sí/No]
    Sugerencias de mejora para el orden: []

    """
    )
        
    analysis = llm_client.ask_llm(prompt)
    print("Logical suggestions")
    answer = get_order_suggestion(analysis)

    return answer

def get_text_chunks(text, max_words: int, paragraph_amount: int) -> list[str]:
    # text va a ser una lista de tuplas (índice de línea en texto original, línea)
    # lines = full_text.splitlines()
    result = []
    curr_chunk = ""
    word_count = 0
    paragraph_count = 0

    for line in text:

        # Check for LaTeX structural commands
        match = re.match(r'^\s*\\(chapter|part|(sub)*section)\*?\{(.+?)\}', line)
        if match:
            command = match.group(1)
            title = match.group(3)
            line_text = f"{command}: {title} \n"
            word_count += len(title.split())
        else:
            line_text = line
            word_count += len(line.split())
            paragraph_count += 1

        curr_chunk += line_text + " "

        if word_count >= max_words or paragraph_count >= paragraph_amount:
            result.append(curr_chunk)
            # result.append(curr_chunk.strip())
            curr_chunk = ""
            word_count = 0
            paragraph_count = 0

    # Append any remaining text
    if curr_chunk:
        result.append(curr_chunk)

    return result

def check_ambiguity_and_transitions(text_lines_for_LLM, llm_client, line_mapper):
    chunks = get_text_chunks(text_lines_for_LLM, 400, 5)
    # chunks es un dict en el que las llaves corresponden a la
    mark_ambiguity = {}
    i = 0
    chunk_first_line_idx = 0
    while i < len(chunks):
        text_chunk = chunks[i]
        first_prompt = f"""Tienes el siguiente capítulo de una tesis en español. Tu tarea consiste en:
                1. Identificar las ideas que queden ambiguas o los conceptos que haga falta explicar porque dependan del contexto,  por ejemplo, los adverbios de modo en ocasiones dependen del punto de referencia. Si la idea está explicada en alguna parte del texto entonces no se considera ambigua.
                ### Texto a analizar:{text_chunk}
                ### Formato de respuesta (usa este formato estricto):
                Si no hay ideas ambiguas devolver: NO
                Si hay ideas ambiguas devolver:
                Idea: [oración exacta del texto]
                - Por qué es ambigua: [explicación]
                """
        llm_response = llm_client.ask_llm(first_prompt)

        second_prompt = f"""Tienes el siguiente capítulo de una tesis en español y una lista de ideas. Tu tarea consiste en:
                1. Identificar si las ideas quedan ambiguas, es decir, que leyendo el capítulo no es posible aclarar las preguntas que te haces al leerlas.
                ### Texto a analizar:{text_chunk}
                ### Ideas: {llm_response}
                ### Formato de respuesta (usa este formato estricto):
                Idea: [oración exacta del texto]
                Ambigua/No ambigua: [Si/No]
                Por qué: []
                """
        ambiguity = llm_client.ask_llm(second_prompt)
        ambiguous_ideas = parse_ambiguity_response(ambiguity)
        
        for element in ambiguous_ideas:
            line_idx, sentence_idx = find_fragment_location(text_chunk, element["idea"])
            if not line_idx:
                print(f"Not found:{element["idea"]}")
                sys.stdout.reconfigure(encoding='utf-8')
                print(element["idea"])
                print(f"!!!!TEXT: {text_chunk}")
                continue
            og_line_idx = line_mapper[line_idx+chunk_first_line_idx]
            
            key = (og_line_idx, sentence_idx)
            if key in mark_ambiguity:
                mark_ambiguity[key] += ", " + element["reason"]
            else:
                mark_ambiguity[key] = element["reason"]
        passed_lines = [line.strip() for line in text_chunk.split("\n") if line.strip()]
        chunk_first_line_idx += len(passed_lines)
        i+=1
    
    #transitions
    # vamos a marcar transiciones con nota para el autor
    transitions_answer, introduction, general_structure = transition_analyzer(llm_client, "\n".join(text_lines_for_LLM)) # devuelve lista de tuplas de la forma: [sección sin transición, sugerencia]
    logical_order_answer = logical_order_analyzer(llm_client, general_structure) # devuelve None si no hay sugerencias para el orden, en caso contrario devuelve una nota para el inicio del capítulo
    print(mark_ambiguity)
    return mark_ambiguity, transitions_answer, introduction, logical_order_answer

    
    